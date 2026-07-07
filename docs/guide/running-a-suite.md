# Running a Suite, Start to Finish

This is the one page that takes you from a clean machine to a passing (or
honestly failing) run — the env contract, the two modes, the preflight, the
screenshot trail, and the failure messages you will actually see with their
fixes. It is written to be read by an AI agent driving the tool, so there is no
tribal knowledge: everything you need is here or printed by `aitester doctor`.

## 0. The one thing that will never happen

**A run against a stub browser can never report PASS.** If the browser backend
cannot actually drive (RF-Browser not initialized, `agent-browser` CLI missing,
no Chrome/Edge for nodriver), the walker refuses to start and raises loudly
(INV-4). Green means the checks ran against a real DOM. If you want to see a
green check, you have to make the browser real first.

## 1. Install + preflight

```bash
pip install aitester-bdd          # or: uv pip install aitester-bdd
aitester doctor                   # tells you exactly what is and isn't ready
```

`aitester doctor` checks, in order:

- the **Python interpreter** it is running under (and flags a dead venv whose
  interpreter was deleted — the `bad interpreter` failure mode),
- **robotframework**,
- the **playwright explorer** (used during authoring) — can it launch chromium,
- your selected **runtime backend** (`AITESTER_BROWSER`),
- for `agent-browser`: a **command-shape smoke test** that drives the exact
  subcommands the backend depends on (`open`, `snapshot -c -i --json`,
  `get count/text`, `click`, `type`, `press`, `screenshot`) against a local
  `data:` URL — this catches CLI-version drift before your suite does,
- the LLM stack (deepagents/langgraph/langchain/litellm) and LLM env vars.

Run `aitester doctor --no-smoke` in headless CI to skip launching a browser.

### Reproducible setup (avoid the dead venv)

Pin the venv to a Python that exists on the machine and recreate it if the
interpreter moved:

```bash
python3.12 -m venv .venv-e2e        # or: uv venv --python 3.12 .venv-e2e
. .venv-e2e/bin/activate
pip install aitester-bdd
aitester doctor                     # confirms the interpreter resolves
```

If `doctor` prints `✗ python interpreter path does not exist` or
`✗ VIRTUAL_ENV=... but its interpreter is missing`, delete and recreate the
venv — do not fight it.

## 2. Pick a backend (the env contract)

| Backend | `AITESTER_BROWSER` | One-time setup | When |
|---------|--------------------|----------------|------|
| **playwright** (default) | `playwright` | `aitester init-browser` | in-process speed, action-heavy suites |
| **agent-browser** | `agent-browser` | `npm i -g @bayeslearner/agent-browser` | zero-init, same driver as authoring, easiest to debug |
| **nodriver** | `nodriver` | system Chrome/Edge + `pip install aitester-bdd[stealth]` | bot-detected sites |

A suite declares its preferred backend as `${ENGINE}` in `*** Variables ***`;
`aitester run` reads it and sets `AITESTER_BROWSER` for you. `--engine` overrides
the suite; the `AITESTER_BROWSER` env var overrides both.

Full variable list: [Environment Variables](../reference/env-vars.md).

## 3. The two modes

Both live inside one `.robot` suite and share one browser session.

- **Pinned** — deterministic steps (`When I click`, `And selector exists`)
  grounded on CSS/testid selectors you (or the authoring agent) traced from the
  live DOM. Fast, repeatable, no LLM at run time.
- **Fluid** — `When I explore    <story>`: an LLM agent drives the browser with
  agency to complete a journey (and, with `I explore and author`, can even emit
  a pinned `.robot` suite from what it did). Fluid needs LLM creds (§5).

A suite can mix them: pin the login and chrome, stay fluid on the
data-dependent middle. Variants are data, not code forks — you own how much of
each you use.

## 4. Run it

```bash
aitester run path/to/suite.robot                 # normal
aitester run suite.robot --headed --step-delay 500   # watch it
aitester run suite.robot --base-url http://localhost:5173
```

Outputs land in the RF output dir: `log.html`, `report.html`, plus
`walk_log.jsonl` (every MDP transition), `emit.jsonl` (captured data), and
`failures.jsonl` (deterministic failure + optional AI diagnosis).

## 5. LLM configuration (fluid + diagnosis)

Three variables, one value:

```bash
export AITESTER_LLM_MODEL=cc/claude-opus-4-7          # bare name
export OPENAI_BASE_URL=http://localhost:20128/v1      # scheme+host, not just /v1
export OPENAI_API_KEY=placeholder                     # real key for other providers
```

Set the **bare** model name. aitester normalizes it per consumer — stripping
`openai/` for the langchain explore agent, adding `openai/` for the litellm
judge — so you never juggle two formats. Leave all three unset to use the
claude-code-proxy defaults. Set-but-blank/malformed fails loudly at start.

## 6. The screenshot trail

By default a *passing* run leaves no PNGs (fluid navigates by accessibility
snapshot; pinned only shoots on failure). To get a numbered visual trail of the
whole journey:

```bash
AITESTER_SHOT_EVERY_STEP=1 aitester run suite.robot
```

- **Pinned**: `step_0001_<rule>_<action>.png`, `step_0002_...` after every
  action and rule.
- **Fluid**: the explore agent is told to call `browser_screenshot(label=...)`
  (in-RF) or `agent-browser screenshot` (standalone) at each milestone →
  `explore_0001_<label>.png`.

All land in the RF output dir. `When I take screenshot` (explicit) also defaults
into the output dir now, not CWD — pass an absolute path to override.

## 7. The five failure messages you'll actually see

| Message (abridged) | Cause | Fix |
|--------------------|-------|-----|
| `browser preflight FAILED — refusing to run so a stub browser cannot report a silent PASS (INV-4) … RF-Browser not initialized` | `AITESTER_BROWSER=playwright` but `rfbrowser init` never ran | `aitester init-browser`, or `AITESTER_BROWSER=agent-browser` |
| `… agent-browser CLI not found on PATH` | agent-browser backend, CLI missing | `npm i -g @bayeslearner/agent-browser`, or switch to `playwright` |
| `LLM configuration is invalid … OPENAI_BASE_URL is malformed` | base URL is a bare path like `/v1` | set `OPENAI_BASE_URL=http://host:port/v1` |
| `LLM configuration is invalid … OPENAI_API_KEY is set but BLANK` | empty cred exported | unset it (uses placeholder) or set a real key |
| `agent-browser command shapes DRIFTED` (from `doctor`) | installed agent-browser version changed a subcommand shape | pin/upgrade agent-browser to a compatible version |

## 8. Acceptance self-check

You are set up correctly when, from a clean machine with `agent-browser`
installed, you can:

1. `aitester doctor` → all backend checks green (or a clear remedy line),
2. `aitester run` a pinned suite **and** a fluid suite against a target app,
3. get a **loud, actionable error** for each failure in §7 instead of a silent
   pass or a cryptic stack trace,
4. produce a numbered **screenshot trail** with `AITESTER_SHOT_EVERY_STEP=1`.

No step above requires knowledge that isn't on this page or in `aitester doctor`.
