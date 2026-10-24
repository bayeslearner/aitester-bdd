---
spec_id: 06-selector-grounding
status: ACTIVE
closed_as: null
since: 2026-10-23
until: null
epic: authoring
features: [match-grounded-selectors, author-wall-clock, run-id-in-wrappers]
supersedes: []
superseded_by: null
depends_on: [05-agent-safety-and-replayable-suites]
anchors:
  - docs/internals/authoring.md
  - docs/history/review-2026-10-23/05-CROSS_PROJECT_CHECK.md
---

# Selectors the author proved, and a clock on the author

## Why

Five rounds against Archestra 1.5.0-rc.6 on 2026-10-23 (investigation records probe-789…846) ended
with replays that fail on the last check rule, not the first. The remaining failures are the author's
choice of element: `locator "h3.flex" contains "Connect your…"` where two `h3.flex` exist and the first
carries the other sentence; `[data-slot=alert]` likewise. The many-match check of 0.5.1 let these through
because the author wrote `# first-match: intended` on the line itself: a gate the gated party switches
off. The coordinator's direction (relaying the owner, 2026-10-23 night): fix aitester where it pays, on
gpt-6-luna; a replay that still fails must fail because of the app.

## Requirements

### R1 — a single-element step pins exactly one element, or the one that holds its text

WHEN the author calls `write_robot_suite`, THE writer SHALL evaluate every selector of a single-element
step (click, type, has text, contains, is visible/disabled, has attribute, has value) on the current
page and SHALL refuse the suite when a selector matches more than one element, naming each match
(index, tag, first 80 characters of text, the attributes it carries: id, data-testid, aria-label,
name, placeholder, href, role) so that the author can pin one. For a text check (`has text`,
`contains`, `matches`) the writer SHALL accept the selector only when exactly one match holds the
expected text and SHALL name that match's attributes in the refusal otherwise. There is no comment that
switches the check off; `count` steps may match many. A selector that matches nothing on the current
page is allowed as today (the step may belong to another page); the refusal says so when it happens on
a text check, so the author knows the check did not run.

### R2 — a wall clock on the in-process author

`AITESTER_AUTHOR_TIMEOUT` (seconds, default 900, the ACP path's value) SHALL bound the deepagents
author too: when the budget is spent the stream stops, the run ends with no terminal call and the
message names the budget. Progress lines carry the remaining budget at each step.

### R3 — the Archestra wrappers use one grammar and the run id aitester sets

`run_suite.sh` injects the `env:` sign-in block only (done 0.5.1), exports `AITESTER_LLM_*` only when the
suite carries an `I explore` line, and stops exporting `UI_RUN_ID`; stories and suites that need a
per-run name use `%{AITESTER_RUN_ID}` (set at `I start verification`; the wrapper may set it first so
the author's exploration and the replay share one id).

## Design

- R1 lives beside `get_counts` in `authoring/mcp_tools.py` as `get_matches(selectors)`: one `eval`
  returning, per selector, the count and up to five matches `{tag, text, attrs}`. `suite_problems`
  takes `matches` (a callable like `probe`) and, for each single-element step, applies the rule above.
  The `probe` count path stays for the parse check. The `# first-match` escape is removed, and the
  author prompt stops mentioning it.
- R2: `agent_loop._invoke_streaming` reads the budget once and breaks out of `agent.stream` when
  `time.monotonic() - t0` passes it; the final message is "author budget of N s spent after K steps".
- R3 is a wrapper change in the investigation, recorded there.

## Tasks

- [ ] R1 `get_matches` + lint + tests; prompt text; remove `first-match`
- [ ] R2 budget + test
- [ ] R3 wrappers (investigation repo, no commit there)
- [ ] Rerun the six rc.6 stories (records from 847); each replay that fails names an app cause
- [ ] Tag v0.5.2 when the unit tests and the live round are green; CHANGELOG

## Verification

- `uv run --frozen ruff check src/ tests/`; `uv run --frozen --extra acp pytest tests/unit`.
- Live: `rerun_050.sh` on archestra-test rc.6; the records say per story whether the replay passed, and
  when it did not, which app behaviour it stopped on.

## Log

- 2026-10-23 (night): opened on the coordinator's direction after the rc.6 rounds; sandbox renumbered to 07.
