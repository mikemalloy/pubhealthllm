# Multi-agent (lean) implementation — Claude Code prompts

Paste these into Claude Code **one at a time, in order**. Wait for green between
each. Assumes the repo conventions in `CLAUDE.md`.

## What changed from the first draft (and why)
The earlier version pre-committed to seven artifact types (table, comparison,
ranking, choropleth_map, mortality, decision_tree) and an always-on planner LLM.
That predicts user demand we can't see yet. Cut it down:

- **Two modes only: `chat` and `artifact`.** `PublicHealthResponse` is already
  general enough to be every data answer — a single stat, a comparison, and a
  ranking are all just different row counts in `statistics`. "Map" / "bar chart"
  are *render choices the frontend makes*, not contract types.
- **No planner LLM on day one.** The existing agent already returns
  `PublicHealthResponse`. Derive the mode from the payload: rich (has statistics)
  → artifact; thin (summary only) → chat. No second model call, no added latency.
- **Keep the envelope** — it's a cheap, stable wrapper that lets us add modes
  later without breaking the frontend.

The planner becomes worth building only when (a) we add the decision-tree mode —
a genuinely different capability needing different elicitation — or (b) we
measure that running the full 8-tool agent on "hi" is too slow/expensive. Until
then, payload-based routing is enough.

## Ground rules baked into every prompt
- **TDD always.** Failing test first, then minimum code, then refactor.
- **Superpowers.** Invoke the named skill at the top of each prompt.
- **Scope guard.** This builds a pure, importable module. It does **NOT** add the
  `/ask` route, does **NOT** edit `server.py`, and does **NOT** touch `frontend/`.
  The HTTP layer is a later session (CLAUDE.md rule 4).

---

## Prompt 0 — Plan the work

```
Invoke the Superpowers `writing-plans` skill.

Read CLAUDE.md and the existing backend/pubhealth_llm/app/agent.py, tools.py, and
schemas.py.

Produce a written plan (in docs/plans/) for a LEAN multi-agent response layer as
a pure Python module — no HTTP route, no server.py edits, no frontend, NO planner
LLM. The design:

- A response envelope: { mode, chat_message, artifact?, meta } where mode is
  "chat" or "artifact".
- An orchestrator run_ask(question, message_history) that:
    1. calls the EXISTING reporter agent.run_agent -> PublicHealthResponse,
    2. inspects the result: if it carries statistics it's a report
       (mode="artifact", payload = the PublicHealthResponse); if it's thin
       (summary only, no statistics) it's conversational (mode="chat",
       chat_message = the summary),
    3. assembles and returns the envelope.

No separate planner.py and no responder.py — one agent, two presentations chosen
by a cheap payload heuristic. The plan must note exactly where a future planner
LLM would slot in (replace the heuristic) so we don't paint ourselves in.

Stop after the plan. No production code yet.
```

---

## Prompt 1 — Envelope schemas (TDD)

```
Invoke the Superpowers `subagent-driven-development` skill. TDD: red → green →
refactor.

Add the response-envelope types to backend/pubhealth_llm/app/schemas.py. Do NOT
modify PublicHealthResponse — only add.

Write tests FIRST (tests/test_envelope_schemas.py), then implement:

- Artifact:
    type: Literal["report"]        # one member for now; add more only when a
                                   # real new payload shape exists
    title: str
    payload: dict                  # a PublicHealthResponse dump
- Meta:
    intent: str = ""
    tools_used: list[str] = []
    model: str = ""
    timing_ms: int = 0
- AskResponse (the envelope):
    mode: Literal["chat", "artifact"]
    chat_message: str              # always present
    artifact: Optional[Artifact] = None   # present only when mode == "artifact"
    meta: Meta = Meta()

Add a model validator: mode == "artifact" requires artifact is not None;
mode == "chat" requires artifact is None. Cover both failures in tests. Keep all
existing tests green.
```

---

## Prompt 2 — Orchestrator (TDD, mock the reporter)

```
Invoke the Superpowers `subagent-driven-development` skill. TDD throughout.

Create backend/pubhealth_llm/app/orchestrator.py:

    async def run_ask(question: str, message_history=None) -> AskResponse

Flow:
1. Time the call. result = await agent.run_agent(question, message_history)
   -> PublicHealthResponse.
2. Decide the mode with a small, named helper, e.g. _is_report_worthy(resp):
   return True if resp.statistics is non-empty. (Document it as a deliberately
   trivial heuristic that a future planner LLM will replace.)
3. If report-worthy:
     mode="artifact"
     artifact = Artifact(type="report", title=<first line / short summary>,
                         payload=resp.model_dump())
     chat_message = a one-liner pointing at the report
       (e.g. "Opened a report on the right.")
   Else:
     mode="chat"
     chat_message = resp.summary
     artifact = None
4. Fill meta: model used, timing_ms, tools_used if the result exposes them
   (else []), intent = "report" or "chat".

Resilience: if agent.run_agent raises, do NOT propagate. Return a valid chat
AskResponse with an apologetic chat_message. Add a test forcing the exception.

Tests must mock agent.run_agent — no real LLM, no DB:
- reporter returns a PublicHealthResponse WITH statistics -> mode="artifact",
  payload equals the mocked dump, envelope validates.
- reporter returns a thin PublicHealthResponse (no statistics) -> mode="chat",
  chat_message == summary, artifact is None.
- reporter raises -> graceful chat AskResponse, run_ask does not raise.

Do NOT add an /ask route. Do NOT import or edit server.py. Do NOT touch frontend/.
```

---

## Prompt 3 — Verification pass

```
Invoke the Superpowers `systematic-debugging` skill only if something is red.

1. Run the full pytest suite; everything green, including the original v1 tests.
2. Report coverage for orchestrator.py and the new envelope schema types. Aim
   >= 90%; add tests for any uncovered branch.
3. Write scripts/demo_run_ask.py (NOT a test, NOT a route) that calls run_ask()
   on three example inputs — a greeting ("what can you do?"), a county data
   question, and a comparison — printing each AskResponse as indented JSON. This
   is the "test the surface before UI" check at the function level.
4. Confirm and list: no /ask route added, server.py untouched, frontend/
   untouched. List every file created or modified.
```

---

## After these land
- The `/ask` HTTP route (next session): a thin wrapper calling run_ask() behind
  `Depends(clerk_guard)` with rate limiting, returning the AskResponse as JSON.
- Add a planner LLM only when the decision-tree mode arrives, or when metrics
  show the full agent is too costly on trivial inputs. It replaces
  `_is_report_worthy` — the envelope and frontend don't change.
- New artifact `type` members (e.g. choropleth, decision_tree) get added only
  when a genuinely different payload shape exists, driven by logged real usage.
