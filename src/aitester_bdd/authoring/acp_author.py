"""Author with an external agent over ACP (Agent Client Protocol), spec 04 R5.

aitester is the ACP client. It starts the agent (Claude Code through
`claude-agent-acp`, Codex through `codex-acp`, or any ACP agent) as a
subprocess over stdio, opens one session whose only extra tools are
aitester's MCP server (`mcp_tools.py`: the browser plus the two terminal
tools), sends the story, and reads the terminal outcome from the state
file the MCP server writes.

Permission policy, fixed: tool calls on aitester's own MCP server are
allowed; every other tool the agent asks to run (its shell, file edits,
web fetch) is rejected. The client advertises no file-system or terminal
capability, so the agent cannot use the client for either.

The agent brings its own model client. Two ways to point it at a gateway:

  - ACP gateway authentication, for agents that offer it (claude-agent-acp
    does): set AITESTER_ACP_GATEWAY_URL and AITESTER_ACP_GATEWAY_KEY. The
    client then advertises gateway auth and calls `authenticate("gateway")`
    with the URL and an `Authorization: Bearer` header; the key goes over
    the protocol, not into the agent's environment.
  - Environment: name the variables the agent reads (for Codex, its
    OpenAI-compatible base URL and key) in AITESTER_AGENT_ENV.

Nothing else from the caller's environment reaches the agent.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from aitester_bdd.authoring.agent_loop import (
    AuthoringResult,
    _agent_env,
    _NAVIGATION_RULE,
    _slugify,
    load_skill,
)
from aitester_bdd.authoring.mcp_tools import read_terminal
from aitester_bdd.authoring.tools import session_id

_MCP_SERVER_NAME = "aitester"

_BROWSER_HELP = (
    "## The browser tool\n\n"
    "Every browser action is one call to the `browser` tool with an agent-browser "
    "command line (no `agent-browser` prefix needed):\n\n"
    "```\n"
    "open <url>\nsnapshot -c -i            # compact, interactive elements, with @refs\n"
    "get count '<css>'\nget text '<css>'\nget attr '<css>' <name>\n"
    "click '<css|@ref>'\nfill '<css>' '<text>'\npress <key>\n"
    "wait '<css>'|<ms>\neval '<js>'\nfind role button click --name 'Save'\n"
    "```\n\n"
    "Refs (@e3) change after every page change: snapshot again before using one.\n\n"
)


def allow_tool_call(title: str | None, raw_name: str | None = None) -> bool:
    """The fixed permission policy: only aitester's own MCP tools run."""
    for name in (raw_name or "", title or ""):
        n = name.lower()
        if n.startswith(f"mcp__{_MCP_SERVER_NAME}__") or n.startswith(f"{_MCP_SERVER_NAME}:") \
                or n.startswith(f"{_MCP_SERVER_NAME}/"):
            return True
    return False


def build_prompt(*, story: str, base_url: str, engine: str) -> str:
    return (
        load_skill()
        + "\n\n---\n\n"
        + f"Story: {story}\n\nBase URL: {base_url}\n\n"
        "You are authoring an aitester-bdd .robot test suite for this story. Use only "
        f"the `{_MCP_SERVER_NAME}` tools; other tools are refused.\n\n"
        + _BROWSER_HELP
        + "## Rules\n\n"
        "  - Every selector in the .robot must come from a real attribute observed on the live page — never invent.\n"
        "  - Stop exploring as soon as every selector is grounded, then write the suite.\n"
        f"  - Declare ${{ENGINE}}    {engine} in the *** Variables *** section.\n"
        + _NAVIGATION_RULE
        + "  - If the app is broken in a way that prevents authoring, call report_bug.\n\n"
        "Finish by calling write_robot_suite with the suite body, or report_bug. Then stop.\n"
    )


class _Client:
    """ACP client callbacks: progress lines and the permission policy."""

    def __init__(self, *, debug: bool) -> None:
        self.debug = debug
        self.steps = 0
        self.t0 = time.monotonic()
        self.refused: list[str] = []

    def _line(self, text: str) -> None:
        print(f"[author/acp] {text} +{time.monotonic() - self.t0:.0f}s", file=sys.stderr, flush=True)

    async def request_permission(self, session_id: str, tool_call: Any, options: list, **kwargs: Any):
        from acp.schema import AllowedOutcome, DeniedOutcome, RequestPermissionResponse

        title = getattr(tool_call, "title", None)
        raw = None
        raw_input = getattr(tool_call, "raw_input", None)
        if isinstance(raw_input, dict):
            raw = raw_input.get("tool_name") or raw_input.get("name")
        want = ("allow_once", "allow_always") if allow_tool_call(title, raw) else ("reject_once", "reject_always")
        if want[0] == "reject_once":
            self.refused.append(title or raw or "?")
            self._line(f"refused tool: {title or raw}")
        for opt in options:
            if getattr(opt, "kind", None) in want:
                return RequestPermissionResponse(outcome=AllowedOutcome(outcome="selected", option_id=opt.option_id))
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        kind = getattr(update, "session_update", "")
        if kind == "tool_call":
            self.steps += 1
            self._line(f"step {self.steps} {getattr(update, 'title', '') or ''}")
        elif self.debug and kind in ("agent_message_chunk", "agent_thought_chunk"):
            content = getattr(update, "content", None)
            text = getattr(content, "text", "") if content is not None else ""
            if text.strip():
                print(text, end="", file=sys.stderr, flush=True)

    # The client advertises no fs/terminal capability; agents must not call these.
    async def write_text_file(self, *a: Any, **k: Any):
        raise PermissionError("aitester's ACP client does not write files for the agent")

    async def read_text_file(self, *a: Any, **k: Any):
        raise PermissionError("aitester's ACP client does not read files for the agent")

    async def create_terminal(self, *a: Any, **k: Any):
        raise PermissionError("aitester's ACP client does not run terminals for the agent")

    async def terminal_output(self, *a: Any, **k: Any):
        raise PermissionError("no terminals")

    async def release_terminal(self, *a: Any, **k: Any):
        return None

    async def wait_for_terminal_exit(self, *a: Any, **k: Any):
        raise PermissionError("no terminals")

    async def kill_terminal(self, *a: Any, **k: Any):
        return None

    async def ext_method(self, method: str, params: dict) -> dict:
        return {}

    async def ext_notification(self, method: str, params: dict) -> None:
        return None


