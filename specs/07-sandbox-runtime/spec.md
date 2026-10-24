---
spec_id: 07-sandbox-runtime
status: ACTIVE
closed_as: null
since: 2026-10-24
until: null
epic: authoring
features: [dry-replay, sandbox-run, author-interface, secret-off-argv, runtime-batched-counts, resume-on-retry, trimmed-prompt]
supersedes: []
superseded_by: null
depends_on: [06-selector-grounding]
anchors:
  - docs/internals/authoring.md
  - docs/history/review-2026-10-23/04-SECURITY_PERFORMANCE_RELIABILITY.md
---

# A throwaway sandbox per run, and the leftovers of specs 04 and 05

## Why

Spec 05 made the authoring agent's tools small. The owner's standing direction is that these tests
run in a sandbox that is destroyed afterwards ("I'm not too worried, and in reality these testing
should be run in a sandboxed environment and then destroyed afterwards", 2026-10-23). This spec is
that sandbox, plus the review items spec 05 did not finish.

## Requirements

### R1 — `--sandbox`

WHEN `aitester author` or `aitester run` is given `--sandbox`, THE run SHALL execute inside a
throwaway container (OrbStack locally, Docker on a VM) holding aitester, agent-browser and Chrome;
network limited to the app under test and the model gateway; secrets injected into the harness
process only; the run folder bind-mounted; the container destroyed after the suite, records and
screenshots are copied out.

### R2 — one `Author` interface (spec 04 R6, carried forward)

THE CLI and the in-Robot fluid path SHALL call one `Author` protocol with the deepagents and ACP
implementations returning the same result type.

### R3 — secrets off argv (review S5)

A `secret` value SHALL not appear on agent-browser's command line. Needs an input path in the CLI
(`fill --stdin` or an env-named value); agent-browser 0.32.0 has none.

### R4 — runtime batched counts (review P2)

THE agent-browser runtime backend SHALL use one `eval` for a list of selectors (fallback candidates,
interrupt and guard selectors) and the CLI's own `wait` for an attach wait, instead of a process
per poll.

### R5 — resume on retry (review P4); R6 — trimmed system prompt (review P5)

## R0 — a dry replay inside the authoring run (first; coordinator's direction, 2026-10-24)

WHEN the author calls `write_robot_suite` and the suite passes the write-time checks, THE writer SHALL
run the suite once with Robot in a fresh browser session, from the suite's own sign-in block, before
accepting it. WHEN that run fails, THE writer SHALL refuse the suite and return the first failing step
(rule, step, expected, observed, or Robot's own error), and the author fixes the step or files the app
fault it shows. `AITESTER_DRY_REPLAY_RETRIES` (default 3) caps the refusals per authoring run; past the
cap the writer refuses with "cap reached" and the author ends with `report_bug` naming the step.
`AITESTER_DRY_REPLAY=0` turns the dry replay off; `AITESTER_DRY_REPLAY_BEFORE` names a command run
before each dry replay (the Archestra wrapper points it at `lab_cleanup.sh`, since a dry replay creates
the same project or invitation the exploration did); `AITESTER_DRY_REPLAY_TIMEOUT` (default 600 s)
bounds one dry replay.

Design: `authoring/dry_replay.py::dry_replay(suite_text, *, timeout_s, before) -> (ok, summary)`
copies the suite to a temporary directory, runs `python -m robot --outputdir … suite.robot` with
`AITESTER_RUN_SESSION` set to a fresh name and the process environment otherwise inherited (the
`env:` references resolve there, never in the agent), then reads `walk_log.jsonl` for the first
failing check or action; with no walk log it quotes Robot's output. `build_tools` and `build_server`
take the callable; tests pass a fake.

Tasks:
- [ ] R0 `dry_replay.py`, wiring in both authors, retry cap, tests
- [ ] Wrapper: `AITESTER_DRY_REPLAY_BEFORE=lab_cleanup.sh` in `author_ui_test.sh`
- [ ] Re-author and replay t09, t04, t01 from a clean lab; records named in the log
- [ ] Tag when green; CHANGELOG


## Candidates from the cross-project check (docs/history/review-2026-10-23/05-CROSS_PROJECT_CHECK.md)

- A1: write-ahead checkpoint and resume of an aborted run, as wise-rpa-bdd has (`WiseRpaBDD.py:386-545`); R5 covers only the author thread today.
- A2: one wall-clock budget for both authors (`AITESTER_AUTHOR_TIMEOUT` exists only on the ACP path); part of R2.
- A3: picobay-engine's capability vocabulary (net/dom/workspace/exec, declared by plugin, granted by host) as the shape of R1's network limits.
- A6: R3 without an agent-browser change: sign in through the Playwright backend, export storage state, start the agent-browser session from it.
- A7 (done 0.5.1): a run id a suite can use for the names of what it creates.

## Design decisions to take first

- Sandbox runtime: OrbStack machine vs Docker container; image contents and size; how the VM case
  (archestra-test) gets the same image.
- Whether `--sandbox` becomes the default for `author`.

## Log

- 2026-10-23: drafted as the successor of specs 04 and 05.

- 2026-10-24: activated for R0 on the coordinator's direction; spec 06 closed FORK-FORWARD into it.
