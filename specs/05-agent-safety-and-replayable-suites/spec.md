---
spec_id: 05-agent-safety-and-replayable-suites
status: CLOSED
closed_as: SHIPPED
since: 2026-10-23
until: null
epic: authoring
features: [browser-tool-no-shell, credentials-by-name, shell-default-deny, origin-pinning, batched-browser-commands, fast-selector-miss, selector-lint, setup-success-marker, run-budget, cleanup-actions, invalid-selector-not-zero]
supersedes: []
superseded_by: 06-sandbox-runtime
depends_on: [04-agent-runtime-hardening-acp]
anchors:
  - docs/internals/authoring.md
  - docs/history/review-2026-10-23/04-SECURITY_PERFORMANCE_RELIABILITY.md
---

# Agent safety and replayable suites

## Why

The first authoring runs against a real single-page app (Archestra 1.4.0-rc.55, 2026-10-23) showed
seven things the independent review `docs/history/review-2026-10-23/04-SECURITY_PERFORMANCE_RELIABILITY.md`
turned into sixteen proposals:

- (a) a signed-out agent ran `env | grep password` and grepped the run folder; its shell could read any file;
- (b) 3 of 9 authored suites used Playwright-only selectors the agent-browser runtime cannot execute;
- (c) 60–600 s per story, one model round trip per browser read;
- (d) the sign-in fixture needed waits and read-back to survive hydration;
- (e) a 300 s global run timeout cut a healthy long test;
- (f) aborted runs left invitations and projects behind;
- (g) exact-count assertions broke on unrelated UI changes.

## Decisions (owner direction, 2026-10-23)

- Restricted tools now; a throwaway sandbox runtime is the next spec, not this one. Kun: tests
  "should be run in a sandboxed environment and then destroyed afterwards".
- Credentials are referred to by name (`env:NAME`); the agent never holds a value.
- Clean-up through the UI grammar and through a direct API action; a suite may use either.

## Requirements and dispositions

| # | requirement | from | state |
|---|---|---|---|
| S1 | The in-process author gets `browser`, `write_robot_suite`, `report_bug` and nothing else; no shell | review S1 | done: `authoring/tools.py::build_browser_tool`, `agent_loop.py`; test `test_author_tools_are_browser_and_terminal_only` |
| S2 | State-setup values may be `env:NAME`; `aitester author --signin FILE` signs the browser in first and writes the block into the suite | review S2 | done: `engine/walk.py::resolve_secret_ref`, `authoring/signin.py`, `cli.py` |
| S3 | A suite's `shell` action runs only with `AITESTER_ALLOW_SHELL=1`; the author refuses it without `# allow-shell` | review S3 | done |
| S4 | `open` stays on the app's origin (`AITESTER_ALLOWED_ORIGINS` for a sign-in host); `eval` is logged | review S4 | done: `mcp_tools.run_browser_command` |
| S5 | Secret values off agent-browser's argv | review S5 | open: the installed CLI (0.32.0) has no stdin or env input for `fill`/`type`; needs an upstream change |
| P1 | `browser` takes a list of commands, stops at the first failure | review P1 | done: `run_browser_commands` |
| P2 | One eval for many counts; CLI `wait` instead of a spawn per poll | review P2 | partly: `get_counts` exists and backs the lint; the runtime's poll loop is unchanged |
| P3 | Content getters fail at once on a selector with no match; prompt workarounds removed | review P3 | done |
| P4 | Resume the thread on retry | review P4 | open |
| P5 | Trim the system prompt | review P5 | open |
| R1 | `write_robot_suite` rejects Playwright-only selectors and ones the live browser cannot parse | review R1 | done: `suite_problems(engine, probe)` |
| R2 | `skip_when` is the state-setup success marker | review R2 | done |
| R3 | Run budget opt-in; rules past it reported as not run | review R3 | done; `And I set run timeout N s` |
| R4 | Clean-up actions run after the suite even on abort | review R4 | done: `And I configure cleanup`, `walk.run_cleanup`, `Verdict.cleanup_failures` |
| R5 | Exact counts above 1 refused unless marked intended | review R5 | done (in the lint) |
| R6 | An invalid selector is an error, not 0 | review R6 | done for agent-browser (`get_count` via the page); nodriver unchanged |

## Verification

- `uv run --frozen ruff check src/ tests/` clean; `uv run --frozen --extra acp pytest tests/unit` passes
  (127 tests: 108 before this sprint + 19 in `tests/unit/test_spec05_hardening.py`).
- Live: the Archestra log-search story authored with `--signin` on a fresh session; the suite replays
  with `aitester run` and its sign-in block resolves `env:` references.

## Out of scope (next spec)

Sandbox runtime (OrbStack machine or container per run, bind-mounting only the run folder, destroyed
afterwards); S5; P2's runtime poll loop; P4; P5; the Playwright and nodriver backends' `get_count`.

## Log

- 2026-10-23: sprint opened and implemented in one pass after the review; owner decisions recorded above.
- 2026-10-23: live check passed. Archestra log-search story: `--signin` signed the session in, the agent made
  7 `browser` calls (batched) and no shell call, wrote the suite in 40 s with the sign-in block as `env:`
  references (probe-774); `aitester run` replayed it in a fresh browser and both rules passed (probe-776).
  127 unit tests, ruff clean. Closed SHIPPED; S5, P2 (runtime), P4, P5 and the sandbox go to spec 06.
  Tagged v0.5.0.
- 2026-10-23 (later): six 0.5.0 suites replayed against 1.5.0-rc.6 on gpt-6-luna; three failed on bare-tag
  locators and an exploration-time project id, one authoring run jammed on a 240 s wait. Lint and the wait
  cap added as 0.5.1 (CHANGELOG); the replays are the live check for it.
