---
spec_id: 01-explore-author-planning
status: DRAFT
since: 2026-06-14
until: null
epic: testing
features: [explore-planning-prompt, author-planning-prompt]
supersedes: []
superseded_by: null
depends_on: []
related: [picobay/specs/11-explore-planning]
---

# Explore / Author Planning via `write_todos` (prompt-only)

<!-- DRAFT — not yet implemented. Frontmatter is the source of truth for
     status. Mirror of picobay spec 11, taking the cheaper prompt-only path
     because the planning tool is already present here. -->

## Context

Both authoring agents are built with deepagents `create_deep_agent`:

- **Explore** agent — `build_explore_agent` path
  [src:src/aitester_bdd/authoring/agent_loop.py:425]. Terminal tools
  `journey_complete` / `journey_blocked`
  [src:src/aitester_bdd/authoring/tools.py:145]. Two browser backends:
  in-RF Playwright (`PLAYWRIGHT_EXPLORE_PROMPT`
  [src:src/aitester_bdd/authoring/playwright_tools.py:283]) and standalone
  agent-browser CLI (`_EXPLORE_SYSTEM_PROMPT`
  [src:src/aitester_bdd/authoring/agent_loop.py:42]).
- **Author** agent — `_author_once`
  [src:src/aitester_bdd/authoring/agent_loop.py:252]. Terminal tools
  `write_robot_suite` / `report_bug`. Prompt from `build_system_prompt`
  [src:src/aitester_bdd/authoring/agent_loop.py:114].

**The planning tool already exists and is active.** The installed deepagents
is **0.6.1** (pyproject pins `>=0.0.15`). Its default middleware stack
unconditionally includes `langchain.agents.middleware.TodoListMiddleware`,
which (a) registers the `write_todos` tool and (b) appends its own
~118-line usage prompt (`WRITE_TODOS_SYSTEM_PROMPT`) to the system message
at call time. So both agents *can* plan today — they are simply never given
**domain-specific** planning guidance. The only discipline currently in our
prompts is the `step_count` instruction ("you MUST perform ALL N steps before
journey_complete") in the explore user message.

picobay validated first-class planning on the TS engine (spec 11,
`update_plan`): on sonnet, ~34% faster, ~26% fewer browser calls, equal 100%
success. The measured win came from a **single upfront commitment**
(`planEvents=1, stalled=false` in every trial), *not* from iterative
re-planning or the stalled-step loop-break. `write_todos` already produces
exactly that upfront-commitment behavior, so we take the prompt-only path
here rather than porting a new tool.

## What `write_todos` does (and does not do)

Schema is fixed by langchain and **cannot be subclassed cheaply**:

```
write_todos(todos: list[{ content: str, status: "pending"|"in_progress"|"completed" }])
```

State persists in graph `PlanningState["todos"]`, readable post-run as
`result["todos"]`. Injected behavior: mark `in_progress` before acting,
`completed` only when fully done, keep ≥1 `in_progress`, and **on a blocker
keep the task `in_progress`**.

Gap vs picobay `update_plan`: no `goalUnderstanding`, no `notes`, and
**no `stalled` status**. The "keep in_progress on blocker" rule is the
*opposite* of "mark stalled → switch strategy". Therefore the failing-strategy
discipline and any goal restatement must live in **our** prompt text, not in
the tool.

## Decision

Option **A (prompt-only)**. No new tool, no schema. Add domain-specific
planning guidance to the explore and author prompts; surface the resulting
todos to the RF log; gate behind a kill-switch. Spec-first per EP6.

## Design

### D1 — Explore planning prompt block
Add to both `_EXPLORE_SYSTEM_PROMPT` and `PLAYWRIGHT_EXPLORE_PROMPT` (behind
the D4 flag): instruct the agent to **call `write_todos` first**, decomposing
the story into one todo per step; mark a step `in_progress` before acting and
`completed` after the verification for that step passes. Because there is no
`stalled` status, encode the switch-strategy discipline explicitly:

> If a step's strategy fails twice (selector not found, action no-ops),
> **rewrite that todo's content** with a different approach (broader selector,
> different attribute, re-snapshot) before retrying — do not repeat the same
> failing move.

