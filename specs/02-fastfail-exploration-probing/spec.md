---
spec_id: 02-fastfail-exploration-probing
status: DRAFT
since: 2026-06-15
until: null
epic: testing
features: [fastfail-probe-prompt, fastfail-playwright-getter, agent-browser-skill-note]
supersedes: []
superseded_by: null
depends_on: [01-explore-author-planning]
---

# Fail-fast exploration probing (kill the 30s `get` stall)

<!-- Fast-track. YAML is the source of truth for status/relationships. -->

## Context

Diagnosed 2026-06-15 (see `docs/internals/exploration-driver-map.md`): the
standalone `aitester author` exploration path drives the third-party
**agent-browser CLI**, whose content getters (`get text/html/attr/value/box`)
**block the full 30s** Playwright default timeout when the selector matches 0
elements, then fail with `os error 35`. `get count` / `is visible` / `eval`
are instant (no auto-wait). During exploration the agent *probes/guesses*
selectors, so it repeatedly eats 30s per miss — that, not planning, dominated
the planning A/B wall-clock.

Two exploration drivers exist (`_is_inside_rf()` switch): **CLI → agent-browser
CLI** (raw shell via `execute`), **in-RF → Playwright** typed tools
(`_PlaywrightBackend` → robotframework-browser, ~10s timeout). The TS port
(`@picobay/engine`) avoids this entirely with an explicit fail-fast probe
wrapper (`BrowserDriverExplorer`: `count→0`, `text→""` immediately).

Success: a missed selector probe costs ≲ a couple seconds on **both** Python
paths, so authoring time reflects real work — and a re-run planning A/B becomes
measurable.

## Constraints

- agent-browser is **third-party**; the CLI exposes no `get` timeout flag/env.
  We cannot change its default — only how the agent *uses* it (probe order).
- In-RF path uses our own Playwright tools → we *can* add a fail-fast wrapper.
- No new dependencies. Keep `enable_planning` (spec-01) behavior intact.
- Prompt changes must not break the existing step_count / pinning guidance.

## Decisions

### D1: Mitigate the agent-browser (CLI) path by prompt, not code
**Choice:** Add explicit fail-fast probing guidance to `_EXPLORE_SYSTEM_PROMPT`
and the author prompt: probe existence with `get count`/`is visible`/`eval`
(instant); only call `get text/html/attr` on a *confirmed* (`count>0`) selector;
never on an unverified one (≈30s stall).
**Why:** the CLI agent writes raw shell — there's no wrapper seam in our code.
Steering the probe order is the only lever, and it's cheap and effective.

### D2: Fix the in-RF (Playwright) path in code — fail-fast getters
**Choice:** Make `playwright_tools._get_text`/`_get_attribute` **count-check
first** and return empty immediately when the selector matches 0 — mirroring
picobay's `BrowserDriverExplorer`. Also lower the exploration browser timeout.
**Why:** this is our code; a structural fail-fast wrapper removes the class of
bug rather than relying on the model. Aligns the Python in-RF path with the TS
port's design.

### D3: Patch the agent-browser skill to document the quirk
**Choice:** Add a "probe before you read" note to the agent-browser skill
(`~/.claude/skills/agent-browser/references/commands.md`).
**Why:** the skill never warns that content getters block 30s on a miss; any
agent using agent-browser benefits. Caveat: third-party skill, may be
overwritten on update — so the prompt fixes (D1) are the durable backstop.

## Tasks

### P1 — Must Do
- [x] 1.1 Prompt fail-fast guidance in `_EXPLORE_SYSTEM_PROMPT` + author
      `build_system_prompt` (agent-browser/CLI path): probe with
      count/is-visible/eval; never `get text/html/attr` on unverified selectors.
- [x] 1.2 Prompt fail-fast guidance in `PLAYWRIGHT_EXPLORE_PROMPT` (in-RF path):
      probe count first; content getters only on confirmed selectors.
- [x] 1.3 Code: `playwright_tools._get_text`/`_get_attribute` count-check first
      (return "" instantly on 0 matches); set a short explore browser timeout.
- [x] 1.4 Skill: add the 30s-quirk + probe-first note to the agent-browser skill.
- [x] 1.5 Verify: imports, `ruff check`, full `pytest` (baseline 38), and a
      direct timing harness proving a missed probe is now fast on the in-RF
      Playwright getter.

### P2 — Should Do (the "correct understanding of planning")
- [x] 2.1 Re-run a clean planning A/B on the fail-fast path. Stalls confirmed
      eliminated (0–1/run vs many pre-fix). Clean serial easy-site result
      recorded in spec-01: planning is ~10–20% overhead, not the earlier 3×
      artifact. Hard site (oscar-films) left unmeasured — rate-limit/latency
      bound in this env (n=1).

## Open Questions
- [ ] Should the CLI path eventually converge onto Playwright (true driver
      unification), retiring the raw-shell agent-browser exploration? (Bigger;
      out of scope here — note for a future spec.)

## Log
**2026-06-15** — Created from the driver diagnosis. Root cause + 3-layer fix
(prompt/code/skill) decided. Depends on spec-01 (planning) for the A/B re-run.

**2026-06-14** — Implemented P1 tasks 1.1/1.2/1.3/1.5 on branch
`feat/02-fastfail-probing`. (1.1) Added a "Selector probing — avoid 30s stalls"
block to `_EXPLORE_SYSTEM_PROMPT` and a new `_AUTHOR_PROBING_BLOCK` appended to
both author paths in `build_system_prompt` (default author + explore_and_author).
(1.2) Added a probe-before-read efficiency rule (#6) to `PLAYWRIGHT_EXPLORE_PROMPT`.
(1.3) Structural fix: `playwright_tools._get_text` now count-checks via
`_get_backend().get_count()` first and returns `{"success": True, "text": ""}`
immediately on 0 matches, never calling the auto-waiting `get_text` on a miss;
existing try/except → empty kept as fallback. Confirmed `_PlaywrightBackend.get_count`
(engine/browser.py) is the cheap guard (uses `get_element_count`, returns 0 on
exception). Note: `_get_attribute`/`_get_value` are not exposed as Playwright tool
functions, so 1.3's guard applies to `_get_text` only. (1.5) Verified: imports OK,
`ruff check` clean, `pytest` 38 passed (matches baseline), and a stub-backend unit
proof shows `_get_text` returns empty in ~0s WITHOUT calling the backend `get_text`
(stub would sleep 30s / assert if called). Task 1.4 (skill) and P2 left untouched.

**2026-06-15** — (1.4) Added a "⚠ Probe before you read" note to the
agent-browser skill (`~/.claude/skills/agent-browser/references/commands.md`)
documenting the 30s content-getter stall and the count/is-visible-first probe
pattern. P1 complete. Next: P2.1 re-run planning A/B on the fail-fast path.

**2026-06-15** — (2.1) Fail-fast fix VERIFIED on live runs: stalls>15s dropped
to 0–1/run (vs many pre-fix); tool mix now `count`/`eval`-dominated. A first
concurrent A/B was invalid (my runner raced `AITESTER_PLANNING` via global
`os.environ` across threads → `write_todos=0` everywhere; oscar-films also
hit rate-limit backoff). Re-ran **serial** quotes-js ON/OFF — planning fired
(`write_todos=3` ON / `0` OFF), both succeeded; planning = ~+9% wall / +19%
LLM time / +54% calls, no benefit. Recorded the correction in spec-01 (the
"3×" was the stall artifact). spec-02 P1+P2 done; ready to mark SHIPPED on
review. Hard-site clean measurement deferred (env-bound).
