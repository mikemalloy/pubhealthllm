# CLAUDE.md — pubHealthLLM conventions

## Non-negotiable rules

1. **TDD always.** Write the failing test first. Red → green → refactor.
   No production code without a failing test that demanded it.

2. **Use Superpowers.** Before any non-trivial work: invoke the relevant skill.
   Planning: `writing-plans`. Execution: `subagent-driven-development`.
   Debugging: `systematic-debugging`. New features: `brainstorming` first.

3. **No frontend this session.** `frontend/` is a placeholder. Do not run
   `create-next-app` or install npm packages until a frontend plan exists.

4. **No `/ask` endpoint yet.** The agent HTTP layer is designed in a separate
   session after the scaffold is reviewed.

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

## Known concerns (address before building /ask)

- Test mock for Clerk guard in `test_health.py` is fragile if `server` module is imported
  elsewhere first. Refactor to lazy Clerk init or `conftest.py` autouse fixture before
  adding more routes.
- `allow_headers=["*"]` in CORS — narrow to `["Authorization", "Content-Type"]` at deploy.