The existing `step_count` guard stays; the todo list makes "did I do all N
steps?" self-enforcing rather than prompt-asserted.

### D2 — Author planning prompt block
Add to `build_system_prompt` (behind the flag): plan rule emission as todos,
and per step decide **PIN** (stable selector traced to an observed attribute)
vs **FLUID** (`I explore` line) — the pin/fluid judgment picobay surfaces.
`write_todos` does not model this; the prompt must state it. Honor the existing
`pinning` parameter (the plan must respect `pinning=pinned|fluid|auto`).

### D3 — Observability (EP4)
After each agent loop, read final `result["todos"]` and emit it to the RF log
on the explore path when `notes=true` (the existing notes default), and fold
it into the bug report on `journey_blocked` / author `report_bug`. This is the
RF-log analog of picobay's `onProgress('planning', …)` trace events. No new
trace channel.

### D4 — Kill-switch (EP1)
Gate planning behind `enable_planning` (default **true**), settable via RF
variable `${ENABLE_PLANNING}` and/or env `AITESTER_PLANNING`, mirroring
picobay's `enablePlanning` resource global. When false, the agent is built
**truly planning-free**: the D1/D2 prompt blocks are dropped *and*
deepagents' always-on `TodoListMiddleware` is swapped for a no-op
`AgentMiddleware` during `create_deep_agent` (so the model sees no
`write_todos` tool and no generic todo prompt).

> **Semantics change (2026-06-15):** OFF previously meant "today's exact
> behavior" — i.e. the middleware's `write_todos` stayed active, only our
> text was dropped. That confounded the planning A/B (the OFF arm still
> planned). OFF now means **all planning off**, which is the correct meaning
> for a planning kill-switch. Implemented via a construction-time swap of
> `deepagents.graph.TodoListMiddleware` (`_maybe_disable_todo_middleware`),
> not `excluded_middleware`.

## Constraints

- **Tool is owned by deepagents/langchain** — we only prompt and read state;
  we do not subclass `WriteTodosInput` or replace the middleware.
- **EP1** — planning is flagged, default-on, kill-switchable; no inline magic.
- **EP4** — every run's plan is logged, not buried in token logs.
- **EP6** — this spec precedes the prompt edits.
- **EP7** — "did it help" is **unverified**: aitester-bdd has no A/B eval
  harness like picobay's `planning-ab.eval`. See Non-goals.

## Non-goals

- Porting picobay's full `update_plan` (its `goalUnderstanding` / `notes` /
  `stalled` / returns-prior-plan semantics). Revisit only if D1's prose
  encoding of the switch-strategy discipline proves insufficient.
- Building an A/B eval harness for aitester-bdd (separate follow-up; without
  it, the speedup is assumed-by-analogy to picobay, not measured here).

## Open questions

1. Does the in-RF Playwright path preserve `TodoListMiddleware` state in
   `result["todos"]`? Both backends call the default `create_deep_agent`
   stack, so expected yes — **verify at implementation**.
   → **RESOLVED (static):** `PlanningState.todos` is `OmitFromSchema(output=False)`
   (kept in output) and `write_todos` returns `Command(update={"todos": …})`;
   both loops already read `result["messages"]` from the same returned graph
   state, so `result["todos"]` is reachable. `_summarize_todos` guards
   missing/empty. Live-run confirmation still pending (needs LLM proxy + browser).
2. Does appending our planning block interact badly with the middleware's own
   auto-injected `WRITE_TODOS_SYSTEM_PROMPT` (duplication / contradiction)?
   Check token cost and for conflicting "when to use" guidance.
   → **OPEN:** our blocks add domain guidance (journey steps / PIN-vs-FLUID) on
   top of the generic middleware prompt; no contradiction spotted, token cost
   unmeasured. Revisit if planning runs look bloated.

## Implementation status

