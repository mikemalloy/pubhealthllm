import os
from pathlib import Path

from fastapi import FastAPI
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

# Clerk guard — wired at startup, applied to no routes yet.
# Add Depends(clerk_guard) to /ask and /measures when those are built.
clerk_config = ClerkConfig(
    jwks_url=os.getenv(
        "CLERK_JWKS_URL",
        "https://placeholder.clerk.invalid/.well-known/jwks.json",
    )
)
clerk_guard = ClerkHTTPBearer(clerk_config)

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
