# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.2] - 2026-07-07

Make the fluid agent provider-agnostic and delete dead authoring code —
resolving the split where the agent half was OpenAI-protocol-locked while
litellm advertised multi-provider.

### Changed

- **Fluid explore/author agent is now provider-agnostic.** `_build_llm` uses
  LangChain's `init_chat_model` instead of a hardcoded `ChatOpenAI`, so the
  agent can run on any LangChain provider (OpenAI-compatible proxies, Anthropic,
  Google, Bedrock, Ollama, …). The provider is derived from the model spec's
  litellm-style prefix; a bare/`cc/…` model is an OpenAI-compatible endpoint.
- The in-walker judge/diagnose one-shots stay on litellm (unchanged) — both LLM
  paths are now multi-provider.

### Added

- `resolve_chat_model` / `split_provider` in `llm.config` — map a litellm-style
  `provider/model` spec to a LangChain `(provider, model)` pair.
- Optional provider extras: `aitester-bdd[anthropic]`, `aitester-bdd[google]`
  (native non-OpenAI providers for the fluid agent).

### Removed

- Dead authoring code in `AIAgentLLM`: `author` / `refine` / `ground_selector`
  methods, their system prompts, and `_strip_fences` — all superseded by the
  deepagents authoring loop and called nowhere. The `LLMClient` Protocol is
  slimmed to the in-walker one-shots (judge/judge_visual/diagnose) it actually
  describes. Orphaned `DEFAULT_*` constants removed.

## [0.4.1] - 2026-07-07

Provider-neutral LLM config + an enforced backend contract.

### Added

- **`BrowserBackend` Protocol** (`engine/browser.py`) — the single source of
  truth for the surface every backend must implement, mirroring the
  `llm.base.LLMClient` idiom. A conformance test derives the surface from the
  Protocol and asserts each backend (`_PlaywrightBackend`, `AgentBrowserBackend`,
  `NodriverBackend`) implements it — so a future surface method (the next
  `preflight`) can't be added to one backend and silently forgotten on another.
- **Neutral LLM env vars** — `AITESTER_LLM_BASE_URL` / `AITESTER_LLM_API_KEY`
  (aitester owns them; the product depends on litellm, not on OpenAI/Anthropic).
  Legacy `OPENAI_BASE_URL` / `OPENAI_API_KEY` still honored (deprecated).
- **Explicit LLM arg passing** — `--llm-model` / `--llm-base-url` / `--llm-api-key`
  on `aitester author`, and `llm_model` / `llm_base_url` / `llm_api_key` kwargs on
  `explore_with_agent` / `author_with_agent`.
- **litellm-native env fallback** — for any non-`cc/…` model, base_url/api_key are
  left unset so litellm / ChatOpenAI resolve creds from their own provider env
  (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, …).

### Changed

- LLM config resolves through `resolve_llm_config` (explicit arg → neutral env →
  legacy env → proxy default / provider-native). The litellm adapter passes
  `api_base`/`api_key` directly to `completion` instead of mutating global env.
- `validate_llm_env` now covers the neutral names too.

## [0.4.0] - 2026-07-07

Honesty & legibility pass — the harness can no longer silently lie about its
own verdict, its failures name their fix, and the happy path is documented.
None of these changes constrain what a consuming agent may do with a suite;
they make the right path obvious and misuse self-diagnosing.

### Fixed

- **NullBrowser silent-pass trap (INV-4).** `walk_verification` now calls each
  backend's `preflight()` before any scenario and **refuses to run** against a
  stub/uninitialized browser (RF-Browser not initialized, `agent-browser` CLI
  missing, no Chrome/Edge for nodriver) — raising `NullBrowserError` with a
  one-line remedy instead of reporting PASS having done nothing. Bypass with
  `AITESTER_ALLOW_STUB_BROWSER=1` (tests only).
- **`BrowserAdapter` docstring / doctor mismatch.** Docstrings and `aitester
  doctor` said `agent-browser` was the default while the code defaults to
  `playwright`. Now consistent (`playwright` is the default).
- **`When I take screenshot` wrote to CWD** unless given an absolute path — now
  defaults into the RF output dir.

### Added

- **`preflight()` on every backend** — `(ok, reason)` health check used by the
  fail-loud gate above.
- **LLM config validation** — blank/malformed `AITESTER_LLM_MODEL` /
  `OPENAI_BASE_URL` / `OPENAI_API_KEY` (e.g. a base URL that is just `/v1`) now
  fail loudly at fluid-run start, naming the exact variable and an example
  value, instead of dying deep in an HTTP client.
- **Model-prefix normalization** — one `AITESTER_LLM_MODEL` value works for both
  the langchain explore agent (wants bare `cc/...`) and the litellm judge (wants
  `openai/cc/...`); aitester strips/adds the `openai/` prefix per consumer.
- **`aitester doctor` upgrades** — reports the Python interpreter + flags a dead
  venv; runs an **agent-browser command-shape smoke test** (`open`,
  `snapshot -c -i --json`, `get count/text`, `click`, `type`, `press`,
  `screenshot`) against a local `data:` URL to catch CLI drift. `--no-smoke`
  skips it for headless CI.
