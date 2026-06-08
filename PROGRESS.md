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

**You are here →** Phase F, item F2 (wire to backend `/ask`). E1–E8 done; E9
(Vercel deploy) still open — can finish in parallel. Backend is DONE (Railway,
auth, live `/ask`). Path: F2 (wire to `/ask`).
F1 is done — UI only, no data. F2 wires the real backend.

⚠️ **Open perf finding (P1):** live `/ask` took ~29s in prod. Diagnose cold-start
vs agentic-loop (two consecutive calls); if it's the loop, address with SSE
streaming (perceived latency) during the UI phase. Tracked in "Perf / hardening".

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
- [x] **D2. Railway service** created; env vars set (`ANTHROPIC_API_KEY`,
      `CLERK_JWKS_URL`, `PUBHEALTH_MODEL`, any Clerk secret); deploy succeeds.
- [x] **D3. Live verification** — `/health`, then authed `/ask` + `/measures`
      against the Railway URL.
- [x] **D4. Anthropic spend cap set.** Confirmed by Mike before sharing the URL.

**Backend complete.** Live at https://pubhealthllm-production.up.railway.app

---

## Phase E — Frontend (UI framework only; NO pubHealth data yet)

Built in `frontend/` from the shadcn template at
`/Volumes/Hub/dev/ui-templates/shadcn` (read-only). Decisions locked:
copy-and-strip the template; real Clerk on the SAME instance as the backend;
navbar "Dashboard" → public Home (chart demos dropped); sidebar user = Clerk,
navbar avatar stays a static placeholder. Verification = `pnpm build` + lint +
manual smoke (no pytest on the frontend). Placeholders use the template's panel
style: `bg-primary-foreground p-4 rounded-lg`.

- [x] **E1. Copy + baseline boot.** Copy the template into `frontend/` (replace
      the placeholder). Remove the template's own `.git`/workspace artifacts,
      rename in `package.json`. `pnpm install && pnpm dev` renders the template
      unchanged. Commit a known-good baseline BEFORE modifying.
- [x] **E2. Strip + rebrand the sidebar.** Header label → "PubHealth". Keep ONLY
      the Application group; delete Projects, Collapsible Group, Nested Items.
      Application items become: Home (`/`, home icon) and "Pub Health LLM"
      (`/llm`, `message-square` lucide icon). Keep `collapsible="icon"` + the
      footer user slot + the `SidebarTrigger` hide behavior.
### di4health pivot (decided after E2)

The Home page becomes a polished landing page for **Decision Intelligence 4
Health (di4health)** — content adapted from https://di4health.github.io (a
project of TEAM Public Health / Tomás Aragón). Decisions locked:
**(1) Rebrand the app to di4health** (brand strings, titles — frontend only, NOT
the backend). **(2) Sidebar:** apply `variant="inset"` to the current sidebar for
the floating-card shell + adopt sidebar-07's `nav-user` as the Clerk user block;
do NOT swap the whole sidebar-07 (revisit only if nav grows nested).
**(3) Content:** tighten di4health's text into landing-page copy — keep every idea
and the full framework, cut word count. **(4) Figures:** hybrid — recreate the
rule-of-4 grids as native theme-aware cards; reuse the complex competence/
complexity + framework PNGs as re-hosted, framed, theme-swapped images. Keep
clear attribution to di4health / TEAM Public Health throughout.

- [x] **E3. Rebrand shell → di4health.** Sidebar brand "PubHealth" → "di4health";
      `<title>`/metadata; any user-facing app name. Keep nav items (Home, Pub
      Health LLM). Mechanical pass; build stays green. (Frontend only — backend
      untouched per CLAUDE.md rule 4.)
- [x] **E4. Inset shell.** Add `variant="inset"` to the sidebar + wrap content in
      `<SidebarInset>`; replace the plain Navbar with the inset header pattern
      (SidebarTrigger + breadcrumb left; Dashboard link + theme toggle + static
      avatar right). Confirm the floating rounded-card look + theme + collapse.
- [x] **E5a. Home — shell, hero, copy.** Public Home `/`: hero (headline,
      mission subhead, Annie Duke quote as a styled callout, primary CTA →
      `/llm`), the "why decision quality / complexity" band, resources row
      (Coding examples, DARTH, TEAM Public Health substack with Julia/Python/R
      badges), footer with attribution + Annie Duke citations. Tightened copy,
      native panels. Remove leftover chart-demo components.
