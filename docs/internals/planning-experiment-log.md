# Planning experiment log — "does planning help exploration?"

Chronological record of the 2026-06-15 investigation, **including the dead-ends
and confounds**, so the conclusions are auditable and the mistakes aren't
repeated. Question: does giving the explore/author agent a planning tool
(`write_todos`) make authoring better/faster?

Primary artifacts: `specs/01-explore-author-planning/spec.md` (planning),
`specs/02-fastfail-exploration-probing/spec.md` (the driver fix that unblocked a
valid measurement), `docs/internals/exploration-driver-map.md` (driver map).
Raw data: `specs/01-.../eval-ab-2026-06-15.tsv`, `eval-ab-2026-06-15-clean.tsv`.

## TL;DR (corrected final understanding)

- On a **simple** authoring task, planning (`write_todos`) is a **~10–20% net
  cost** (+9% wall, +19% LLM time, +54% LLM calls) with **no outcome benefit** —
  measured cleanly only after fixing the confounds below.
- The earlier headline "**planning is ~3× slower**" was **false** — an artifact
  of an agent-browser driver stall, not planning.
- deepagents' flat `write_todos` (unlike picobay's `update_plan`) doesn't reduce
  redundant work, so it has no offsetting saving → **default flipped to OFF**
  (opt-in via `AITESTER_PLANNING=1|true|on|yes`), commit `72ee97d`.
- **Still unmeasured:** the hard-task case cleanly; n>1 trials; the in-RF
  Playwright path live (everything below was on the CLI/agent-browser path).

## The experiments, in order

### Exp 1 — first A/B (CONFOUNDED: kill-switch was a no-op)
6 runs (3 hard wise-corpus sites × ON/OFF), CLI `aitester author`, planning
"default-on". Result looked mixed-to-negative. **Confound:** `write_todos` fired
2–3× *even on the OFF arm*. Root cause: deepagents' `TodoListMiddleware` is
always in the default stack; the `AITESTER_PLANNING=false` switch only dropped
*our* prompt block, not the tool. So OFF still planned → not a real A/B.
→ Fix: D4 now swaps `TodoListMiddleware` for a no-op (commit `0670e90`).

### Exp 2 — clean-ish A/B post-D4 (CONFOUNDED: wall-clock = driver stalls)
12 runs (quotes-js, oscar-films × ON/OFF × 3), concurrency 4. Headline:
quotes-js ON 2.9× slower; oscar-films OFF 0/3 vs ON 2/3. **Confound discovered
later:** wall-clock was dominated by ~200s/run of agent-browser tool stalls
(~30s gaps), not planning. Also oscar-films hit 360s timeouts. So "seconds" was
junk; the "3×" was noise.

### Diagnosis — the root confound (a driver bug, not planning)
Per-LLM-call tracing showed 100s LLM + ~200s of ~30s gaps. Direct-timing the
third-party `agent-browser` binary: `get text/html/attr/value/box` on a **0-match
selector blocks the full 30s** (Playwright default locator timeout, surfaced as
`os error 35`); `get count`/`is visible`/`eval` are **instant**. During
exploration the agent *probes/guesses* selectors → 30s per miss. This — not
planning — produced every "slow" number above. Full write-up:
`docs/internals/exploration-driver-map.md`. Fixed in spec-02 (prompt + a
structural fail-fast count-check in the Playwright getter + a skill note).

### Exp 3 — post-fix A/B (INVALID: my runner raced the flag)
4 runs, concurrency 2, on the fail-fast path. **Good news:** stalls dropped to
**0–1/run** (the fix works; tool mix now `count`/`eval`-dominated). **But
invalid for planning:** `write_todos=0` on the ON arms — my runner set
`AITESTER_PLANNING` via process-global `os.environ` while running ON/OFF in
parallel threads, so the OFF thread clobbered the ON flag. Plus oscar-films
`llm_time=1600s` = rate-limit (429) backoff inside the calls. Two more confounds.

### Exp 4 — serial A/B (VALID, finally)
Serial quotes-js OFF then ON (one process → no env race), fail-fast path.
Planning **fired** (`write_todos=3` ON / `0` OFF); both succeeded.

| arm | suite | wall | llm_calls | llm_time | write_todos | stalls>15s |
|-----|-------|------|-----------|----------|-------------|------------|
| OFF | ✓ | 98s | 13 | 64s | 0 | 1 |
| ON  | ✓ | 107s | 20 | 76s | 3 | 1 |

→ planning = ~+9% wall / +19% LLM time / +54% calls, no benefit. The clean,
trustworthy data point. (n=1/arm; one residual stall in each — the prompt fix
isn't 100%.)

## Confound catalog (the methodology lessons)

1. **No-op kill-switch** — "off" still ran the mechanism (always-on middleware).
   *Lesson: prove the control arm is actually off (here: `write_todos` count).*
2. **Wrong primary metric** — wall-clock was dominated by a driver stall.
   *Lesson: measure the thing under test (LLM calls/time), not end-to-end time
   that bundles unrelated I/O.*
3. **Shared mutable global across concurrent runs** — `os.environ` raced.
   *Lesson: per-run flags must be process-isolated, or run serially.*
4. **Rate-limit backoff inflated "compute"** — retries hid inside call latency.
   *Lesson: watch for 429 backoff; serialize to avoid it; sanity-check
   per-call latency.*
5. **Benchmarked the wrong path** — the CLI/agent-browser path, not the in-RF
   Playwright feature people actually use. *Lesson: confirm the code path under
   test matches the product surface.*

## Open / unverified

- Hard-task planning effect, cleanly (oscar-films is rate-limit/latency-bound
  in this env) — the one place planning plausibly *helps* (convergence).
- n>1 trials for variance (current valid result is n=1/arm).
- The in-RF Playwright explorer, measured live (all numbers here are CLI).
- Whether the CLI path should converge onto Playwright (spec-02 open question).
