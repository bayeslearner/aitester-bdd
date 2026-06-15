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
- [ ] 1.1 Prompt fail-fast guidance in `_EXPLORE_SYSTEM_PROMPT` + author
      `build_system_prompt` (agent-browser/CLI path): probe with
      count/is-visible/eval; never `get text/html/attr` on unverified selectors.
- [ ] 1.2 Prompt fail-fast guidance in `PLAYWRIGHT_EXPLORE_PROMPT` (in-RF path):
      probe count first; content getters only on confirmed selectors.
- [ ] 1.3 Code: `playwright_tools._get_text`/`_get_attribute` count-check first
      (return "" instantly on 0 matches); set a short explore browser timeout.
- [ ] 1.4 Skill: add the 30s-quirk + probe-first note to the agent-browser skill.
- [ ] 1.5 Verify: imports, `ruff check`, full `pytest` (baseline 38), and a
      direct timing harness proving a missed probe is now fast on the in-RF
      Playwright getter.

### P2 — Should Do (the "correct understanding of planning")
- [ ] 2.1 Re-run a clean planning A/B on the fail-fast path: 1 easy + 1 hard
      target, ON vs OFF, measuring **tool-call counts + LLM time** (not
      stall-dominated wall-clock). Record in spec-01's eval section.

## Open Questions
- [ ] Should the CLI path eventually converge onto Playwright (true driver
      unification), retiring the raw-shell agent-browser exploration? (Bigger;
      out of scope here — note for a future spec.)

## Log
**2026-06-15** — Created from the driver diagnosis. Root cause + 3-layer fix
(prompt/code/skill) decided. Depends on spec-01 (planning) for the A/B re-run.
