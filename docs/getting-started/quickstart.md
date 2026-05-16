# Quick Start

Get a working test suite in under 5 minutes.

## Prerequisites

- Python 3.11+
- Node.js 18+ (for the `agent-browser` CLI)
- An LLM endpoint (Claude via claude-code-proxy, or any OpenAI-compatible API)

## Install

```bash
pip install aitester-bdd
npm i -g agent-browser
```

## Configure LLM access

```bash
# Default: claude-code-proxy (runs alongside Claude Code)
export AITESTER_LLM_MODEL=cc/claude-opus-4-7
export OPENAI_BASE_URL=http://localhost:20128/v1
export OPENAI_API_KEY=placeholder
```

## Author a suite

```bash
aitester author \
  --story "Open Wikipedia, verify the search input exists, search for 'BDD', verify the article heading" \
  --base-url https://en.wikipedia.org \
  --out wiki_smoke.robot
```

The agent will:

1. Open the browser and navigate to the base URL
2. Take accessibility snapshots to ground selectors
3. Write a `.robot` file with rules that test your story
4. Dry-run it to verify the keywords parse

## Run the authored suite

```bash
aitester run wiki_smoke.robot
```

Output:
```
Wiki Smoke :: Wikipedia smoke test  | PASS |
1 test, 1 passed, 0 failed
```

No LLM tokens consumed at run time. The suite is plain Robot Framework.

## Watch it run (headed mode)

```bash
aitester run wiki_smoke.robot --headed --step-delay 500
```

This opens a visible browser window and pauses 500ms after each action so you can follow along.

## What just happened

1. **Author phase** — the LLM drove `agent-browser` to explore the live site, took snapshots, grounded selectors in the real DOM, and composed a `.robot` file using the aitester-bdd keyword grammar.
2. **Run phase** — Robot Framework parsed the `.robot` file. The aitester-bdd keyword library built an in-memory rule DAG (deferred execution). `Then I finalize verification` triggered the walker, which executed the DAG against a live browser.

## Next steps

- [Writing Suites by Hand](../guide/writing-suites.md) — understand the keyword vocabulary
- [Rule Composition](../guide/rule-composition.md) — parent-child rules, guards, retry
- [How It Works](../internals/plan-then-execute.md) — the plan-then-execute model explained
