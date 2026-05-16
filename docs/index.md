# aitester-bdd

**LLM-driven BDD test authoring for Robot Framework.** Give it a story and a live web app; an agent explores the target, then writes a deterministic `.robot` suite with selectors grounded in the actual DOM — or files a bug report when the system is broken.

## The key insight

The LLM is the **author**, not the **runtime**. At authoring time, an agent drives a live browser and produces a `.robot` file. At run time, plain Robot Framework executes the suite — no LLM, no tokens, fully deterministic. Failures optionally get an AI diagnosis after the fact.

## What makes it different

- **Intention → `.robot` suite** — from English story to executable test in one command
- **Three runtime backends** — `agent-browser` (zero-install), `playwright` (in-process speed), `nodriver` (stealth)
- **Rule DAG** — parent-child composition, guards, retry-with-redo, scope inheritance
- **Deferred execution** — every keyword builds a plan; nothing touches the browser until `Then I finalize`
- **AOP failure diagnosis** — failed rules get a trajectory trace + AI-written explanation

## Quick example

```bash
# Author a suite from a story
aitester author \
  --story "Open the homepage, verify it has a search input and a logo" \
  --base-url https://example.com \
  --out smoke.robot

# Run it (no LLM at run time)
aitester run smoke.robot
```

## Next steps

- [Quick Start](getting-started/quickstart.md) — install and run your first test in 5 minutes
- [Writing Suites](guide/writing-suites.md) — learn the keyword vocabulary
- [How It Works](internals/architecture.md) — understand the implementation