Code landed on `main` @ `1b3b832` (2026-06-14): env kill-switch
`AITESTER_PLANNING` (default on; RF `${ENABLE_PLANNING}` deferred —
`# TODO(spec-01)`), D1/D2 prompt blocks, D3 `result["todos"]` → RF log + notes +
bug reports. Static verification: imports, `ruff check`, 38 tests pass, disabled
path byte-identical.

**Live functional verification — PASSED (2026-06-15, `aitester author`, model
`cc/claude-sonnet-4-6` via local proxy, target en.wikipedia.org):**
- D1: agent called `write_todos` 8× and decomposed the journey
  (first todo: "Explore: open Wikipedia homepage and snapshot").
- D2: emitted a fully-PINNED rule DAG with selectors grounded in real DOM
  (`#searchInput`, `button.cdx-search-input__end-button`, `h1#firstHeading`,
  `#mw-content-text p`) + parent links.
- D3: **Open Question #1 now confirmed live** — `result["todos"]` populated at
  the author read point; `final_message` carried
  `Plan (5/5 steps completed)` with all steps `[x]`.
- `_summarize_todos` unit-checked deterministically (glyphs, counts, empty/
  non-dict guards).

**Comparative A/B — RUN 2026-06-15, NO clean win + a confound found.**
3 hard targets from the wise-rpa-bdd job corpus (the lineage aitester-bdd
descends from), each `aitester author` ON vs OFF, sonnet-4-6. Raw:
`eval-ab-2026-06-15.tsv`.

| site | arm | suite | secs | iters | write_todos |
|------|-----|-------|------|-------|-------------|
| quotes-js | ON  | yes | 158 | 35 | 4 | ON **slower** |
| quotes-js | OFF | yes | 100 | 23 | 3 | |
| oscar-films | ON  | yes | 194 | 31 | 3 | ON faster wall, more iters |
| oscar-films | OFF | yes | 235 | 25 | 3 | |
| hockey-teams | ON  | no (timeout 360s) | — | 16 | 3 | both FAIL |
| hockey-teams | OFF | no (timeout 360s) | — | 22 | 2 | |

Findings:
1. **No replication of picobay's +34%.** Directionally mixed-to-negative:
   quotes-js was *worse* with our block (+58s, +12 iters); oscar-films faster
   wall but more iters; hockey-teams (form pagination) failed both arms.
2. **The A/B is CONFOUNDED — the OFF arm still plans.** `write_todos` fired
   2–3× even with `AITESTER_PLANNING=0`. Root cause: D4 only omits *our prompt
   block*; deepagents' `TodoListMiddleware` (the `write_todos` tool **and** its
   own generic todo prompt) is in the default `create_deep_agent` stack and is
   always on. So this measured "domain-specific block vs generic-middleware
   default", NOT "planning vs no planning".
3. **D4 is therefore an incomplete kill-switch — a real defect.** A true
   off-switch must exclude `TodoListMiddleware` from the stack (deepagents
   `excluded_middleware`), not just drop our text.
4. **Implication for the spec's premise.** The base agent already plans via
   middleware; D1/D2 add guidance *on top*, and on this sample that delta is
   not a win (and sometimes a regression). spec-01's marginal value over the
   middleware baseline is **unproven-to-negative**.

**Verdict: DRAFT, NOT promoted.** A valid A/B isn't even possible until D4 is
fixed to truly disable the tool. Open options: (a) fix D4 (exclude middleware)
and re-run a clean A/B; (b) reconsider whether the D1/D2 blocks earn their
tokens at all given the always-on middleware; (c) accept planning-by-middleware
as the baseline and drop the domain blocks. Decision deferred to maintainer.

**D4 FIXED (2026-06-15, branch `fix/d4-true-planning-off`).** Finding #3 above
is resolved. The OFF path now swaps `deepagents.graph.TodoListMiddleware` for a
no-op `AgentMiddleware` subclass at construction time
(`_maybe_disable_todo_middleware`, wrapping both `create_deep_agent` calls).
This **changes the OFF semantics** from "today's exact behavior (middleware
todos still on)" to "all planning off" — the correct meaning for a kill-switch.
Probe (recorder middleware capturing `request.tools` / `request.system_prompt`,
both arms via `create_deep_agent`):
- ON  (`AITESTER_PLANNING` unset/true): `write_todos` IS in tools AND in prompt.
- OFF (`AITESTER_PLANNING=false`): `write_todos` NOT in tools AND NOT in prompt.
`ruff check` clean, 38 tests pass, module imports. A clean planning-vs-no-planning
A/B (option a) is now possible; re-run + promotion decision still deferred.

