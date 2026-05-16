# Environment Variables

Complete reference for all environment variables aitester-bdd reads.

## Runtime (walker)

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_BROWSER` | `agent-browser` | Backend: `agent-browser`, `playwright`, `nodriver` |
| `AITESTER_HEADED` | (unset) | `1`/`true`/`yes` = visible browser |
| `AITESTER_STEP_DELAY_MS` | `0` | Pause after each action (ms) |
| `AITESTER_RUN_TIMEOUT` | `300` | Global run timeout (seconds) |
| `AITESTER_RUN_SESSION` | auto UUID | Browser session ID override |
| `AITESTER_DISABLE_ASPECTS` | (unset) | CSV of aspects to disable |

## Output

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_EMIT_DIR` | RF `${OUTPUT_DIR}` or cwd | Output directory for JSONL files |
| `AITESTER_WALK_LOG_MAX` | `2000` | In-memory walk log ring size |

## LLM (diagnosis + semantic checks)

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_LLM_MODEL` | `cc/claude-opus-4-7` | Model ID for litellm |
| `AITESTER_AI_DIAGNOSIS` | `on` | `off` to disable LLM diagnosis |
| `OPENAI_BASE_URL` | `http://localhost:20128/v1` | LLM endpoint URL |
| `OPENAI_API_KEY` | (required) | API key for LLM calls |

## Emit

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_EMIT_MAX_BYTES` | `2048` | Truncation limit per captured field |

## Testing / Development

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_API_BASE_URL` | `http://localhost:5175` | Base URL for `api_returns` state check |
| `AITESTER_API_TOKEN` | (unset) | Bearer token for direct API checks |
