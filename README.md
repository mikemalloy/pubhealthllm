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

See `docs/plans/2026-06-04-scaffold-backend.md` for the scaffolding plan.

- `backend/pubhealth_llm/` — lifted engine: PydanticAI agent, 8 tools, schemas, ingestion
- `backend/data/` — baked-in: healthgpt.db (CDC PLACES + mortality), chroma_db (MMWR)
- `backend/server.py` — FastAPI; `/health` (public), `/ask` (Clerk, coming next)
- `frontend/` — deferred (Next.js 16 / shadcn / Clerk)
- `terraform/` — AWS App Runner + ECR reference (not deployed)

## Data sources

| Source | Type | Coverage |
|--------|------|----------|
| CDC PLACES 2023 | 36 health measures (diabetes, obesity, smoking…) | ~3,000 US counties |
| CDC MMWR 2022–2024 | Weekly surveillance reports | ~200 chunks, semantic search |
| CDC NCHS Mortality | Leading causes of death, age-adjusted rates | State-level, 1999–2017 |