Aside (not planning-related): the run surfaced a pre-existing
`LocalShellBackend virtual_mode` deprecation warning at `agent_loop.py:410` —
worth addressing separately.

**CLEAN A/B (post-D4-fix, 2026-06-15) — planning effect is TASK-DEPENDENT, not
a blanket win.** N=3/arm, truly-off OFF (0 `write_todos`), sonnet-4-6, parallel
@ concurrency 4, 360s timeout. Raw: `eval-ab-2026-06-15-clean.tsv`.

| site | arm | suite ok | mean s | mean iters | mean wt |
|------|-----|----------|--------|-----------|---------|
| quotes-js (easy) | OFF | 3/3 | **94**  | 22 | 0 |
| quotes-js (easy) | ON  | 3/3 | 276 | 39 | 3.3 |
| oscar-films (AJAX, hard) | OFF | **0/3** (timeout) | 360 | 18 | 0 |
| oscar-films (AJAX, hard) | ON  | **2/3** | 293 | 33 | 2.7 |

Findings:
1. **D4 fix validated live:** 0 `write_todos` across all 6 OFF runs — the
   kill-switch truly disables planning; the A/B is now trustworthy.
2. **Easy task → planning HURTS:** quotes-js ON is ~2.9× slower (276 vs 94s) and
   ~75% more iters (39 vs 22), both arms succeed. Pure overhead.
3. **Hard task → planning HELPS convergence:** oscar-films OFF failed to author
   in 6 min on all 3 trials; ON completed 2/3 (245–273s). The plan helped the
   agent commit to a terminal `write_robot_suite` instead of wandering to
   timeout. (n=3 w/ timeouts → suggestive, not proven.)
4. **No replication of picobay's "+34% everywhere."** Directionally consistent
   with picobay's deeper read (planning helps harder structured tasks, overhead
   elsewhere), but the easy-case regression here is large.

**VERDICT: do NOT keep planning default-ON.** The ~3× easy-case slowdown is too
costly for a blanket default. Recommended: flip default to OFF with opt-in for
hard/slow-to-converge targets, OR fix the prompt-induced iteration bloat (the
"call write_todos first + mark each step" guidance ~doubles rounds on easy
sites) before reconsidering default-on. Spec remains **DRAFT**; promotion
declined on this evidence.

**CORRECTION (2026-06-15, post spec-02 fail-fast fix).** The "~3× slower" above
was an artifact: it was dominated by agent-browser's **30s-per-missed-probe
stall** (see `docs/internals/exploration-driver-map.md` + spec-02), NOT
planning. After spec-02 eliminated the stalls, a **clean serial** A/B (no env
race, planning confirmed firing — `write_todos=3` ON / `0` OFF) on quotes-js:

| arm | suite | wall | llm_calls | llm_time | write_todos |
|-----|-------|------|-----------|----------|-------------|
| OFF | ✓ | 98s | 13 | 64s | 0 |
| ON  | ✓ | 107s | 20 | 76s | 3 |

Real effect on this easy task: planning is a **modest net cost** — +9% wall,
+19% LLM time, +54% LLM calls, **no outcome benefit** (both succeed). The
overhead is the extra `write_todos` + reasoning rounds; unlike picobay's
`update_plan`, deepagents' flat `write_todos` does **not** reduce redundant
verification, so there's no offsetting saving. **The decline-default-ON verdict
stands, but the magnitude is ~10–20%, not 3×.** Caveats: n=1/arm (variance
unmeasured); hard-site case still not cleanly measured (oscar-films is
rate-limit/latency-bound in this env). A 3-trial confirmation would firm it up.
