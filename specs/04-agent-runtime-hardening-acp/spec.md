---
spec_id: 04-agent-runtime-hardening-acp
status: DRAFT
closed_as: null
since: 2026-10-23
until: null
epic: authoring
features: [deepagents-07-support, llm-call-budget, author-progress-line, ui-navigation-before-bug, acp-external-agent]
supersedes: []
superseded_by: null
depends_on: []
anchors:
  - docs/internals/authoring.md
  - docs/internals/exploration-driver-map.md
---

# Authoring runtime: current deepagents, honest progress, and external agents over ACP

## Why

On 2026-10-23 `aitester author` was pointed at a real single-page app (Archestra 1.4.0-rc.55,
signed in, on a lab host) with UMGPT as the model. Three things went wrong before any test was
written:

1. A fresh install crashed at once: `AttributeError: module 'deepagents.graph' has no attribute
   'TodoListMiddleware'`. `pyproject.toml` accepts `deepagents>=0.0.15`; 0.7 removed the class
   from its default stack, and `_maybe_disable_todo_middleware` patches it
   [src:src/aitester_bdd/authoring/agent_loop.py:127].
2. The first run sat for 7 minutes on one model call and printed nothing. Each call waits up to
   120 s and retries up to 8 times [src:src/aitester_bdd/authoring/agent_loop.py:370]; progress
   is printed only with `--debug`.
3. The second run spent 60 steps and filed a bug report: typing `/llm/logs` redirected to `/chat`.
   The page was one click away through the app's own sidebar (Studio, then Logs).

The owner also asked for the agent loop to work with external agents over ACP (Agent Client
Protocol), so the author can be Claude Code, Codex or another ACP agent instead of the in-process
deepagents loop.

## Mental model and invariants

- **Author** = an agent that uses the live app through a browser and ends with exactly one
  terminal act: write the `.robot` suite, or write a bug report.
- **Runtime** = Robot Framework running the suite; pinned lines need no LLM.
- Invariant: every selector in a suite was observed on the live page.
- Invariant: a value typed with `secret` never reaches a log, an emitted file or a model prompt.
- Invariant: a bug report means the app is broken, not that one route to a page failed.

## Requirements

### R1 — deepagents 0.7

WHEN aitester is installed fresh, THE authoring loop SHALL run on deepagents 0.7.x without
patching deepagents internals. Planning (`AITESTER_PLANNING`) adds langchain's
`TodoListMiddleware` explicitly when on and adds nothing when off. `pyproject.toml` states a
tested lower and upper bound for deepagents, langgraph and langchain.

### R2 — bounded model calls

THE model client SHALL wait at most `AITESTER_LLM_TIMEOUT` seconds per call (default 60) and
retry at most `AITESTER_LLM_MAX_RETRIES` times (default 3).

### R3 — progress without --debug

WHILE `aitester author` runs, THE CLI SHALL print one line per agent step (step number, tool,
elapsed seconds) to stderr, and SHALL print a line when a model call times out or is retried.
`--debug` keeps its full stream.

### R4 — navigate through the UI before reporting a bug

WHEN a typed URL redirects or a page seems missing, THE author SHALL try the app's own
navigation (sidebar, menus, mode toggles, links) before concluding the page is unreachable, and
the bug report SHALL list the UI paths it tried.

### R5 — external authors over ACP

WHEN `--agent acp:<command>` is given (for example `acp:npx @agentclientprotocol/claude-agent-acp`
or `acp:codex-acp`), THE author SHALL run as an ACP client:

- start the agent as a subprocess over stdio;
- open a session with the working directory and one MCP server that aitester provides;
- send the same story prompt as the deepagents path;
- end when the agent calls one of aitester's terminal tools.

The MCP server exposes the terminal tools (`write_robot_suite`, `report_bug`) and the browser
commands the cheatsheet lists, so the external agent needs no shell access to drive the browser.
Permission requests from the agent are answered by a fixed policy: allow aitester's own MCP
tools, deny everything else.

### R6 — one interface for both authors

THE CLI and the in-Robot fluid path SHALL call one `Author` interface with two implementations
(deepagents, ACP), returning the same result type (suite path or bug report path, transcript,
step count, elapsed time).

## Non-functional

- No change to `.robot` output format or runtime keywords.
- The deepagents path stays the default; ACP is opt-in.
- Secrets typed during exploration are passed by environment variable name, never in the prompt.

