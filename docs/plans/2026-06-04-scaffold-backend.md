# pubHealthLLM Backend Scaffold — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold `/Volumes/Hub/dev/pubHealthLLM` as a clean backend-first repo — lift the proven v1 engine, swap Gradio for FastAPI, wire Clerk, get tests green, and stand up a TDD-built `/health` endpoint. No frontend, no `/ask` endpoint this session.

**Architecture:** `backend/` holds a FastAPI `server.py` (Railway-deployable), the lifted `pubhealth_llm/` engine package, baked-in `data/`, and the full test suite. `frontend/` is a placeholder only. Clerk guard is wired at startup but applied to no routes yet — that happens when `/ask` is built.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, fastapi-clerk-auth, httpx (test client), PydanticAI, ChromaDB, sentence-transformers, SQLite — all lifted from v1 with Gradio removed.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/server.py` | FastAPI app — `/health` only; Clerk guard wired but unapplied |
| Create | `backend/requirements.txt` | v1 deps minus gradio; plus fastapi, uvicorn, fastapi-clerk-auth, httpx |
| Create | `backend/pytest.ini` | pytest config (lifted from v1) |
| Create | `backend/.env` | Real secrets — gitignored |
| Create | `backend/.env.example` | Placeholder keys — committed |
| Copy → adapt | `backend/pubhealth_llm/` | Lifted engine package (app/, data_ingestion/, decision_tree/) |
| Copy → adapt | `backend/tests/` | Lifted test suite; remove Gradio tests; update env tests |
| Create | `backend/tests/test_health.py` | TDD: `/health` endpoint tests |
| Copy → adapt | `backend/Dockerfile.railway` | Railway deploy stub (no HF model download) |
| Copy → adapt | `backend/Dockerfile` | AWS build-context stub (no HF model download) |
| Copy | `terraform/` | AWS IaC reference (verbatim from Drug Discovery) |
| Create | `frontend/README.md` | "Deferred — do not build yet" |
| Create | `.gitignore` | Secrets, venv, pycache, large data files |
| Create | `.gitattributes` | Git LFS for healthgpt.db and chroma_db |
| Create | `README.md` | Project overview, how to run backend + tests |
| Create | `CLAUDE.md` | Conventions: TDD, Superpowers, no Gradio, engine lifted from v1 |

---

## Task 1: Directory skeleton + git init

**Files:**
- Create: `backend/`, `backend/data/`, `backend/pubhealth_llm/`, `backend/tests/`
- Create: `frontend/`
- Create: `terraform/`
- Create: `docs/plans/` (already exists)
- Create: `.gitignore`
- Create: `.gitattributes`

- [ ] **Step 1: Create top-level directories**

```bash
mkdir -p /Volumes/Hub/dev/pubHealthLLM/backend/data
mkdir -p /Volumes/Hub/dev/pubHealthLLM/backend/pubhealth_llm
mkdir -p /Volumes/Hub/dev/pubHealthLLM/backend/tests
mkdir -p /Volumes/Hub/dev/pubHealthLLM/frontend
mkdir -p /Volumes/Hub/dev/pubHealthLLM/terraform
```

- [ ] **Step 2: Create `.gitignore`**

Write `/Volumes/Hub/dev/pubHealthLLM/.gitignore`:

```gitignore
# Secrets
.env
*.env.local

# Python
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
*.egg-info/
dist/
build/

# Large data files (baked into Docker image, not committed)
backend/data/healthpub.db
backend/data/cdc_places_raw.csv
backend/data/cdc_places_county_raw.csv
backend/data/cdc_mortality_raw.csv

# DB and vector store tracked via Git LFS (see .gitattributes)
# If LFS unavailable, uncomment to exclude entirely:
# backend/data/healthgpt.db
# backend/data/chroma_db/

# Node / frontend (future)
node_modules/
.next/
out/

# macOS
.DS_Store