- [x] **E5b. Home — framework centerpiece.** The "rule of 4s" as native, theme-
      aware visuals: 4 **DEEP** challenge cards (D/E/E/P typographic accents +
      lucide icon + mapped constraint), plus a Tabs explorer across the four
      pillars (DEEP challenges, constraints, dimensions, competency domains).
- [x] **E6. Figures (hybrid assets).** Re-host the two complex PNGs
      (competence-vs-complexity; di4health framework diagram — has light/dark
      variants) into `public/`; render in framed containers with theme-aware
      swapping. Native rule-of-4 grids already done in E5b.
- [x] **E7a. Clerk core + gated `/llm`.** Add `@clerk/nextjs`; `<ClerkProvider>`
      wrapping the app in layout.tsx; `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` +
      `CLERK_SECRET_KEY` from the SAME Clerk instance as the backend's
      `CLERK_JWKS_URL` in `.env.local` (gitignored); `.env.example` documents them
      with placeholders (no real values committed). `middleware.ts`
      (`clerkMiddleware` + `createRouteMatcher`) protects `/llm`; Home stays
      public. `/llm` = simple auth-gated placeholder panel in the inset content.
- [x] **E7b. Sidebar `nav-user` (Clerk).** Replace the footer user slot with a
      sidebar-07-style `nav-user`: `<SignedIn>` → user block from `useUser`
      (name/email/avatar) + up-arrow dropdown wired to `openUserProfile()` /
      `signOut()`; `<SignedOut>` → "Sign in" (`SignInButton`). Navbar avatar stays
      a static placeholder.
- [x] **E8. Verify.** `pnpm build` + lint clean; manual smoke: Home public with
      di4health content + inset shell; `/llm` redirects logged-out, renders
      logged-in; theme + collapse work. Screenshot.
- [ ] **E9. Deploy to Vercel.** Project root directory = `frontend`; set Clerk
      env vars; deploy; verify live (Home public, `/llm` gated). Add the Vercel
      origin to the backend CORS allow-list (hardening item).

---

## Phase F — Pub Health LLM page (the `/llm` UI, then wire it up)

Keep the inset shell + di4health styling. Decisions locked: multi-turn
conversation thread (left); draggable splitter that can also collapse the chat so
the artifact goes full-width; the right artifact panel always renders the LATEST
report as markdown (chat-only replies stay in the left thread; welcome+examples
show until the first report); copy-to-clipboard icon on the artifact. Two tasks:

- [x] **F1. Page UI (no backend).** Two-panel resizable layout via shadcn
      `resizable` (react-resizable-panels): left ~1/3 chat thread with input
      pinned at the bottom; right ~2/3 artifact panel. Artifact renders markdown
      (`react-markdown` + `remark-gfm`, Tailwind `prose`) with a copy-to-clipboard
      icon. Chat panel collapsible; divider draggable. On fresh load the artifact
      shows the welcome (what it can do now + future) and 2–3 clickable example
      prompts (copy drafted in the F1 prompt). Use local/mock state — input
      doesn't call the backend yet; render a sample report to prove markdown
      formatting. Stays Clerk-gated (from E7a).
- [ ] **F2. Wire to backend `/ask`.** Call the Railway `/ask` with the Clerk
      token (`useAuth().getToken()` → `Authorization: Bearer`). Map the
      `AskResponse` envelope: `chat_message` → left thread; `artifact` (report)
      → right panel as markdown; chat-only → left only (right keeps last/welcome).
      Pass `message_history` for multi-turn. Solid loading/"thinking" state for
      the ~29s latency; error handling. Decide the markdown source (surface the
      backend's `PublicHealthResponse.to_markdown()` in the artifact vs build it
      client-side). Add the frontend origins (localhost + Vercel) to the backend
      CORS allow-list + redeploy Railway (this is the deferred CORS item; the one
      sanctioned backend touch). SSE streaming stays P1.

---

## Perf / hardening (not blocking)

- [ ] **P1. `/ask` ~29s in prod.** Diagnose cold-start vs agentic loop (two
      consecutive calls). If loop → SSE streaming for perceived latency (parked
      in §3a); secondary: faster-model routing for simple Qs, result caching,
      keep-warm to avoid cold start.