## Out of scope

- Removing a browser backend (spec 03 P1).
- Moving `specs/` to `docs/specs/` (spec 03 P0 reconciles lifecycle).

## Design

### Components

```text
cli.author ──► Author (protocol)
                 ├─ DeepAgentsAuthor  (agent_loop.py, in-process; deepagents 0.7)
                 └─ AcpAuthor         (new authoring/acp_author.py; acp 0.12 client)
                        └─ spawns external agent ── MCP stdio ──► authoring/mcp_tools.py
                                                                    (browser cmds + terminal tools)
```

`authoring/tools.py` already holds the terminal tools as plain functions; the MCP server wraps the
same functions, so both authors share one implementation.

### ACP session flow

1. `spawn_agent_process(client, command, *args, env=…, cwd=workdir)`.
2. `initialize` (protocol version, client capabilities: no fs, no terminal).
3. `session/new` with `cwd=workdir`, `mcpServers=[{name: "aitester", command: sys.executable,
   args: ["-m", "aitester_bdd.authoring.mcp_tools", "--session", <browser session>]}]`.
4. `session/prompt` with the story prompt.
5. Stream `session/update` notifications to the R3 progress line.
6. `session/request_permission`: allow tools whose name starts with `aitester`, deny others.
7. Finish when the MCP server records a terminal call (a marker file in the workdir), or when
   the prompt turn ends; no terminal call means authoring failed (not a silent pass).

### Model routing for external agents

The external agent brings its own model client. `--agent-env` passes named variables through to
the subprocess, so a deployment's gateway is chosen by configuration, not code. Checked
2026-10-23 against UMGPT (`https://api.toolkit.umgpt.umich.edu`): `POST /v1/messages` (Anthropic
Messages) and `POST /v1/responses` (OpenAI Responses) both answered 200. So Claude Code over ACP
runs with `ANTHROPIC_BASE_URL` and `ANTHROPIC_API_KEY` set to that gateway, and Codex with its
OpenAI-compatible base URL.

### Failure handling

- Agent process exits or the protocol errors: the author returns failed with stderr captured.
- Per-turn wall clock: `AITESTER_AUTHOR_TIMEOUT` (default 900 s), then `session/cancel`.

## Verification

- `uv run pytest tests/unit -q` passes on deepagents 0.7.31 and on the lower bound.
- A unit test for R1: planning off builds no `write_todos` tool; planning on builds it.
- A unit test for R2/R3 with a fake model that sleeps past the timeout: one retry line printed.
- Live check (R4): the Archestra log-search story writes a suite, and `aitester run` passes it.
- Live check (R5): the same story through `--agent acp:…` with one external agent.

## Tasks

- [ ] 1. Foundation
  - [x] 1.1 Pin deepagents/langgraph/langchain to tested ranges; remove the TodoList patch; add
        TodoListMiddleware explicitly when planning is on (R1). Verification: unit tests + fresh
        `uv tool install`.
  - [x] 1.2 Timeout and retry knobs with defaults 60 s / 3 (R2).
  - [x] 1.3 Per-step progress line and retry/timeout lines without `--debug` (R3).
  - [x] 1.4 Prompt rule and `report_bug` description for UI navigation first (R4).
- [ ] 2. Core
  - [ ] 2.1 `Author` protocol and `DeepAgentsAuthor` around the current loop (R6).
  - [x] 2.2 `mcp_tools.py`: MCP stdio server over the terminal tools and browser commands (R5).
  - [ ] 2.3 `AcpAuthor` with the session flow and permission policy above (R5).
  - [x] 2.4 `--agent` CLI option; `acp` extra in `pyproject.toml` (R5).
- [ ] 3. Tests
  - [ ] 3.1 Unit tests for 1.1–1.3 ([x], `tests/unit/test_agent_runtime.py`) and the permission policy.
  - [ ] 3.2 Live: Archestra log-search story, deepagents author (R4).
  - [ ] 3.3 Live: same story, ACP author.
- [ ] 4. Docs
  - [ ] 4.1 `docs/reference/env-vars.md`, `docs/internals/authoring.md`, README backends section.
  - [ ] 4.2 Code review findings: each fixed here or filed as an issue.
