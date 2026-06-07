# PROGRESS — server-side build state

**This file is the single source of truth for "where are we."** It is committed to
git, so it survives a dead session. Read it at the start of every session; update
the checkboxes and the "You are here" pointer at the end of every session, then
commit it (`git add PROGRESS.md && git commit -m "progress: <what changed>"`).

Status keys: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked.

---

## Current decision (why we're here)

The multi-agent code that got built is the **full planner + responder** version.
`ARCHITECTURE.md §3a` was simplified to a **lean, no-planner** design. Code and
doc diverged. We are aligning the **code to the doc**: strip the planner LLM call
so `/ask` makes one model call, not two. The planner/responder modules are
**parked, not deleted** (they're already tested; §3a re-introduces them in a
later phase).

**You are here →** Phase D, item D2. Path from here:
D2 → D3 → D4 → UI.

C2 live check passed the contract (chat / artifact modes correct, real CDC PLACES
statistics in payloads). Two findings surfaced, to clear before Docker:

---

## Phase A — Lean heuristic refactor (DO THIS FIRST)

Goal: `run_ask` makes exactly **one** LLM call and derives mode from the payload.

- [x] **A1. Refactor `orchestrator.run_ask`.** Remove the `plan_request` and
      `run_responder` calls. New flow: call `run_agent(question, history)` →
      `PublicHealthResponse`; if `statistics` is non-empty → `mode="artifact"`
      (payload = the response); else → `mode="chat"`, `chat_message = summary`.
      Keep the existing graceful-degradation try/except.
      *Done when:* a test asserts `run_ask` calls `run_agent` exactly once and
      never calls `plan_request`/`run_responder`.
- [x] **A2. Add the named heuristic helper** `_is_report_worthy(resp)` (statistics
      non-empty) with its own unit test. Built to be swapped for a planner later.
- [x] **A3. Park planner + responder.** Leave `planner.py`, `responder.py`, and
      the `Plan` schema in place but unwired from `run_ask`. Add a one-line
      module docstring note: "Deferred per ARCHITECTURE.md §3a — not on the
      request path yet."
- [x] **A4. Update tests.** `test_orchestrator.py`: rich payload → artifact; thin
      payload → chat; reporter raises → graceful chat. Mock `run_agent` (no real
      LLM). Keep planner/responder unit tests green as parked units.
- [x] **A5. Green + offline check.** Full suite green; default run makes no
      network call. Update this file, commit.

---

## Phase B — Server HTTP layer (AFTER Phase A)

Order: 1–3 make it work; 4–6 make it safe. TDD throughout. This is the deferred
`/ask` session from CLAUDE.md rule 4.

- [x] **B0. conftest auth fixture FIRST** (CLAUDE.md known concern). Add an
      autouse fixture overriding `clerk_guard` via `app.dependency_overrides`
      before adding any guarded route.
- [x] **B1. `POST /ask`.** Add `AskRequest` model (question + optional
      `message_history`). Handler: `await run_ask(...)` → return `AskResponse`.
      `Depends(clerk_guard)`.
- [x] **B2. `GET /measures`.** Wrap `get_available_measures()`; return structured
      JSON (not the formatted string). `Depends(clerk_guard)`.
- [x] **B3. Apply auth + real config.** `Depends(clerk_guard)` on `/ask` +
      `/measures`; `/health` stays public; set real `CLERK_JWKS_URL`.
- [x] ~~**B4. Rate limiting.**~~ **DEFERRED to hardening.** The Anthropic spend
      cap (set in Console → Workspaces → Limits) is the real bill backstop; with
      `/ask` Clerk-gated and traffic near zero, an app-level limiter buys little
      now. Leave a `# TODO: rate limit — see hardening` comment on `/ask`.
- [x] **B5. Fail-fast startup validation.** Call `validate_model_config()` in a
      FastAPI lifespan hook; assert `data/` files exist. Bad config fails at boot.
- [x] **B6. HTTP tests.** `/ask` happy path (mock `run_ask`), `/ask` 401 without
      token, `/measures`. (Rate-limit test dropped with B4.)

---

## Phase C — Run locally (verify before deploy)

- [x] **C1. Boot + smoke.** `uvicorn server:app` starts clean; `GET /health` →
      200. Document the exact run command in README.
- [x] **C2. Live API check.** With real `ANTHROPIC_API_KEY` + Clerk env set, hit
      `/ask` and `/measures` with a valid token (curl/httpx) and confirm a real
      `AskResponse` and the measures JSON come back. This is the first real
      end-to-end LLM call — confirms the contract holds against a live model.

## Pre-D fixes (clear before Docker build)

- [x] **PD1. chromadb missing → MMWR retrieval silently off.** Verify `chromadb`
      is in `requirements.txt` at the right version; reinstall cleanly in the
      venv; re-run an MMWR-flavored question to confirm `search_mmwr_reports`
      actually returns passages (not the "vector DB not available" fallback).
- [x] **PD2. `meta.tools_used` always `[]`.** Populate it from the agent run
      result (tool-call parts) so production telemetry is accurate. The parked
      `# TODO: populate from agent result` in orchestrator.py.

## Phase D — Deploy to Railway

- [x] **D1. Dockerfile.railway builds locally** with `data/` baked in (db +
      chroma); image runs and serves `/health`.
- [ ] **D2. Railway service** created; env vars set (`ANTHROPIC_API_KEY`,
      `CLERK_JWKS_URL`, `PUBHEALTH_MODEL`, any Clerk secret); deploy succeeds.
