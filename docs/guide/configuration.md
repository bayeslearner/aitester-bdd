# Configuration

aitester-bdd is configured through environment variables, CLI flags, and in-suite declarations. No config files.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AITESTER_BROWSER` | `agent-browser` | Runtime backend: `agent-browser`, `playwright`, `nodriver` |
| `AITESTER_HEADED` | (unset) | Set to `1`/`true`/`yes` for visible browser |
| `AITESTER_STEP_DELAY_MS` | `0` | Milliseconds to pause after each action |
| `AITESTER_RUN_TIMEOUT` | `300` | Global run timeout in seconds |
| `AITESTER_DISABLE_ASPECTS` | (unset) | Comma-separated: `trajectory,instrument,diagnose,step_delay` |
| `AITESTER_EMIT_DIR` | RF `${OUTPUT_DIR}` or cwd | Where to write emit.jsonl and walk_log.jsonl |
| `AITESTER_RUN_SESSION` | auto-generated UUID | Override the browser session ID |
| `AITESTER_LLM_MODEL` | `cc/claude-opus-4-7` | Model for semantic checks and diagnosis |
| `AITESTER_AI_DIAGNOSIS` | `on` | Set to `off` to skip LLM diagnosis on failure |
| `AITESTER_WALK_LOG_MAX` | `2000` | Max entries in the in-memory walk log ring |
| `OPENAI_BASE_URL` | `http://localhost:20128/v1` | LLM endpoint |
| `OPENAI_API_KEY` | (required for LLM features) | API key |

## CLI flags

### `aitester run`

```bash
aitester run suite.robot [OPTIONS]
```

| Flag | Purpose |
|------|---------|
| `--headed` | Visible browser window |
| `--step-delay N` | Pause N ms after each action |
| `--base-url URL` | Override `${BASE_URL}` in the suite |
| `--output-dir DIR` | Where RF writes output.xml, log.html |
| `--engine ENGINE` | Override `${ENGINE}` (backend selection) |

### `aitester author`

```bash
aitester author --story "..." --base-url URL --out FILE [OPTIONS]
```

| Flag | Purpose |
|------|---------|
| `--story TEXT` | The intention to verify (plain English) |
| `--base-url URL` | Target application URL |
| `--out FILE` | Output `.robot` file path |
| `--debug` | Stream agent steps to stderr |
| `--max-attempts N` | Retry authoring on crash (default: 2) |

## In-suite declarations

### Backend selection

```robot
*** Variables ***
${ENGINE}    agent-browser
```

`aitester run` reads this and sets `AITESTER_BROWSER` accordingly.

### Interrupts

```robot
And I configure interrupts    dismiss=.cookie-banner
And I configure interrupts    dismiss=[role="dialog"] button.close
```

### State setup (suite-level auth)

```robot
And I configure state setup    action=open    url=http://localhost:5173/login
And I configure state setup    action=input   css=#username    value=admin
And I configure state setup    action=password    css=#password    value=secret
And I configure state setup    action=click   css=#submit
And I configure state setup    skip_when=.logged-in-marker
```

Runs once before any scenario. If `skip_when` selector is visible, setup is skipped (user already logged in).

### Per-rule configuration

```robot
I define rule "slow_page"
    And set rule timeout 60000          # 60s deadline
    And I set retry 3 delay 1000        # retry guards 3x with 1s delay
    And I set guard policy "abort"      # stop run if guard fails
    And set child scope ".container"    # children inherit this CSS prefix
    And I pause interrupts              # don't dismiss for this rule
    And screenshot on enter             # capture state on rule start
    And screenshot on fail              # capture state on failure
```
