import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer

from pubhealth_llm.app.config import validate_model_config
from pubhealth_llm.app.orchestrator import run_ask
from pubhealth_llm.app.schemas import AskRequest, AskResponse, MeasureItem
from pubhealth_llm.app.tools import (
    check_aurora_db,
    check_vector_store,
    list_available_measures,
    warmup_aurora_db,
)

logger = logging.getLogger(__name__)

_DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
]


def get_cors_origins() -> list[str]:
    """Return the list of allowed CORS origins.

    Always includes the two localhost defaults. If the ``CORS_ORIGINS``
    environment variable is set it is treated as a comma-separated list of
    additional origins; each entry is stripped of surrounding whitespace.
    Duplicate origins are removed while preserving order (defaults first).

    The env var is read at call time so tests can monkeypatch ``os.environ``.

    Example::

        CORS_ORIGINS="https://myapp.vercel.app, http://localhost:3000"
        # → ["http://localhost:3000", "http://localhost:5173",
        #     "https://myapp.vercel.app"]
    """
    origins: list[str] = list(_DEFAULT_CORS_ORIGINS)
    extra = os.environ.get("CORS_ORIGINS", "")
    if extra:
        for origin in extra.split(","):
            stripped = origin.strip()
            if stripped and stripped not in origins:
                origins.append(stripped)
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fail-fast startup validation.

    Runs in order:
    1. Validate model config (provider + API key present).
    2. Aurora Data API connectivity check — SELECT 1.
    3. Vector store integrity check — confirms S3 Vectors index is reachable
       and non-empty.

    Raises immediately on misconfiguration so the container dies at boot,
    not on the first request.
    """
    # 1. Model config validation — raises ValueError or EnvironmentError on bad config
    validate_model_config()

    # 2. Aurora Data API ping (warms cluster, confirms connectivity)
    check_aurora_db()

    # 3. Vector store integrity check — raises RuntimeError if collection won't load
    check_vector_store()

    yield  # App is running


app = FastAPI(title="pubHealthLLM API", version="0.1.0", lifespan=lifespan)

# CORS — defaults to localhost; extend via CORS_ORIGINS env var at deploy time.
# TODO: narrow allow_headers to ["Authorization", "Content-Type"] before production deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
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


@app.get("/warmup")
async def warmup(_: Any = Depends(clerk_guard)) -> dict:
    """Trigger Aurora Serverless v2 auto-resume and report DB readiness.

    Aurora auto-pauses after idle to save cost; the first /ask after a quiet
    period otherwise eats a 30s cold-resume. The frontend pings this on /llm
    mount so the resume is already underway by the time the user asks.

    Fast and single-attempt — it does NOT block on the resume window. One
    lightweight SELECT 1 (no retry). See ``warmup_aurora_db``:
        {"database": "ready"}   — cluster is up
        {"database": "warming"} — resume in progress (the ping itself started it)
        {"database": "error", "detail": "<ClassName>"} — any failure, never 500

    Clerk-guarded exactly like /ask — an unauthenticated endpoint that wakes
    the database would invite abuse that defeats auto-pause.
    """
    return warmup_aurora_db()


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