- [ ] **D3. Live verification** — `/health`, then authed `/ask` + `/measures`
      against the Railway URL.
- [ ] **D4. CONFIRM Anthropic spend cap is set** before sharing the URL
      (prerequisite for the deferred B4).

---

## Deploy-time hardening (not blocking a working API)

- [ ] **Rate limit `/ask`** (deferred B4) — prereq: confirm Anthropic spend cap
      is set. Add `slowapi`, per-user key, env-configurable limit.
- [ ] Narrow CORS `allow_headers` to `["Authorization", "Content-Type"]`.
- [ ] Real frontend origins in CORS allow-list.
- [ ] Secrets in Railway env (`ANTHROPIC_API_KEY`, Clerk keys).

---

## Session log (newest first)

- 2026-06-07 — Phase D1 complete. Dockerfile.railway: added all-MiniLM-L6-v2 model
  pre-bake layer (offline at boot), $PORT support, JSON CMD form. Created .dockerignore
  (excludes .venv 1.5GB, __pycache__, .env, scripts/; keeps data/). Image 3.32GB,
  build 2:41. Boot: startup validation passed (validate_model_config + healthgpt.db +
  chroma_db is_dir + check_vector_store all green). GET /health → 200.
- 2026-06-07 — Pre-D PD2 complete. agent.py: AgentResult dataclass + _extract_tools_used()
  iterates new_messages(), collects ToolCallPart.tool_name, excludes _output_tool_name
  ("final_result"), dedupes preserving order. run_agent returns AgentResult. orchestrator:
  unpacks agent_result.response + agent_result.tools_used; Meta.tools_used populated for
  both artifact and chat paths. New test file test_agent_tools_extraction.py (3 tests);
  test_orchestrator.py 11→13. All callers updated (smoke + integration tests). 25 green.
- 2026-06-07 — Pre-D PD1 complete. chromadb==1.5.8 was in requirements.txt but
  uninstalled (venv out of sync); sentence-transformers also missing — both now
  installed. tools.py: check_vector_store() added (fails-fast on None or count=0).
  server.py lifespan: step 3 calls check_vector_store(). test_startup.py: 4→6 tests.
  Live verify: search_mmwr_reports returns real passages (source PDFs, relevance
  scores) for COVID vaccination queries. 41 tests green.
- 2026-06-07 — Phase C2 complete. scripts/demo_run_ask.py: 3 live calls, all
  correct modes. Greeting → chat. Travis County diabetes → artifact, 2 CDC PLACES
  stats (9.0% crude, 9.5% age-adj). Cook/Harris obesity → artifact, 4 stats.
  SQLite tools fired; real data confirmed. Two findings: (1) meta.tools_used always
  [] (tracking gap, not data gap); (2) chromadb not installed in venv — MMWR
  degrades silently. Verify Docker image installs chromadb before Railway deploy.
- 2026-06-07 — Phase C1 complete. uvicorn server:app --reload --port 8000 boots
  clean; lifespan passed (validate_model_config OK, healthgpt.db + chroma_db found);
  GET /health → 200 {"status":"ok","version":"0.1.0","data":{...}}. README updated
  with exact run command and lifespan note.
- 2026-06-07 — Phase B6 complete. test_ask.py: +2 artifact-mode tests asserting
  mode/artifact shape differs between chat and artifact envelopes. test_auth.py:
  +2 _get_clerk_bearer tests using monkeypatch (no manual try/finally); removed
  fragile clerk_guard unit test and _reset_clerk_singleton helper. server.py 98%
  coverage (1 miss: clerk_guard body, unreachable without real Clerk). 39 tests green.
- 2026-06-06 — Phase B5 complete. lifespan handler in server.py: validate_model_config()
  first, then is_dir() check on chroma_db (not just exists()), then exists() on healthgpt.db.
  test_startup.py: 4 tests (success, model-failure, db-failure, chroma-failure). Quality
  fixes: chroma check is_dir(), model-failure test tightened to ValueError only, stale B5
  comment removed from _get_clerk_bearer, chroma branch covered by new test. 35 tests green.
- 2026-06-05 — Phase B3 complete. test_auth.py: 4 tests covering /health public,
  /ask + /measures require auth (401/403 via no_auth fixture). server.py: lazy
  Clerk init with env-driven CLERK_JWKS_URL; accurate comment on empty-URL 500
  behavior; neutral warning text. Duplicate health test removed. All tests green.
- 2026-06-05 — Phase B2 complete. GET /measures returns structured JSON;
  list_available_measures() added to tools.py; MeasureItem model in
  schemas.py. 11 new tests, all green offline.
- 2026-06-05 — Phase B1 complete. POST /ask wired to run_ask; AskRequest
  added to schemas.py; conftest autouse handles auth. 11 new tests, all
  green offline.
- 2026-06-05 — Phase B0 complete. clerk_guard lazy-init in server.py;
  autouse override_clerk_guard fixture in conftest.py; fragile ClerkHTTPBearer
  patch removed from test_health.py. Suite green and offline.
- 2026-06-05 — Phase A complete. run_ask makes one LLM call; mode derived
  from payload heuristic (_is_report_worthy). planner.py + responder.py
  parked (not deleted). All tests green offline.
- 2026-06-05 — Created this tracker. Phase A not yet started. Engine + envelope
  schemas + config already built and tested; `server.py` has `/health` only.
