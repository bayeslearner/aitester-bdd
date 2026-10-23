# Code quality review, 2026-10-23

An independent read-only review of `src/aitester_bdd/` (about 9,300 lines), run after a live
authoring session against a real single-page app failed three ways (spec
`04-agent-runtime-hardening-acp`). Unit tests at review time, in a scratch environment built
with `uv sync --frozen`: 56 passed, 2 failed (both from finding 5). The `playwright` and
`stealth` extras were not installed, so 7b is inferred from robotframework-browser's source.

Paths are relative to `src/aitester_bdd/`. Line numbers are as of the review, before any fix.
Disposition column: where each finding is handled.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | HIGH | `await=` never fails a step | spec 04 task 5.1 |
| 2 | HIGH | closed page or bad JS makes visible/enabled/checked pass (agent-browser) | spec 04 task 5.2 |
| 3 | HIGH | negative checks pass when the selector matches nothing | spec 04 task 5.3 |
| 4 | HIGH | actions on missing elements do nothing (nodriver, agent-browser) | spec 04 task 5.4 |
| 5 | HIGH | the default LLM setup is broken; Tailscale IP shipped as a default | spec 04 task 5.5 |
| 6 | HIGH | terminal tools do not stop the run; transcript-scan verdicts | spec 04 task 2.1 |
| 7 | MED-HIGH | secret values leak (timeout errors, Playwright fallback, argv, explore stories) | spec 04 task 5.6 |
| 8 | MEDIUM | `explore_and_author` and nodriver do not share the walker's browser | spec 04 task 5.7 |
| 9 | MEDIUM | fail-open: preflight exception, zero-rule PASS, swallowed setup steps | spec 04 task 5.8 |
| 10 | MEDIUM | dependency floors below what the code imports; litellm has no timeout | spec 04 tasks 1.1, 1.2 |
| 11 | MEDIUM | the agent's shell inherits the whole environment | spec 04 task 5.9 |
| 12 | LOW-MED | coupling to deepagents internals (TodoList patch, auto subagent) | spec 04 tasks 1.1, 2.1 |
| 13 | LOW | three copies of the cheatsheet; dead `source_root`; `last_status` unreachable | spec 04 task 5.10 |

## 1. `await=` never fails a step

`engine/walk.py:597` (`_await_after_action`) and `:1419` discard the bool returned by
`wait_for_elements_state`. All three backends return `False` on timeout instead of raising
(`agent_browser_backend.py:219`, `nodriver_backend.py:241`, `browser.py:331`).
`When I click locator "#save" await=".toast-ok"` passes when the toast never appears.
Fix: raise when the result is `False`.

## 2. A closed page or bad JS makes checks pass (agent-browser)

`evaluate_js` turns any error containing "context", "navigation" or "destroyed" into the string
`"__NAVIGATED__"` (`agent_browser_backend.py:45-48, 350-352`). `is_visible`, `is_enabled` and
`is_checked` call `bool()` on it (`:472-491`), and a non-empty string is truthy. Playwright's
error "Target page, context or browser has been closed" contains "context". The same hint list is
copied in `browser.py:124` and `nodriver_backend.py:52`. Fix: return the navigation sentinel only
from the `js` action; getters raise or retry after load.

## 3. Negative checks pass when the selector matches nothing

The getters swallow errors and return `""`, `False` or `0` (`agent_browser_backend.py:439-443,
460-464`; `browser.py:679-735`; `nodriver_backend.py:516-527`). In `walk.py:248-271`, `hidden`,
`not_contains`, `not_class` and `disabled` then pass on a mistyped selector. On agent-browser and
nodriver, `enabled` is `!({}.disabled)`, true for a missing element; nodriver's `is_visible` is
`count > 0` (`:565`), so a `display:none` element reads visible. Fix: check count > 0 first and
fail with "no element matched".

## 4. Actions on missing elements do nothing

nodriver `click`, `type`, `double_click` and `select` do nothing when `_select` returns `None`
(`nodriver_backend.py:303-306, 336-348`). agent-browser `select`, `hover`, `focus` and
`double_click` ignore a JS `false` (`agent_browser_backend.py:258-300`); `click_text` only logs a
warning. Fix: raise on no match; a backend conformance test with a missing selector.

## 5. The default LLM setup is broken

`llm/config.py:45` sets `DEFAULT_MODEL_BARE = "claude-fallback"`, but `_is_default_proxy_model`
(`:65-69`) applies the proxy URL and key only to models starting `cc/`. With nothing set, calls go
to api.openai.com with model "claude-fallback". This fails `tests/unit/test_fail_loud.py:230` and
`test_resolve_defaults_to_proxy_for_cc_model`. The default base URL is a hard-coded Tailscale IP
(`:47`) with key "placeholder", in a package published on PyPI. Fix: no shipped default endpoint;
no LLM configured means fail loud.

