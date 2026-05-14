# aitester-bdd

**LLM-driven BDD test authoring for Robot Framework.** Give it a story and a live web app; an agent explores the target via `agent-browser`, then writes a deterministic `.robot` suite with selectors grounded in the snapshots it actually took — or files a bug report when the system is broken in a way that prevents the test.

## What it is

A Robot Framework library that fills a gap in the RF ecosystem: turning a plain-English intention into a deterministic, executable `.robot` test suite. Run-time has no LLM in the loop; the suite is plain RF code that runs reproducibly.

## What's novel

| Existing | What aitester-bdd adds |
|---|---|
| `robotframework-browser` (Playwright) | — |
| `robotframework-aiagent` (Chat keyword) | — |
| LangChain / DeepAgents | — |
| _no canonical package_ | **Intention → `.robot` suite** authored by an agent loop that drives the target live via `agent-browser` |
| _no canonical package_ | **Bug-report exit channel** — agent writes `triage/<story>.md` instead of a fake suite when the system is broken |
| _no canonical package_ | **Three pluggable runtime backends** — `agent-browser` (default, zero-install), `playwright` (in-process speed), `nodriver` (bot-detection-resistant) — same authored suite runs on any of them |
| _no canonical package_ | **AOP failure aspect** — every rule failure ships with an AI-written natural-language diagnosis (SUT-vs-test classification) plus a full MDP trajectory in `walk_log.jsonl` |
| _no canonical package_ | **Rule DAG with parent-child composition** + observation-gate discipline + retry-with-redo guard semantics (ported from WISE BDD) |

## Status

**Alpha.** Authoring path verified end-to-end against public sites (example.com, the-internet.herokuapp.com/login) and against an intentional-fail suite that exercises the AI failure-diagnosis aspect.

## Quick start

```bash
pip install aitester-bdd          # base install
npm i -g agent-browser            # browser CLI for both Explore and Run

# Set your LLM endpoint. Defaults point at claude-code-proxy:
export AITESTER_LLM_MODEL=openai/cc/claude-opus-4-7
export OPENAI_BASE_URL=http://localhost:20128/v1
export OPENAI_API_KEY=placeholder

# Author a suite from a story
aitester author \
  --story "log in as admin and verify the case list shows at least one row" \
  --base-url http://localhost:5173 \
  --out suite.robot

# Run it (no LLM at run time; uses agent-browser backend by default)
aitester run suite.robot
```

Output sidecar files at `<output_dir>/`:
- `walk_log.jsonl` — every MDP transition (rule_enter / before_action / after_action / state_check / dismiss / emit / rule_exit)
- `failures.jsonl` — failure context + AI diagnosis for every failed rule
- `emit.jsonl` — explicit `And I emit "..."` captures (intention-driven; only when the story is a diagnostic probe)

## Three runtime backends, one authored suite

`AITESTER_BROWSER=` picks the driver at run-time:

| Backend | Default? | Setup | Best for |
|---------|----------|-------|----------|
| `agent-browser` | ✓ | none — CLI ships its own browser | most cases; same driver author + run, zero install friction |
| `playwright` | | `aitester init-browser` once | action-heavy tests where subprocess latency matters |
| `nodriver` | | `pip install aitester-bdd[stealth]` + Edge/Chrome | bot-detected sites (DataDome / Cloudflare BM / etc.) |

Same `.robot` runs on any of the three.

## Architecture (one paragraph)

The LLM is the author, not the runtime. At authoring time, a DeepAgents/LangGraph agent reads `SKILL.md` as its system prompt, drives the live target via `agent-browser` tools (open, snapshot, click, type, eval, screenshot), and emits a `.robot` file with selectors grounded in real snapshots — or writes a bug report when the system is broken in a way that prevents authoring. At run time, plain Robot Framework executes the suite via one of three pluggable browser backends; no LLM in the loop. Failures fire an AOP `diagnose` aspect that hands the LLM the MDP trajectory plus snapshot and asks "why?" — short natural-language diagnoses land on `RuleResult.ai_diagnosis` and `failures.jsonl`. The walker, gotcha-fixes, and AspectRegistry are ported from the WISE RPA BDD skill.

## License

MIT
