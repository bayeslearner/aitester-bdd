---
spec_id: 06-sandbox-runtime
status: DRAFT
closed_as: null
since: 2026-10-23
until: null
epic: authoring
features: [sandbox-run, author-interface, secret-off-argv, runtime-batched-counts, resume-on-retry, trimmed-prompt]
supersedes: []
superseded_by: null
depends_on: [05-agent-safety-and-replayable-suites]
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

## Design decisions to take first

- Sandbox runtime: OrbStack machine vs Docker container; image contents and size; how the VM case
  (archestra-test) gets the same image.
- Whether `--sandbox` becomes the default for `author`.

## Log

- 2026-10-23: drafted as the successor of specs 04 and 05.