# Terraform state (contains sensitive data)
terraform/*.tfstate
terraform/*.tfstate.backup
terraform/.terraform/
terraform/terraform.tfvars

# Misc
query_log.txt
*.log
wandb/
```

- [ ] **Step 3: Create `.gitattributes` for Git LFS**

Write `/Volumes/Hub/dev/pubHealthLLM/.gitattributes`:

```
backend/data/healthgpt.db filter=lfs diff=lfs merge=lfs -text
backend/data/chroma_db/** filter=lfs diff=lfs merge=lfs -text
backend/data/mmwr_pdfs/** filter=lfs diff=lfs merge=lfs -text
```

- [ ] **Step 4: Initialize git repo**

```bash
cd /Volumes/Hub/dev/pubHealthLLM && git init
```

Expected output: `Initialized empty Git repository in /Volumes/Hub/dev/pubHealthLLM/.git/`

- [ ] **Step 5: Create `frontend/README.md` placeholder**

Write `/Volumes/Hub/dev/pubHealthLLM/frontend/README.md`:

```markdown
# Frontend (Deferred)

Backend-first. Do not build the frontend yet.

Planned stack: Next.js 16 / React 19 / TypeScript / shadcn-ui / Tailwind 4 / Clerk.

See `docs/plans/` for architecture decisions.
```

---

## Task 2: Lift engine package from v1

**Source (read-only):** `/Volumes/Hub/dev/rag/pubHealthLLM_v1`
**Destination:** `/Volumes/Hub/dev/pubHealthLLM/backend/`

- [ ] **Step 1: Copy engine package**

```bash
cp -r "/Volumes/Hub/dev/rag/pubHealthLLM_v1/pubhealth_llm" \
      /Volumes/Hub/dev/pubHealthLLM/backend/pubhealth_llm
```

- [ ] **Step 2: Copy test suite**

```bash
cp -r "/Volumes/Hub/dev/rag/pubHealthLLM_v1/tests" \
      /Volumes/Hub/dev/pubHealthLLM/backend/tests
```

- [ ] **Step 3: Copy pytest.ini**

```bash
cp "/Volumes/Hub/dev/rag/pubHealthLLM_v1/pytest.ini" \
   /Volumes/Hub/dev/pubHealthLLM/backend/pytest.ini
```

- [ ] **Step 4: Copy small data artifacts (NOT the large raw files)**

```bash
cp "/Volumes/Hub/dev/rag/pubHealthLLM_v1/data/healthgpt.db" \
   /Volumes/Hub/dev/pubHealthLLM/backend/data/healthgpt.db

cp -r "/Volumes/Hub/dev/rag/pubHealthLLM_v1/data/chroma_db" \
      /Volumes/Hub/dev/pubHealthLLM/backend/data/chroma_db

cp -r "/Volumes/Hub/dev/rag/pubHealthLLM_v1/data/mmwr_pdfs" \
      /Volumes/Hub/dev/pubHealthLLM/backend/data/mmwr_pdfs
```

Do NOT copy: `healthpub.db` (~881MB), `cdc_places_raw.csv` (~695MB), `cdc_places_county_raw.csv` (~51MB), `cdc_mortality_raw.csv`.

- [ ] **Step 5: Remove the Gradio layer from the copied package**

```bash
rm /Volumes/Hub/dev/pubHealthLLM/backend/pubhealth_llm/app/gradio_app.py
```

`agent.py`, `tools.py`, `schemas.py` stay intact.

- [ ] **Step 6: Verify the copy**

```bash
ls /Volumes/Hub/dev/pubHealthLLM/backend/pubhealth_llm/app/
# Expected: __init__.py  agent.py  schemas.py  tools.py
# NOT expected: gradio_app.py

ls /Volumes/Hub/dev/pubHealthLLM/backend/data/
# Expected: healthgpt.db  chroma_db/  mmwr_pdfs/
```

---

## Task 3: Secrets — `.env` and `.env.example`

**Sources (read-only):**
- LLM keys: `/Volumes/Hub/dev/rag/pubHealthLLM_v1/.env`
- Clerk keys: `/Volumes/Hub/dev/Drug Discovery/.env`

- [ ] **Step 1: Read source `.env` files for key names (do not print values)**

```bash
grep -E '^[A-Z_]+=.' "/Volumes/Hub/dev/rag/pubHealthLLM_v1/.env" | cut -d= -f1
grep -E '^[A-Z_]+=.' "/Volumes/Hub/dev/Drug Discovery/.env" | cut -d= -f1
```

- [ ] **Step 2: Create `backend/.env` with real values**

Use the Read tool to get the actual values from both source `.env` files, then write `backend/.env` containing:

```
ANTHROPIC_API_KEY=<from pubHealthLLM_v1/.env>
CLERK_JWKS_URL=<from Drug Discovery/.env>
CLERK_SECRET_KEY=<from Drug Discovery/.env>
# Optional — copy if present in pubHealthLLM_v1/.env:
OPENAI_API_KEY=<if present>
GROQ_API_KEY=<if present>
LLAMA_CLOUD_API_KEY=<if present>
```

**Never print these values. Use Write tool directly.**

- [ ] **Step 3: Verify `.env` is gitignored before any commit**

```bash
cd /Volumes/Hub/dev/pubHealthLLM && git check-ignore -v backend/.env
```

Expected: `backend/.env` is listed as ignored.

- [ ] **Step 4: Create `backend/.env.example`**

Write `/Volumes/Hub/dev/pubHealthLLM/backend/.env.example`:

```
# pubHealthLLM — environment variable template
# Copy to .env and fill in real values. Never commit .env.

# Required: LLM inference
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Required: Clerk authentication
CLERK_JWKS_URL=https://your-clerk-domain.clerk.accounts.dev/.well-known/jwks.json
CLERK_SECRET_KEY=sk_test_your-clerk-secret-key-here

# Optional: additional LLM providers
OPENAI_API_KEY=sk-your-openai-key-here
GROQ_API_KEY=gsk_your-groq-key-here
LLAMA_CLOUD_API_KEY=llx-your-llama-cloud-key-here
```

---

## Task 4: Update `requirements.txt`

**Files:**
- Create: `backend/requirements.txt`

- [ ] **Step 1: Write updated `requirements.txt`**

Write `/Volumes/Hub/dev/pubHealthLLM/backend/requirements.txt`:

```
# pubHealthLLM backend — Python dependencies
# Python: 3.11+

# ---------------------------------------------------------------------------
# Web framework
# ---------------------------------------------------------------------------
fastapi>=0.115.0
uvicorn>=0.30.0
fastapi-clerk-auth

# ---------------------------------------------------------------------------
# Core agent framework
# ---------------------------------------------------------------------------
pydantic-ai==1.86.0
pydantic==2.12.5

# ---------------------------------------------------------------------------
# LLM providers
# ---------------------------------------------------------------------------
anthropic==0.96.0
openai==2.32.0
groq>=0.8.0

# ---------------------------------------------------------------------------
# Vector database and embeddings
# ---------------------------------------------------------------------------
chromadb==1.5.8
sentence-transformers==5.4.1

# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------
PyPDF2==3.0.1

# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------
pandas==3.0.2
sqlalchemy==2.0.49
requests==2.32.4

# ---------------------------------------------------------------------------
# Web scraping (MMWR index)
# ---------------------------------------------------------------------------
beautifulsoup4==4.14.3

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
python-dotenv==1.2.2
tqdm==4.67.3

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
pytest==8.4.1
pytest-asyncio==1.3.0
httpx>=0.27.0
```

Note: `gradio==6.13.0` removed. `fastapi`, `uvicorn`, `fastapi-clerk-auth`, `httpx` added.

---

## Task 5: Fix lifted tests for the new context

Three test files import from Gradio or test Groq-only env vars. Remove or replace them.

**Files:**
- Delete: `backend/tests/test_gradio_app.py`
- Rewrite: `backend/tests/test_environment.py`
- Partially rewrite: `backend/tests/test_model_selection.py` (remove Gradio imports at end)

- [ ] **Step 1: Remove the Gradio test file**

```bash
rm /Volumes/Hub/dev/pubHealthLLM/backend/tests/test_gradio_app.py
```

Reason: `gradio_app.py` was deleted in Task 2. Tests would error on import, not on logic.

- [ ] **Step 2: Rewrite `test_environment.py`**

The v1 version tests `GROQ_API_KEY` only. Replace with tests for the keys this project actually requires.

Write `/Volumes/Hub/dev/pubHealthLLM/backend/tests/test_environment.py`:

```python
"""
Tests for environment configuration.

Verifies required API keys are loaded from .env and have plausible values.
Does NOT make network calls.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")


def test_anthropic_api_key_is_set():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    assert key, (
        "ANTHROPIC_API_KEY is not set. "
        "Copy .env.example to .env and add your Anthropic key."
    )


def test_anthropic_api_key_not_placeholder():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    assert key != "sk-ant-your-key-here", (
        "ANTHROPIC_API_KEY still has the placeholder value from .env.example."
    )


def test_anthropic_api_key_non_empty_string():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    assert len(key) > 10, f"ANTHROPIC_API_KEY is too short ({len(key)} chars)."


def test_clerk_jwks_url_is_set():
    url = os.getenv("CLERK_JWKS_URL", "")
    assert url, (
        "CLERK_JWKS_URL is not set. "
        "Copy from the Drug Discovery project .env."
    )


def test_clerk_jwks_url_looks_like_url():
    url = os.getenv("CLERK_JWKS_URL", "")
    assert url.startswith("https://"), f"CLERK_JWKS_URL must be an https URL, got: {url!r}"


def test_clerk_secret_key_is_set():
    key = os.getenv("CLERK_SECRET_KEY", "")
    assert key, "CLERK_SECRET_KEY is not set."


def test_env_file_exists():
    env_path = Path(__file__).parents[1] / ".env"
    assert env_path.exists(), ".env not found. Run: cp .env.example .env"


def test_data_directory_exists():
    data_dir = Path(__file__).parents[1] / "data"
    assert data_dir.is_dir(), "data/ directory missing from backend/."
```

- [ ] **Step 3: Remove Gradio-dependent tests from `test_model_selection.py`**

The bottom of `test_model_selection.py` (sections 8–10) imports from `pubhealth_llm.app.gradio_app` which no longer exists. Remove those sections.

Read the file, then delete everything from the line containing `# 8. Gradio chat() function signature` to the end of the file.

- [ ] **Step 4: Verify no remaining Gradio imports in tests**

```bash
grep -r "gradio" /Volumes/Hub/dev/pubHealthLLM/backend/tests/ --include="*.py"
```

Expected: no output.

---

## Task 6: Python venv and baseline test run (TDD checkpoint 1)

- [ ] **Step 1: Create virtualenv**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend && python3 -m venv .venv
```

- [ ] **Step 2: Install dependencies**

```bash
/Volumes/Hub/dev/pubHealthLLM/backend/.venv/bin/pip install --upgrade pip
/Volumes/Hub/dev/pubHealthLLM/backend/.venv/bin/pip install -r \
    /Volumes/Hub/dev/pubHealthLLM/backend/requirements.txt
```

This will take a few minutes (sentence-transformers + chromadb are large).

- [ ] **Step 3: Run the lifted test suite**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend && \
    .venv/bin/pytest tests/ -v --tb=short 2>&1 | head -100
```

- [ ] **Step 4: Triage failures**

Expected pass: all tests except any that still import gradio (should be zero after Task 5).

Expected skip: `test_anthropic_api.py`, `test_groq_api.py` (live API keys — skip if not set, which is correct).

If any unexpected failures appear, fix them minimally:
- Import errors due to missing module → check if the module was deleted in error
- Path errors (`.env` location) → conftest.py uses `Path(__file__).parents[1]` which resolves correctly to `backend/` after the copy; no change needed
- Any test that imports `gradio_app` → remove just that test function

- [ ] **Step 5: Confirm suite green (excluding intentionally removed Gradio tests)**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend && \
    .venv/bin/pytest tests/ -v --ignore=tests/test_health.py 2>&1 | tail -20
```

Expected: all collected tests pass or are skipped (skipped = live API tests without keys).

- [ ] **Step 6: Commit baseline**

```bash
cd /Volumes/Hub/dev/pubHealthLLM
git add backend/pubhealth_llm/ backend/tests/ backend/pytest.ini \
        backend/requirements.txt backend/.env.example \
        .gitignore .gitattributes frontend/README.md docs/
git commit -m "$(cat <<'EOF'
feat: lift pubhealth_llm engine and test suite from v1

- Copy pubhealth_llm/ (app/, data_ingestion/, decision_tree/) from v1
- Copy test suite (95 tests); remove gradio_app test; update env tests
- requirements.txt: remove gradio, add fastapi/uvicorn/clerk/httpx
- .gitignore, .gitattributes (Git LFS for data artifacts)
- frontend/ placeholder only

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: TDD — `/health` endpoint (TDD checkpoint 2)

Follow strict red → green → refactor. Write the test, watch it fail, implement minimum code to pass.

**Files:**
- Create: `backend/tests/test_health.py`
- Create: `backend/server.py`

- [ ] **Step 1: Write the failing test**

Write `/Volumes/Hub/dev/pubHealthLLM/backend/tests/test_health.py`:

```python
"""
Tests for GET /health.

The health endpoint is public (no auth), returns 200 with a small
JSON status payload. Clerk guard is wired at startup but does not
protect this route.
"""

import pytest
from unittest.mock import patch


@pytest.fixture(scope="module")
def client():
    # Patch Clerk guard init to avoid needing a live JWKS URL in tests
    with patch("server.ClerkHTTPBearer") as mock_guard:
        mock_guard.return_value = lambda: None
        from fastapi.testclient import TestClient
        from server import app
        return TestClient(app)


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_status_is_ok(client):
    resp = client.get("/health")
    assert resp.json()["status"] == "ok"


def test_health_has_version_key(client):
    resp = client.get("/health")
    assert "version" in resp.json()


def test_health_has_data_key(client):
    resp = client.get("/health")
    assert "data" in resp.json()


def test_health_data_has_db_and_chroma(client):
    resp = client.get("/health")
    data = resp.json()["data"]
    assert "db" in data
    assert "chroma" in data
```

- [ ] **Step 2: Run the test — confirm it FAILS**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend && \
    .venv/bin/pytest tests/test_health.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError: No module named 'server'` or `ImportError`. This is correct — the test is red.

- [ ] **Step 3: Implement minimum `server.py` to make tests pass**

Write `/Volumes/Hub/dev/pubHealthLLM/backend/server.py`:

```python
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
        "version": "0.1.0",
        "data": {
            "db": str(_DATA_DIR / "healthgpt.db"),
            "chroma": str(_DATA_DIR / "chroma_db"),
        },
    }
```

- [ ] **Step 4: Run the test — confirm it PASSES**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend && \
    .venv/bin/pytest tests/test_health.py -v 2>&1 | tail -20
```

Expected:
```
PASSED tests/test_health.py::test_health_returns_200
PASSED tests/test_health.py::test_health_status_is_ok
PASSED tests/test_health.py::test_health_has_version_key
PASSED tests/test_health.py::test_health_has_data_key
PASSED tests/test_health.py::test_health_data_has_db_and_chroma
5 passed
```

- [ ] **Step 5: Run full suite — confirm nothing regressed**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend && \
    .venv/bin/pytest tests/ -v 2>&1 | tail -30
```

- [ ] **Step 6: Smoke test with uvicorn**

```bash
cd /Volumes/Hub/dev/pubHealthLLM/backend && \
    .venv/bin/uvicorn server:app --port 8001 &
sleep 2
curl -s http://localhost:8001/health | python3 -m json.tool
kill %1
```

Expected: JSON with `status: ok`.

- [ ] **Step 7: Commit**

```bash
cd /Volumes/Hub/dev/pubHealthLLM
git add backend/server.py backend/tests/test_health.py
git commit -m "$(cat <<'EOF'
feat: add /health endpoint (TDD) with Clerk guard wired

- Write test_health.py first (red), then implement server.py (green)
- Clerk guard instantiated at startup; not yet applied to any route
- CORS locked to localhost; TODO: add production origin at deploy time

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Deployment scaffolding (reference stubs only)

**Files:**
- Create: `backend/Dockerfile.railway`
- Create: `backend/Dockerfile`
- Copy: `terraform/` from Drug Discovery

- [ ] **Step 1: Write `backend/Dockerfile.railway`**

Write `/Volumes/Hub/dev/pubHealthLLM/backend/Dockerfile.railway`:

```dockerfile
# backend/Dockerfile.railway
# Railway deployment: build context is backend/ directory.
# Do NOT use for AWS — use backend/Dockerfile (project-root context) for that.
#
# Key difference from Drug Discovery template:
#   - No HuggingFace model download layer (no ML model to pull)
#   - data/ directory is BAKED INTO the image (healthgpt.db + chroma_db)
#     so there is zero cold-start download delay at runtime.
#   - TODO: bump memory to 2–4 GB in Railway settings (sentence-transformers
#     + ChromaDB need headroom; Drug Discovery used 3 GB for PyTorch).

FROM python:3.11-slim

WORKDIR /app

# System deps for sentence-transformers / chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies (split layer for better caching)
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements.txt

# Bake application source
# TODO: update COPY list when new modules are added (e.g. rate_limiter.py)
COPY server.py /app/

# Bake engine package
COPY pubhealth_llm/ /app/pubhealth_llm/

# Bake data artifacts (healthgpt.db ~84MB, chroma_db ~3.3MB)
# These are built once during ingestion and committed via Git LFS.
# TODO: if data grows beyond ~500MB, move to a Railway volume mount instead.
COPY data/ /app/data/

EXPOSE 8000

# TODO: increase --workers to 2 once memory budget is confirmed
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

- [ ] **Step 2: Write `backend/Dockerfile` (AWS / project-root build context)**

Write `/Volumes/Hub/dev/pubHealthLLM/backend/Dockerfile`:

```dockerfile
# backend/Dockerfile
# Build context must be the project root:
#   docker build -f backend/Dockerfile .
# Used by AWS App Runner via Terraform (see terraform/).
# For Railway use backend/Dockerfile.railway instead.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /tmp/requirements.txt

COPY backend/server.py /app/
COPY backend/pubhealth_llm/ /app/pubhealth_llm/
COPY backend/data/ /app/data/

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

- [ ] **Step 3: Copy Terraform from Drug Discovery as reference**

```bash
cp -r "/Volumes/Hub/dev/Drug Discovery/terraform/" \
      /Volumes/Hub/dev/pubHealthLLM/terraform/
```

Do not run any `terraform` commands.

- [ ] **Step 4: Commit deployment scaffolding**

```bash
cd /Volumes/Hub/dev/pubHealthLLM
git add backend/Dockerfile backend/Dockerfile.railway terraform/
git commit -m "$(cat <<'EOF'
chore: add deployment scaffolding (Railway + AWS Terraform reference)

- Dockerfile.railway: bakes data/ into image, no HF model download
- Dockerfile: project-root build context for AWS App Runner
- terraform/: verbatim from Drug Discovery as IaC reference (not deployed)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Root docs — README + CLAUDE.md

**Files:**
- Create: `README.md`
- Create: `CLAUDE.md`

- [ ] **Step 1: Write root `README.md`**

Write `/Volumes/Hub/dev/pubHealthLLM/README.md`:

```markdown
# pubHealthLLM

AI-powered public health decision support. Answers evidence-based questions
about population health using CDC PLACES, MMWR surveillance, and NCHS
mortality data.

**Status:** Backend scaffold complete. Frontend deferred.

---

## Running the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY + Clerk keys
uvicorn server:app --reload
```

Health check: `curl http://localhost:8000/health`

## Running tests

```bash
cd backend
pytest tests/ -v
```

Live API tests (agent, Anthropic) are automatically skipped if keys are absent.

## Architecture

See `docs/plans/2026-06-04-scaffold-backend.md` and `ARCHITECTURE.md` (if present).

- `backend/pubhealth_llm/` — lifted engine: PydanticAI agent, 8 tools, schemas, ingestion
- `backend/data/` — baked-in: healthgpt.db (CDC PLACES + mortality), chroma_db (MMWR)
- `backend/server.py` — FastAPI; `/health` (public), `/ask` (Clerk, coming next)
- `frontend/` — deferred (Next.js 16 / shadcn / Clerk)
- `terraform/` — AWS App Runner + ECR reference (not deployed)
```

- [ ] **Step 2: Write `CLAUDE.md`**

Write `/Volumes/Hub/dev/pubHealthLLM/CLAUDE.md`:

```markdown
# CLAUDE.md — pubHealthLLM conventions

## Non-negotiable rules

1. **TDD always.** Write the failing test first. Red → green → refactor.
   No production code without a failing test that demanded it.

2. **Use Superpowers.** Before any non-trivial work: brainstorm → plan →
   execute with TDD skill. The workflow is: `superpowers:brainstorming` →
   `superpowers:writing-plans` → `superpowers:executing-plans` (or subagent-driven).

3. **No frontend this session.** `frontend/` is a placeholder. Do not run
   `create-next-app`, do not install npm packages. Frontend is a separate session.

4. **No `/ask` endpoint yet.** The agent HTTP layer is designed in a separate
   session after the scaffold is complete.

## Project context

- Engine lifted from `pubHealthLLM_v1` (read-only at `/Volumes/Hub/dev/rag/pubHealthLLM_v1`).
- Gradio and HuggingFace Spaces target dropped. Replaced by FastAPI.
- Structural template: Drug Discovery at `/Volumes/Hub/dev/Drug Discovery` (read-only).
- Deploy target: Railway (backend), Vercel (frontend). Terraform = AWS fallback only.

## Backend layout

```
backend/
├── server.py              # FastAPI app — only edit this for HTTP layer
├── pubhealth_llm/
│   ├── app/
│   │   ├── agent.py       # PydanticAI agent + run_agent()
│   │   ├── tools.py       # 8 tools (CDC PLACES, MMWR, mortality)
│   │   └── schemas.py     # PublicHealthResponse — this IS the API contract
│   ├── data_ingestion/    # CDC PLACES → SQLite, MMWR → ChromaDB
│   └── decision_tree/     # Health economic Monte Carlo (phase 2)
├── data/                  # Baked into Docker image; tracked via Git LFS
├── tests/
└── requirements.txt
```

## Key decisions (from ARCHITECTURE.md)

- `PublicHealthResponse` schema is the JSON API contract. Return it as-is from `/ask`.
- Simplify model registry to Claude only (+ one fallback). Drop Groq condensed-prompt hack.
- Clerk auth from day one: `Depends(clerk_guard)` on `/ask` + `/measures`; `/health` public.
- CORS locked to known origins — not `*`.
- Rate limit `/ask` — it calls a paid LLM with 8 tools.
- Data is baked into the Docker image (not downloaded at runtime).
```

- [ ] **Step 3: Final commit**

```bash
cd /Volumes/Hub/dev/pubHealthLLM
git add README.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: add README and CLAUDE.md with project conventions

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Done checklist

- [ ] `ARCHITECTURE.md` read; plan saved to `docs/plans/2026-06-04-scaffold-backend.md`
- [ ] Directory structure created; `frontend/` is a placeholder only
- [ ] Engine package + small data artifacts lifted; large files and Gradio layer excluded
- [ ] `backend/.env` has real keys; `.env.example` committed; `.env` gitignored; no values printed
- [ ] Lifted pytest suite green (minus removed Gradio + env tests, noted above)
- [ ] `/health` built test-first (red → green); Clerk guard wired to no routes
- [ ] Dockerfiles + terraform copied as adapted stubs; nothing deployed
- [ ] git initialized; hygiene files in place; clean commits; tests green

## Tests intentionally removed / replaced

| File | Reason |
|------|--------|
| `test_gradio_app.py` | Gradio layer dropped; tests import `gradio_app.py` which was deleted |
| `test_environment.py` | Rewrote: dropped Groq-only key checks, added Anthropic + Clerk checks |
| `test_model_selection.py` sections 8–10 | Imported from `gradio_app.py`; sections 1–7 (agent.py) kept intact |

## Deferred (not this session)

- `/ask` endpoint (agent HTTP layer) — designed in next session
- `/measures` endpoint
- Frontend (Next.js, Clerk UI, brief-style layout)
- Railway deployment + Railway env vars
- Rate limiting on `/ask`
- SSE streaming of tool-call progress
- RAG eval harness + reranker
- Decision tree mode (phase 2)
