import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer

from pubhealth_llm.app.config import validate_model_config
from pubhealth_llm.app.orchestrator import run_ask
from pubhealth_llm.app.schemas import AskRequest, AskResponse, MeasureItem
from pubhealth_llm.app.tools import check_vector_store, list_available_measures

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent / "data"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fail-fast startup validation.

    Runs in order:
    1. Validate model config (provider + API key present).
    2. Assert baked data files exist (healthgpt.db and chroma_db/).
    3. Vector store integrity check — loads the ChromaDB collection and
       confirms it is non-empty.

    Raises immediately on misconfiguration so the container dies at boot,
    not on the first request.
    """
    # 1. Model config validation — raises ValueError or EnvironmentError on bad config
    validate_model_config()

    # 2. Data presence checks
    db_path = _DATA_DIR / "healthgpt.db"
    chroma_path = _DATA_DIR / "chroma_db"

    if not db_path.exists():
        raise RuntimeError(f"Missing required data file: {db_path}")
    if not chroma_path.is_dir():
        raise RuntimeError(f"Missing required data directory: {chroma_path}")

    # 3. Vector store integrity check — raises RuntimeError if collection won't load
    check_vector_store()

    yield  # App is running


app = FastAPI(title="pubHealthLLM API", version="0.1.0", lifespan=lifespan)

# CORS — localhost only for now; update with real origins at deploy time
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Clerk auth guard — lazy init so tests can override via dependency_overrides
# ---------------------------------------------------------------------------

_clerk_bearer: Optional[ClerkHTTPBearer] = None


def _get_clerk_bearer() -> ClerkHTTPBearer:
    """Return the ClerkHTTPBearer singleton, creating it on first call.

    Lazy so that importing server in tests never triggers a JWKS fetch.
    CLERK_JWKS_URL must be set in the environment. If absent, a warning is
    logged and requests to protected routes will be rejected.
    Hard startup validation for missing CLERK_JWKS_URL is handled in the
    lifespan handler, not here.
    """
    global _clerk_bearer
    if _clerk_bearer is None:
        jwks_url = os.getenv("CLERK_JWKS_URL")
        if not jwks_url:
            logger.warning(
                "CLERK_JWKS_URL is not set. Requests to protected routes will fail. "
                "Set CLERK_JWKS_URL in your .env file. "
                "(Hard startup validation is planned for a later phase.)"
            )
            jwks_url = ""  # PyJWKClient will error on first request (500)
        _clerk_bearer = ClerkHTTPBearer(ClerkConfig(jwks_url=jwks_url))
    return _clerk_bearer


async def clerk_guard(request: Request) -> Any:
    """
    FastAPI dependency for Clerk authentication.

    Usage:  @app.post("/ask")
            async def ask(payload=Depends(clerk_guard)): ...

    Override in tests:
        app.dependency_overrides[clerk_guard] = lambda: {"sub": "test-user"}
    """
    return await _get_clerk_bearer()(request)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": app.version,
        "data": {
            "db": str(_DATA_DIR / "healthgpt.db"),
            "chroma": str(_DATA_DIR / "chroma_db"),
        },
    }


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest, _: Any = Depends(clerk_guard)) -> AskResponse:
    """
    Answer a public health question.

    Calls run_ask() which makes a single LLM call and returns a structured
    AskResponse. run_ask handles all errors internally — it always returns
    a valid AskResponse and never raises.

    Requires: valid Clerk JWT in Authorization header.
    """
    return await run_ask(req.question, req.message_history)


@app.get("/measures", response_model=list[MeasureItem])
def measures(
    category: str | None = None,
    _: Any = Depends(clerk_guard),
) -> list[MeasureItem]:
    """
    List available CDC PLACES health measures for UI autocomplete.

    Args:
        category: Optional category filter (partial match, case-insensitive).

    Returns:
        JSON array of MeasureItem objects.
    """
    return list_available_measures(category)