- [ ] 5. Fail-closed hardening (from `docs/history/review-2026-10-23/03-CODE_QUALITY.md`; R7)
  - [x] 5.1 `await=` fails the step when the wait returns False (finding 1).
  - [x] 5.2 Navigation sentinel only from the `js` action; getters raise (finding 2).
  - [x] 5.3 State checks fail with "no element matched" on zero matches (finding 3).
  - [x] 5.4 Actions raise on no match on every backend; conformance test (finding 4).
  - [x] 5.5 No shipped default endpoint; unconfigured LLM fails loud; fix the 2 failing tests (finding 5).
  - [ ] 5.6 Secret redaction in commands and errors; no Playwright fallback; no `html=True` notes (finding 7).
        Done: error/log redaction, no fallback, plain-text notes, explore debug opt-in. Open: the value
        still travels on agent-browser's argv (7c), and secrets resolved into an `I explore` story
        still reach the model (7d) — issues to file.
  - [ ] 5.7 Explore shares the walker's browser or refuses (finding 8).
  - [x] 5.8 Preflight exceptions, zero-rule verdicts and failed setup steps fail (finding 9).
  - [x] 5.9 Allowlisted environment for the agent's shell (finding 11).
  - [x] 5.10 One cheatsheet; remove dead `source_root` (finding 13). The explore system
        prompt keeps its short quick-reference; the two user messages share one constant.

### R7 — fail closed

A pinned step SHALL pass only when its check ran against at least one matched element and held.
A missing element, a closed page, a timed-out wait, a failed setup step, a preflight error or a
suite with zero rules SHALL fail with a message saying which.

## Log

- 2026-10-23: drafted from the Archestra run.
- 2026-10-23: independent review landed (13 findings, 56/58 unit tests passing); R7 and task 5
  added. Task 2.1 also covers finding 6 (terminal state kept in Python).
- 2026-10-23: tasks 1.1–1.4, 5.5, 5.9, 5.10 done; terminal state moved into Python for both
  author and explore (`TerminalState` + `stop_when_done` middleware; first successful call wins,
  an unparseable suite returns an error and the loop continues). `return_direct` was tried first
  and dropped: it also ended the run on a rejected suite. `aitester author` now exits 2 after a
  bug report. Unit tests: 72 passed on deepagents 0.7.31 / langchain 1.4.7 (scratch env from
  `uv sync --frozen`). The repo has no git metadata on this Mac; nothing committed.
- 2026-10-23: tasks 2.2, 2.4, 5.1–5.4, 5.8 done; 5.6 partly. 108 unit tests pass with the [acp]
  extra (new: `test_agent_runtime.py`, `test_fail_closed.py`, `test_acp_author.py`). The tests'
  FakeBrowser now reports an element that has text as present, as a real page does.
- 2026-10-23 live (Archestra 1.4.0-rc.55, UMGPT `claude-sonnet-5-5`): the deepagents author found
  Studio → Logs by itself and wrote `log_search.robot` in 613 s (R4 holds). `aitester run` of that
  suite failed honestly at `await=a[href='/llm/logs']` after the Studio click (R7 / finding 1
  working; before this sprint the step would have passed). The runtime cannot switch the Studio
  toggle: text locators find no "Studio", a synthetic JS click and a CDP mouse click both leave the
  sidebar in AI mode, and refs from one `snapshot` were "unknown" to the next command. Suspected
  cause: `AGENT_BROWSER_STATE` replaying saved storage on every CLI call; not yet settled.
- 2026-10-23 live ACP (`claude-agent-acp@0.95.0`): the session opens. The model gateway rejects
  `x-api-key` (ANTHROPIC_API_KEY, 401) and ACP gateway auth sends a placeholder Bearer over the
  custom header (401); ANTHROPIC_AUTH_TOKEN (Bearer) works. Gateway-auth support stays in
  `acp_author.py` for gateways that take the key in a custom header. Run 3: Claude Code made 45
  tool calls, all through `mcp__aitester__browser` except one ToolSearch, then `report_bug` after
  246 s; the report listed each UI path it tried (R4) and `aitester author` exited 2. R5 holds end
  to end; it hit the same Studio-toggle wall as below.
- 2026-10-23 the Studio-toggle wall settled: the toggle does nothing when clicked before the page
  hydrates. Signed in through the form, waiting 3 s, then clicking the toggle by snapshot ref, the
  Logs link appears. App timing, not an aitester defect; suites click it under a rule retry
  (`I set retry`). The earlier "unknown ref" errors came from the same early clicks.