- **Screenshot trail** — `AITESTER_SHOT_EVERY_STEP=1` captures a numbered PNG
  after every action/rule (pinned walk, via a new `screenshot` aspect) and at
  each milestone (fluid explore, via a `browser_screenshot` tool + prompt).
- **Docs** — new "Running a Suite, Start to Finish" guide: env contract, the
  two modes, the doctor, the screenshot trail, and the top failure messages
  with their fixes. env-vars reference updated.

## [0.3.0] - 2026-05-20

### Changed

- **Default runtime backend: `playwright`** (was `agent-browser`). Consistent engine for pinned and fluid tests. Reliable `get_text`, native Playwright waits, in-process speed. Requires `aitester init-browser` on first run.
- **Guard timeout: 10s** (was 200ms). Matches upstream WISE RPA BDD's `wait_for_elements_state("attached", "10s")`. Guards now wait for SPA hydration.
- **Text observations poll** — `has_text`, `contains`, `matches`, `not_contains` now poll until match or timeout (was single read). Catches post-navigation text changes.

### Added

- **Playwright explore tools** — when running inside RF, `I explore` uses typed Python tools (`browser_click`, `browser_get_text`, `browser_snapshot`, etc.) that call the same RF Browser instance the walker uses. No subprocess, no session handoff. Mixed suites (pinned login → fluid explore) share one browser session.
- **Auto-import Browser library** — suites don't need `Library Browser` when using the `playwright` backend. The walker auto-imports it via `BuiltIn().import_library("Browser")`.
- **JS-level wait fallback** — `wait_for_elements_state` falls back to in-page JS polling for SPA apps where hash routing creates elements after initial page load.
- **`fill_secret` / `type_secret` handling** — RF Browser API compatibility for secret password inputs.

### Fixed

- `has_text` observation after navigation returned stale text from the previous view (single read, no poll).
- Guard timeout too short (200ms) for SPA route transitions — elements appeared after guards timed out.
- `type secret` keyword failed on Playwright backend (`fill_text` doesn't accept `secret` kwarg).

## [0.2.0] - 2026-05-16

### Added

- **`I explore` keyword** — fluid LLM-driven test execution within the rule DAG. The walker hands its browser session to the agent loop at topo-sort time; no separate browser lifecycle.
- **`I explore and author` keyword** — same as explore, but also writes a pinned `.robot` suite from the journey.
- **`I ask LLM` action + `llm_response_contains` / `llm_response_semantic` state checks** — interact with LLMs as a plan-phase action (deferred execution, not immediate).
- **WalkContext dataclass** — centralizes runtime configuration (headed, step_delay_ms, run_timeout_s, disabled_aspects). Replaces scattered `os.environ.get()` calls.
- **`step_delay` aspect** — step delay is now a proper AOP aspect (fires via `after_action` hook), not an inline `time.sleep`.
- **`--headed` and `--step-delay` CLI flags** on `aitester run` for visual observation.
- **Three runtime backends** — `agent-browser` (default, zero-install), `playwright` (in-process speed), `nodriver` (bot-detection-resistant). Declared via `${ENGINE}` variable in the suite.
- **Session isolation** — each adapter instance gets its own session UUID; cookies never leak between test runs or authoring sessions.
- **Scenario isolation** — `clear_state()` between scenarios so each Robot test case starts clean.
- **`state_setup` configuration** — suite-level auth/consent actions that run once before any scenario.
- **Quality gates** — `min_records`, `filled_pct`, `max_failed_pct` assertions on captured artifacts.
- **Expansion (TIER 2)** — parametric capture over elements or Cartesian combinations.
- **`visual_semantic` state check** — multimodal screenshot-to-LLM judge.
- **Shell action + assertions** — `When I run shell`, `Then last shell exit`, stdout/stderr checks.
- **GitHub Actions CI** — lint + test on Python 3.11/3.12/3.13, build verification, docs deployment.
- **`py.typed` marker** — enables downstream type checking.

### Changed

- **Headed mode now works for all backends** — previously the walker always passed `headless=True` regardless of env var. Now `WalkContext.headed` flows correctly to `BrowserAdapter.new_session()`.
- **Aspect disabling centralized** — `AITESTER_DISABLE_ASPECTS` is read once at `WalkContext` construction, not per-registry-build.

### Fixed

- Duplicate `SKILL.md` in wheel (force-include removed; `packages` directive already includes it).
- Test suite: `declare_parents` → `and_declare_parents`, `set_rule_timeout` → `and_set_rule_timeout` renames propagated to all tests.
- 138 lint errors resolved (unused imports, `Optional` → `X | None`, import ordering, undefined forward refs).

## [0.1.0] - 2026-04-01

### Added

- Initial release: keyword library, walker, BrowserAdapter, AspectRegistry, trajectory/instrument/diagnose aspects.
- Authoring agent loop (DeepAgents + LangGraph) with `aitester author` CLI.
- `aitester run` CLI for executing authored suites.
- Rule DAG with parent-child composition, guards, retry-redo, interrupt dismissal.
- SKILL.md grammar reference for the authoring agent.
- Wikipedia quickstart example.