async def _author_async(
    *, agent_command: str, story: str, base_url: str, suite_path: Path,
    bug_report_dir: Path, engine: str, timeout_s: float, debug: bool,
) -> AuthoringResult:
    from acp import PROTOCOL_VERSION, spawn_agent_process
    from acp.helpers import text_block
    from acp.schema import AuthCapabilities, ClientCapabilities, EnvVariable, Implementation, McpServerStdio

    started = time.monotonic()
    argv = shlex.split(agent_command)
    if not argv:
        raise ValueError("empty ACP agent command")
    slug = _slugify(story)[:60] or "untitled"
    bug_path = bug_report_dir / f"{slug}.md"
    workdir = Path(tempfile.mkdtemp(prefix="aitester-acp-"))
    state_file = workdir / "terminal.json"
    browser_session = session_id()

    mcp_server = McpServerStdio(
        name=_MCP_SERVER_NAME,
        command=sys.executable,
        args=[
            "-m", "aitester_bdd.authoring.mcp_tools",
            "--session", browser_session,
            "--suite-path", str(suite_path.resolve()),
            "--bug-path", str(bug_path.resolve()),
            "--state-file", str(state_file),
        ],
        env=[EnvVariable(name=k, value=v) for k, v in _agent_env(browser_session).items()],
    )
    client = _Client(debug=debug)
    final_message = ""
    gateway_url = os.environ.get("AITESTER_ACP_GATEWAY_URL", "").strip()
    gateway_key = os.environ.get("AITESTER_ACP_GATEWAY_KEY", "").strip()
    caps = ClientCapabilities(
        auth=AuthCapabilities(field_meta={"gateway": True}) if gateway_url else AuthCapabilities()
    )
    async with spawn_agent_process(client, argv[0], *argv[1:], env=_agent_env(browser_session), cwd=str(workdir)) as (conn, _proc):
        init = await conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=caps,
            client_info=Implementation(name="aitester-bdd", version=_version()),
        )
        if gateway_url:
            methods = {m.id for m in (init.auth_methods or [])}
            if "gateway" not in methods:
                raise RuntimeError(
                    f"AITESTER_ACP_GATEWAY_URL is set but the agent offers no 'gateway' "
                    f"auth method (it offers: {sorted(methods) or 'none'})"
                )
            headers = {"Authorization": f"Bearer {gateway_key}"} if gateway_key else {}
            await conn.authenticate(method_id="gateway", gateway={"baseUrl": gateway_url, "headers": headers})
        session = await conn.new_session(cwd=str(workdir), mcp_servers=[mcp_server])
        try:
            resp = await asyncio.wait_for(
                conn.prompt(
                    session_id=session.session_id,
                    prompt=[text_block(build_prompt(story=story, base_url=base_url, engine=engine))],
                ),
                timeout=timeout_s,
            )
            final_message = f"stop reason: {resp.stop_reason}"
        except TimeoutError:
            await conn.cancel(session_id=session.session_id)
            final_message = f"timed out after {timeout_s:.0f}s"

    kind, path = read_terminal(state_file)
    if client.refused:
        final_message += f"; refused tools: {', '.join(sorted(set(client.refused)))}"
    return AuthoringResult(
        suite_path=path if kind == "suite" else None,
        bug_report_path=path if kind == "bug" else None,
        iterations=client.steps,
        final_message=final_message,
        transcript=[],
        elapsed_s=time.monotonic() - started,
    )


def _version() -> str:
    import importlib.metadata as md

    try:
        return md.version("aitester-bdd")
    except md.PackageNotFoundError:
        return "dev"


def author_with_acp(
    *, agent_command: str, story: str, base_url: str, suite_path: Path,
    bug_report_dir: Path, engine: str = "agent-browser", debug: bool = False,
    timeout_s: float | None = None,
) -> AuthoringResult:
    """Run one ACP authoring session; same result type as `author_with_agent`."""
    if timeout_s is None:
        timeout_s = float(os.environ.get("AITESTER_AUTHOR_TIMEOUT", "900"))
    return asyncio.run(_author_async(
        agent_command=agent_command, story=story, base_url=base_url,
        suite_path=suite_path, bug_report_dir=bug_report_dir, engine=engine,
        timeout_s=timeout_s, debug=debug,
    ))
