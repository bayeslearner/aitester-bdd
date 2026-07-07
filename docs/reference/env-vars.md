# Environment Variables

Complete reference for all environment variables aitester-bdd reads.

## Runtime (walker)

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_BROWSER` | `playwright` | Backend: `playwright`, `agent-browser`, `nodriver` |
| `AITESTER_HEADED` | (unset) | `1`/`true`/`yes` = visible browser |
| `AITESTER_STEP_DELAY_MS` | `0` | Pause after each action (ms) |
| `AITESTER_RUN_TIMEOUT` | `300` | Global run timeout (seconds) |
| `AITESTER_RUN_SESSION` | auto UUID | Browser session ID override |
| `AITESTER_DISABLE_ASPECTS` | (unset) | CSV of aspects to disable (`trajectory`, `instrument`, `diagnose`, `step_delay`, `screenshot`) |
| `AITESTER_SHOT_EVERY_STEP` | (unset) | `1`/`true`/`yes` = capture a numbered PNG after every action/rule (pinned) and at each milestone (fluid). Leaves a visual trail in the output dir. |
| `AITESTER_ALLOW_STUB_BROWSER` | (unset) | `1`/`true`/`yes` = bypass the preflight that refuses to run against a stub/uninitialized browser. **Tests only** — defeats INV-4 (no silent PASS). |

## Output

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_EMIT_DIR` | RF `${OUTPUT_DIR}` or cwd | Output directory for JSONL files |
| `AITESTER_WALK_LOG_MAX` | `2000` | In-memory walk log ring size |

## LLM (diagnosis + semantic checks)

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_LLM_MODEL` | `cc/claude-opus-4-7` | Model ID. Set the **bare** name (e.g. `cc/claude-opus-4-7`); aitester normalizes it — stripping `openai/` for the langchain explore agent and adding `openai/` for the litellm judge. Setting either format works. |
| `AITESTER_AI_DIAGNOSIS` | `on` | `off` to disable LLM diagnosis |
| `OPENAI_BASE_URL` | `http://localhost:20128/v1` | LLM endpoint URL. Must be scheme+host (e.g. `http://host:port/v1`); a bare path like `/v1` is rejected up front. |
| `OPENAI_API_KEY` | `placeholder` | API key. The default placeholder works against claude-code-proxy; set a real key for other providers. A **blank** value is rejected up front. |

If any of these three is **set but blank/malformed**, the fluid agent fails
loudly at start naming the exact variable and an example — it no longer dies
deep inside an HTTP client. Leaving them **unset** uses the defaults above.

## Emit

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_EMIT_MAX_BYTES` | `2048` | Truncation limit per captured field |

## Testing / Development

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_API_BASE_URL` | `http://localhost:5175` | Base URL for `api_returns` state check |
| `AITESTER_API_TOKEN` | (unset) | Bearer token for direct API checks |