- [ ] **Rate limit `/ask`** (deferred B4) — prereq met (spend cap set). Add
      `slowapi`, per-user key, env-configurable limit.
- [ ] Narrow CORS `allow_headers` to `["Authorization", "Content-Type"]`.
- [ ] Real frontend origins in CORS allow-list (do during Phase E).
- [ ] Secrets in Railway env (`ANTHROPIC_API_KEY`, Clerk keys).

---

## Session log (newest first)

- 2026-06-08 — Phase E5a complete. page.tsx replaced: hero (badge, H1,
  subhead, Annie Duke blockquote, 2 CTAs), why-decision-quality band
  (placeholder for E6 figure), framework anchor (placeholder for E5b),
  resources (3 cards: Coding examples/DARTH/TEAM PH with badges), footer
  (attribution + Annie Duke citations). Deleted 6 demo components
  (AppBarChart, AppAreaChart, AppLineChart, AppPieChart, CardList, TodoList).
  Home bundle: 138kB → 485B. pnpm build clean, no warnings.
- 2026-06-08 — Phase F1 complete. LlmChat.tsx ("use client"): ResizablePanelGroup
  (orientation="horizontal", react-resizable-panels v4 API) — left 33% chat +
  right 67% artifact. Chat: scrollable message bubbles (user/assistant styling),
  3 example-prompt chips on empty state (fill input on click), Textarea + Send
  pinned at bottom, Enter-to-send. Artifact: header with Copy icon (clipboard +
  2s "copied" state), react-markdown + remark-gfm in prose/dark:prose-invert div.
  Chat panel collapsible via panelRef imperative handle (collapse/expand) + toggle
  button. Welcome markdown on fresh load; sample report (heading, GFM table,
  sources, disclaimer) on first submit. v4 API fixes: orientation not direction,
  panelRef not ref, onResize not onCollapse/onExpand. @tailwindcss/typography
  registered via @plugin in globals.css. pnpm build clean, /llm 58kB.
- 2026-06-08 — Phase E8 complete. Mechanical: pnpm build ✅ lint ✅ tsc ✅.
  Cleanup: deleted 11 unused shadcn primitives (calendar, chart, checkbox,
  form, hover-card, label, popover, progress, scroll-area, select, table);
  removed 7 orphaned deps (@hookform/resolvers, @tanstack/react-table,
  date-fns, react-day-picker, react-hook-form, recharts, zod). Build still
  clean, 3 routes, 88kB middleware. Visual smoke (manual — no browser
  automation): HOME/DEEP-tabs/figures/resources/footer, /llm auth gate,
  sidebar nav-user, collapse, theme toggle, mobile layout — PENDING user
  confirmation.
- 2026-06-08 — Phase E7b complete. NavUser.tsx ("use client"): useUser() for
  conditional render (avoids SignedIn/SignedOut — removed in Clerk v7 client
  exports); isLoaded guard prevents flicker. Signed-in: Avatar (imageUrl +
  initials fallback) + name/email + ChevronsUpDown trigger; DropdownMenu opens
  right (bottom on mobile) with header row + "Manage account" (openUserProfile)
  + "Sign out" (signOut). Signed-out: SignInButton mode="modal" with LogIn icon.
  AppSidebar: old User2/ChevronUp/DropdownMenu block → <NavUser />. pnpm build
  clean, bundle unchanged.
- 2026-06-08 — Phase E7a complete. @clerk/nextjs 7.4.3 installed. .env.local
  created (gitignored under .env*). .env.example added with placeholder keys.
  ClerkProvider added as outermost provider in layout.tsx. src/middleware.ts:
  clerkMiddleware + createRouteMatcher(['/llm(.*)']) + auth.protect(). /llm
  page: server component with auth() + placeholder panel. pnpm build clean,
  3 routes + 88kB middleware. Clerk dev-browser handshake confirmed in curl
  headers (x-clerk-auth-reason: protect-rewrite) — real redirect tested in browser.
- 2026-06-08 — Phase E6 complete. Downloaded di_decision_competence_complexity.png
  (1.1MB) and di4health_dq_light.png (3.1MB) to frontend/public/img/. Dark variant
  404'd — deleted, light-frame approach used for both (bg-white panel stays white in
  both themes). Figure 1 in "why decision quality" band; Figure 2 above FrameworkTabs
  in #framework section. next/image with width/height dims. pnpm build clean.
