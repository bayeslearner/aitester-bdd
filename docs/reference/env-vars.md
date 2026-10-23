# Environment Variables

Complete reference for all environment variables aitester-bdd reads.

## Runtime (walker)

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_BROWSER` | `playwright` | Backend: `playwright`, `agent-browser`, `nodriver` |
| `AITESTER_HEADED` | (unset) | `1`/`true`/`yes` = visible browser |
| `AITESTER_STEP_DELAY_MS` | `0` | Pause after each action (ms) |
| `AITESTER_RUN_TIMEOUT` | `0` | Run budget in seconds; 0 = none. Rules past it are reported as not run. A suite's `And I set run timeout N s` wins |
| `AITESTER_ALLOW_SHELL` | (unset) | `1` lets a suite's `shell` actions run at replay; refused otherwise |
| `AITESTER_ALLOWED_ORIGINS` | (unset) | Comma-separated origins the authoring agent may `open` besides the app under test (a sign-in host) |
| `AITESTER_RUN_SESSION` | auto UUID | Browser session ID override |
| `AITESTER_DISABLE_ASPECTS` | (unset) | CSV of aspects to disable (`trajectory`, `instrument`, `diagnose`, `step_delay`, `screenshot`) |
| `AITESTER_SHOT_EVERY_STEP` | (unset) | `1`/`true`/`yes` = capture a numbered PNG after every action/rule (pinned) and at each milestone (fluid). Leaves a visual trail in the output dir. |
| `AITESTER_ALLOW_STUB_BROWSER` | (unset) | `1`/`true`/`yes` = bypass the preflight that refuses to run against a stub/uninitialized browser. **Tests only** — defeats INV-4 (no silent PASS). |

## Output

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_EMIT_DIR` | RF `${OUTPUT_DIR}` or cwd | Output directory for JSONL files |
| `AITESTER_WALK_LOG_MAX` | `2000` | In-memory walk log ring size |

## LLM (fluid tests, diagnosis + semantic checks)

aitester-bdd is provider-agnostic — it depends on **litellm** (multi-provider)
and **langchain-openai** (the OpenAI *protocol* client), not on any vendor SDK.
Its own config uses **neutral, aitester-owned** names:

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_LLM_MODEL` | (none; required) | Model spec. Set the **bare** name; aitester normalizes it (strips `openai/` for the langchain explore agent, adds `openai/` for the litellm judge). Authoring and fluid steps refuse to start without it. |
| `AITESTER_LLM_BASE_URL` | (unset) | LLM endpoint URL for an OpenAI-compatible gateway. Must be scheme+host (e.g. `https://gateway.example.com/v1`); a bare path like `/v1` is rejected up front. |
| `AITESTER_LLM_API_KEY` | (unset) | Credential for that gateway. A **blank** value is rejected up front. |
| `AITESTER_AI_DIAGNOSIS` | `on` | `off` to disable LLM diagnosis |
| `AITESTER_LLM_REASONING_EFFORT` | (unset) | Sent as `reasoning_effort` on OpenAI-compatible providers; some gateways need `none` for newer models to call tools over chat completions |
| `AITESTER_LLM_TIMEOUT` | `60` | Seconds one explore/author model call may take before it is retried |
| `AITESTER_LLM_MAX_RETRIES` | `3` | Retries per explore/author model call; each retry prints a `[author] model call:` line |
| `AITESTER_AGENT_ENV` | (unset) | Comma-separated extra variables the agent's shell may see. By default it gets only `PATH`, `HOME`, locale, `TMPDIR` and `AGENT_BROWSER_*`, never API keys or test secrets |

**Resolution precedence** (per value): explicit arg (`--llm-model` / `--llm-base-url`
/ `--llm-api-key`, or the `llm_*` kwargs on `explore_with_agent` /
`author_with_agent`) → `AITESTER_LLM_*` → legacy `OPENAI_BASE_URL` /
`OPENAI_API_KEY` (**deprecated**, still honored) → otherwise **left unset so
the provider resolves creds from its own native env** (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, …). There is no shipped default model
or endpoint.

**Multi-provider.** Both LLM paths are provider-agnostic. The model spec uses a
litellm-style `provider/model` prefix; the default `cc/…` (no prefix) is treated
as an OpenAI-compatible endpoint. The fluid agent uses LangChain's
`init_chat_model`, so a **native** non-OpenAI provider needs its integration
package — install the extra and set the model:

| Provider | Install | Model example |
|----------|---------|---------------|
| OpenAI-compatible (default) | (base install) | `cc/claude-opus-4-7`, `openai/gpt-4o` |
| Anthropic (native) | `pip install aitester-bdd[anthropic]` | `anthropic/claude-opus-4-8` |
| Google Gemini (native) | `pip install aitester-bdd[google]` | `gemini/gemini-2.0-flash` |

Any other LangChain-supported provider works too — install its
`langchain-<provider>` package and use the matching `provider/model` prefix.

If any LLM var is **set but blank/malformed**, the fluid agent fails loudly at
start naming the exact variable and an example — it no longer dies deep inside
an HTTP client. Leaving them **unset** uses the precedence above.

## Emit

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_EMIT_MAX_BYTES` | `2048` | Truncation limit per captured field |

## Testing / Development

| Variable | Default | Description |
|----------|---------|-------------|
| `AITESTER_API_BASE_URL` | `http://localhost:5175` | Base URL for `api_returns` state check |
| `AITESTER_API_TOKEN` | (unset) | Bearer token for direct API checks |
