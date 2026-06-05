import os
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi_clerk_auth import ClerkConfig, ClerkHTTPBearer

app = FastAPI(title="pubHealthLLM API", version="0.1.0")

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
    Set CLERK_JWKS_URL to the real endpoint in production.
    """
    global _clerk_bearer
    if _clerk_bearer is None:
        jwks_url = os.getenv(
            "CLERK_JWKS_URL",
            "https://placeholder.clerk.invalid/.well-known/jwks.json",
        )
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


_DATA_DIR = Path(__file__).parent / "data"


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
