# Installation

## Base install

```bash
pip install aitester-bdd
```

This gives you the keyword library, walker, CLI, and the zero-install `agent-browser` backend.

## Runtime backends

aitester-bdd supports three browser backends. The **runtime default** (when a
suite declares no `${ENGINE}` and `AITESTER_BROWSER` is unset) is `playwright`,
which needs a one-time `aitester init-browser`. The `agent-browser` backend is
the zero-install option and the default engine that `aitester author` declares
in the suites it writes. Optional extras enable the others:

### agent-browser (zero-install)

```bash
npm i -g agent-browser
```

No Python extras needed. The CLI ships its own Chromium. Every authored selector is guaranteed to resolve identically at run time because authoring and execution use the same driver.

### Playwright (in-process speed)

```bash
pip install aitester-bdd[playwright]
rfbrowser init  # downloads ~300MB of browsers once
```

Faster for action-heavy suites (no subprocess overhead per action). Declare in your suite:

```robot
*** Variables ***
${ENGINE}    playwright
```

### Nodriver (stealth / bot-detection bypass)

```bash
pip install aitester-bdd[stealth]
```

Requires Microsoft Edge or Google Chrome already installed on the system. No Playwright fingerprint — evades DataDome, Cloudflare BM, and similar bot detection. Declare:

```robot
*** Variables ***
${ENGINE}    nodriver
```

## LLM configuration (authoring only)

The LLM is only needed at **authoring time** (`aitester author`). Running authored suites (`aitester run`) consumes zero tokens.

```bash
# Option A: any OpenAI-compatible gateway (required: aitester ships no default model or endpoint)
export AITESTER_LLM_MODEL=claude-sonnet-5-5
export AITESTER_LLM_BASE_URL=https://your-gateway.example.com/v1
export AITESTER_LLM_API_KEY=...

# Option B: direct Anthropic API
export AITESTER_LLM_MODEL=claude-opus-4-7-20250219
export ANTHROPIC_API_KEY=sk-ant-...

# Option C: any OpenAI-compatible endpoint
export AITESTER_LLM_MODEL=gpt-4o
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_API_KEY=sk-...
```

## Development install

```bash
git clone https://github.com/bayeslearner/aitester-bdd.git
cd aitester-bdd
uv sync --dev
uv run pytest tests/ -q  # verify
```

## Verify installation

```bash
aitester --version
agent-browser --version
```