## 6. Terminal tools do not stop the run, and verdicts come from the transcript

The tool descriptions say "The agent loop stops" (`authoring/tools.py:189, 199`); nothing ends the
loop. Explore: `journey_complete` followed by `journey_blocked` still reports PASS
(`agent_loop.py:818`). Author: `_parse_terminal_markers` (`:392-399`) scans every message,
including model text, so an AI message echoing "AUTHORING_DONE: suite=…" counts. A suite and a
bug report can both be set; the written path is not checked against `suite_path`; `aitester
author` exits 0 after a bug report (`cli.py:95-96`). Fix: terminal state kept in Python, first
call wins, path checked, suite parsed with `robot.api.get_model`, non-zero exit on a bug report.

## 7. Secret values leak

a. On timeout the agent-browser error includes the argument list (`agent_browser_backend.py:
121-123`), password included; it reaches `walk.py:847-855`, the RF `AssertionError` and log, and
`_run_state_setup`'s `log.warning` (`walk.py:1745`).
b. Playwright: if `type_secret` raises, the code falls back to `fill_text` (`browser.py:437-441`),
which robotframework-browser logs at INFO (inferred; extra not installed).
c. agent-browser and nodriver ignore `secret` (`agent_browser_backend.py:267`,
`nodriver_backend.py:336`); the value is on the process command line.
d. `I explore "… ${PW}"` sends the resolved value to the LLM, prints it (hard-coded
`debug=True`, `walk.py:903, 914`) and logs notes with `html=True` (`walk.py:922`), which also lets
page text inject HTML into `log.html`.
Clean: walk_log entries (`walk_log.py:192-201`), the diagnose prompt (`:330-337`), emit records.
Fix: a redacting value type used in every backend's command and error text; no Playwright
fallback; mask registered secrets in explore stories; drop `html=True`.

## 8. Browser session handling outside plain explore

`explore_and_author` inside Robot builds its own session (`agent_loop.py:508-509`), so it starts
signed out, against its docstring. With nodriver, `getattr(browser, "_session", None)`
(`walk.py:883`) is `None` and explore starts a fresh agent-browser browser. agent-browser `close()`
runs only if `_opened` (`:166-171`), so a daemon is left running when the agent opened the page.
The `I explore` docstring advertises an unread `session=`. Fix: pass the backend or session
explicitly; refuse explore on backends that cannot share their browser.

## 9. Other fail-open places

A `preflight()` that raises counts as OK (`walk.py:1696-1700`). `Verdict.passed` is `all([])`,
true for zero rules (`verdict.py:36`). `_run_state_setup` swallows failed login steps
(`walk.py:1744`). `_dismiss`, `clear_state`, `capture_field` use bare `except: pass`.

## 10. Dependency floors and timeouts

`langchain>=0.3`, but `langchain.agents.middleware.types` exists only in 1.x. The deepagents floor
predates `LocalShellBackend`. `httpx` is imported (`walk.py:452`) but undeclared.
`litellm.completion` gets no timeout (`llm/aiagent_adapter.py:104-115`). The author's
timeout/retries apply only on the openai provider path (`agent_loop.py:370-372`).

## 11. The agent's shell inherits the whole environment

`LocalShellBackend(inherit_env=True, env=dict(os.environ))` (`agent_loop.py:508-517, 714-722`)
gives a page-steered model a shell holding every secret in the environment. Fix: an allowlisted
environment, or typed browser tools only.

## 12. Coupling to deepagents internals

The TodoList patch replaces a module global that only 0.6 reads. deepagents adds a
general-purpose subagent that receives the terminal tools; its calls never appear in the parent's
messages. `result["todos"]` and the `LocalShellBackend` signature are internals. Fix:
`subagents=[]`, explicit middleware, terminal state outside the transcript.

## 13. Duplicated and dead paths

The cheatsheet exists three times (`agent_loop.py:51-66, 536-556, 763-776`), the nav-hint list
three times. `_is_inside_rf()` picks tools by whether the Browser library is loaded, not by the
engine in use. `build_tools(source_root)` ignores `source_root`. `last_status` cannot pass on
agent-browser or nodriver: `record_response` has no caller.

## Where an ACP author replaces deepagents

The swap point is `_author_once` and `explore_with_agent` in `authoring/agent_loop.py`.
`_build_llm`, the TodoList patch and `_summarize_todos` go away on that path;
`_invoke_with_debug_stream` becomes a consumer of `session/update`. The tools in
`authoring/tools.py` become an MCP server given in `session/new`, with terminal state kept in
Python (which also fixes 6). `playwright_tools.py` would need an HTTP MCP server inside the Robot
process. `walk.py:_walk_explore_rule` stays the caller with a small adapter.