- 2026-06-08 — Phase E5b complete. FrameworkTabs.tsx: shadcn Tabs (4 tabs).
  Tab 1 DEEP: 4 cards with large D/E/E/P letter accents, lucide icons,
  constraint badges (Information/Values/Time/Resources), one-liners. Tabs
  2-4 use SimpleCard with icon+title+blurb: Constraints (4), Dimensions (4,
  with execution framework note), Competencies (4, Alliance for Decision
  Education). Responsive 1→2→4 col grid. page.tsx E5b placeholder → 
  <FrameworkTabs />. pnpm build clean, Home 485B → 10.6kB.
- 2026-06-08 — Phase E4 complete. AppSidebar: variant prop added, passed
  "inset" from layout.tsx. Navbar.tsx replaced by SiteHeader.tsx: left =
  SidebarTrigger + Separator + Breadcrumb (di4health / page); right =
  Dashboard link + theme toggle + static avatar (unchanged behavior).
  layout.tsx: body flex removed, <main> → <SidebarInset>, Navbar →
  SiteHeader. pnpm build clean, 2 routes.
- 2026-06-08 — Phase E3 complete. AppSidebar brand "PubHealth" → "di4health";
  layout.tsx metadata title → "di4health — Decision Intelligence 4 Health",
  description updated. No other user-facing brand strings found. pnpm build
  clean, no warnings.
- 2026-06-07 — Phase E2 complete. AppSidebar.tsx rewritten: brand "Lama Dev"
  → "PubHealth" (logo.svg kept), Application group trimmed to Home (/) +
  Pub Health LLM (/llm, MessageSquare icon), Projects/Collapsible/Nested
  groups deleted, SidebarFooter "John Doe" kept as-is. Deleted demo routes
  (payments/, users/) + EditUser.tsx + TablePagination.tsx (only used by
  those routes). pnpm build clean, 2 routes (/ + /_not-found), no warnings.
- 2026-06-07 — Phase E1 complete. Copied shadcn template into frontend/
  (excluded node_modules, .next, .git, pnpm-workspace.yaml). Renamed
  package.json "name" to "pubhealth-frontend". Added .npmrc with
  `only-built-dependencies[]=sharp` + `onlyBuiltDependencies` to lockfile
  settings; used `--ignore-scripts` for pnpm install (sharp native optional).
  Fixed 3 template lint errors (unused vars in EditUser.tsx + Navbar.tsx —
  leftover from commented-out code in original template). pnpm dev → 200 at
  localhost:3000, title "ShadCN Tutorial", Ready in 856ms. pnpm build → clean,
  7 static pages, no warnings.

- 2026-06-07 — Phase D3 complete. scripts/verify_railway.py created (Clerk
  backend SDK: list users → create session → mint JWT → call Railway).
  Part 1 (unauth): /health → 200, /ask → 403, /measures → 403. Part 2
  (authed, mike.malloy.2004@gmail.com): GET /measures → 200 (39 measures),
  POST /ask → 200 mode=artifact, tools_used=[tool_get_health_statistics,
  tool_search_mmwr_reports], Travis County diabetes 9.0% crude/9.5%
  age-adj (CDC PLACES 2023). Full contract confirmed on Railway.
- 2026-06-07 — Phase D2 complete. Railway deploy succeeded at
  https://pubhealthllm-production.up.railway.app — GET /health → 200
  {"status":"ok","version":"0.1.0"}. Root cause of crash was LFS pointer
  files baked instead of real data (Railway clones without LFS fetch).
  Fix: removed all data/* from LFS tracking (.gitattributes cleared),
  re-committed as regular git objects (healthgpt.db 69MB, chroma_db 3MB,
  mmwr_pdfs 3.5MB — all under GitHub 100MB hard limit).
- 2026-06-07 — Phase D2 (partial): railway.json added (builder=DOCKERFILE,
  dockerfilePath=Dockerfile.railway). LFS confirmed: healthgpt.db, chroma_db
  (4 files), mmwr_pdfs (9 PDFs) — all real objects (* marker, not pointers).
  D2 checkbox stays open until Railway deploy succeeds.
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
