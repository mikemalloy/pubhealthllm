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

**You are here →** Phase B, item B3 (not started).

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
- [ ] **B3. Apply auth + real config.** `Depends(clerk_guard)` on `/ask` +
      `/measures`; `/health` stays public; set real `CLERK_JWKS_URL`.
- [ ] **B4. Rate limiting.** Add `slowapi` (not in requirements yet); per-user/IP
      limit on `/ask`.
- [ ] **B5. Fail-fast startup validation.** Call `validate_model_config()` in a
      FastAPI lifespan hook; assert `data/` files exist. Bad config fails at boot.
- [ ] **B6. HTTP tests.** `/ask` happy path (mock `run_ask`), `/ask` 401 without
      token, `/measures`, rate-limit behavior.

---

## Deploy-time hardening (not blocking a working API)

- [ ] Narrow CORS `allow_headers` to `["Authorization", "Content-Type"]`.
- [ ] Real frontend origins in CORS allow-list.
- [ ] Secrets in Railway env (`ANTHROPIC_API_KEY`, Clerk keys).

---

## Session log (newest first)

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
