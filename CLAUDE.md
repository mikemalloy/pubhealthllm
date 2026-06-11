# CLAUDE.md — pubHealthLLM conventions

## Non-negotiable rules

0. **Track progress in `PROGRESS.md`.** Before any work, read `PROGRESS.md` and
   resume from the "You are here" marker. Before stopping, update its checkboxes,
   move the marker, add a session-log line, and commit it
   (`git add PROGRESS.md && git commit`). The commit is what makes the state
   survive a dead session — commit `PROGRESS.md` even if nothing else is ready.

1. **TDD always (backend).** Write the failing test first. Red → green →
   refactor. No production code without a failing test that demanded it. (Applies
   to the Python backend. The frontend uses build + lint + manual smoke checks,
   not pytest — see Phase E.)

2. **Use Superpowers.** Before any non-trivial work: invoke the relevant skill.
   Planning: `writing-plans`. Execution: `subagent-driven-development`.
   Debugging: `systematic-debugging`. New features: `brainstorming` first.

3. **Frontend is now ACTIVE (Phase E).** Built in `frontend/` by copying the
   shadcn template at `/Volumes/Hub/dev/ui-templates/shadcn` (read-only) and
   stripping it down. Stack: Next.js 15 / React 19 / Tailwind 4 / shadcn /
   next-themes / pnpm / lucide-react / Clerk. UI placeholders only — do NOT wire
   pubHealth data/endpoints into the UI yet.

4. **Backend is DONE and deployed** (AWS Lambda + Function URL, `/health` + `/ask` + `/measures`,
   Clerk-guarded). Do NOT change backend behavior during the frontend phase.
   - Function URL: `https://4tgkp3yp35krou263q3m5a5xpu0dtqrt.lambda-url.us-west-1.on.aws`
   - CORS_ORIGINS: `https://pubhealth.chefmike.dev`
   - Terraform: `terraform/6_backend/` (old App Runner root files archived to `terraform/archive/`)

## Project context

- Engine lifted from `pubHealthLLM_v1` (read-only at `/Volumes/Hub/dev/rag/pubHealthLLM_v1`).
- Gradio and HuggingFace Spaces target dropped. Replaced by FastAPI.
- Structural template: Drug Discovery at `/Volumes/Hub/dev/Drug Discovery` (read-only).
- Deploy target: AWS Lambda (backend, us-west-1), Vercel (frontend, pubhealth.chefmike.dev).

## Backend layout

```
backend/
├── server.py              # FastAPI app — only edit this for HTTP layer
├── pubhealth_llm/
│   ├── app/
│   │   ├── agent.py       # PydanticAI agent + run_agent()
│   │   ├── tools.py       # 8 tools (CDC PLACES, MMWR, mortality)
│   │   └── schemas.py     # PublicHealthResponse — this IS the API contract
│   ├── data_ingestion/    # CDC PLACES → Aurora Serverless v2, MMWR → S3 Vectors
│   └── decision_tree/     # Health economic Monte Carlo (phase 2)
├── data/                  # Baked into Docker image; tracked via Git LFS
├── tests/
└── requirements.txt
```

## Key decisions (from ARCHITECTURE.md)

- `PublicHealthResponse` schema is the JSON API contract. Return it as-is from `/ask`.
- LLM: `bedrock:us.amazon.nova-pro-v1:0` (cross-region inference profile). No Anthropic/Groq.
- Vector store: S3 Vectors (`pubhealth-vectors` bucket, `mmwr-embeddings` index). No ChromaDB.
- Relational data: Aurora Serverless v2 via Data API. No SQLite.
- Clerk auth from day one: `Depends(clerk_guard)` on `/ask` + `/measures`; `/health` public.
- CORS locked to known origins — not `*`.
- Rate limit `/ask` — it calls a paid LLM with 8 tools.
- Data lives in AWS (Aurora + S3 Vectors) — no baked-in data files or Docker image.

## Known concerns (address before building /ask)

- Test mock for Clerk guard in `test_health.py` is fragile if `server` module is imported
  elsewhere first. Refactor to lazy Clerk init or `conftest.py` autouse fixture before
  adding more routes.
- `allow_headers=["*"]` in CORS — narrow to `["Authorization", "Content-Type"]` at deploy.
