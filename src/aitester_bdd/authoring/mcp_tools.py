"""MCP stdio server handed to an external authoring agent over ACP (spec 04 R5).

The agent gets exactly three tools and no shell:

  - `browser`           — one agent-browser command, run in aitester's session
  - `write_robot_suite` — terminal: write the parsed-and-checked suite
  - `report_bug`        — terminal: write the bug report

The server runs in its own process, so the terminal outcome is written to a
JSON state file with O_EXCL: the first successful terminal call wins and
`AcpAuthor` reads the file when the prompt turn ends.

Run by `AcpAuthor` as:
  python -m aitester_bdd.authoring.mcp_tools --session S --suite-path P \
      --bug-path B --state-file F
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from aitester_bdd.authoring.tools import suite_problems

# agent-browser subcommands the author may use: reading and driving the page.
# Session, profile, install and dashboard commands are excluded.
BROWSER_COMMANDS = frozenset({
    "open", "snapshot", "get", "click", "dblclick", "fill", "type", "press",
    "wait", "eval", "find", "is", "hover", "focus", "select", "check",
    "uncheck", "scroll", "screenshot", "back", "forward", "reload", "read",
})
_MAX_OUTPUT = 200_000


def run_browser_command(command: str, *, session: str, timeout_s: int = 60) -> str:
    """Run one agent-browser command line in `session`; return its output."""
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"ERROR: cannot parse command: {exc}"
    if argv and argv[0] == "agent-browser":
        argv = argv[1:]
    if not argv or argv[0] not in BROWSER_COMMANDS:
        return (
            f"ERROR: {argv[0] if argv else '(empty)'!r} is not an allowed agent-browser "
            f"command; allowed: {', '.join(sorted(BROWSER_COMMANDS))}"
        )
    if any(a in ("--session", "--profile", "--state", "--cdp") for a in argv):
        return "ERROR: session, profile, state and cdp flags are fixed by aitester"
    binary = shutil.which("agent-browser")
    if not binary:
        return "ERROR: agent-browser CLI not found on PATH"
    try:
        r = subprocess.run(
            [binary, "--session", session, *argv],
            capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except subprocess.TimeoutExpired:
        return f"ERROR: timed out after {timeout_s}s"
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    text = out if r.returncode == 0 else f"exit {r.returncode}\n{err or out}"
    return text[:_MAX_OUTPUT]


def record_terminal(state_file: Path, kind: str, path: Path) -> bool:
    """Write the terminal outcome once. False when one is already recorded."""
    try:
        fd = os.open(state_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"kind": kind, "path": str(path)}, fh)
    return True


def read_terminal(state_file: Path) -> tuple[str | None, Path | None]:
    if not state_file.exists():
        return None, None
    data = json.loads(state_file.read_text(encoding="utf-8"))
    return data.get("kind"), Path(data["path"]) if data.get("path") else None


def build_server(*, session: str, suite_path: Path, bug_path: Path, state_file: Path):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        name="aitester",
        instructions=(
            "Drive the web app only through the `browser` tool (agent-browser commands, "
            "e.g. `snapshot -c -i`, `click @e3`, `open https://…`). End the task by calling "
            "write_robot_suite or report_bug exactly once."
        ),
    )

    @server.tool(description=(
        "Run one agent-browser command in the test's browser session and return its "
        "output, e.g. 'open https://app/', 'snapshot -c -i', 'click @e3', "
        "'get count .row', 'fill #q hello', 'eval \"document.title\"'. Add --json for JSON."
    ))
    def browser(command: str) -> str:
        return run_browser_command(command, session=session)

    @server.tool(description=(
        "TERMINAL. Write the complete .robot suite. It is parsed first; a parse error "
        "comes back so you can fix it. On success, stop: the task is done."
    ))
    def write_robot_suite(content: str) -> str:
        problems = suite_problems(content)
        if problems:
            return "ERROR: not a runnable suite: " + "; ".join(problems[:5])
        if state_file.exists():
            return "REFUSED: this run already ended. Stop now."
        suite_path.parent.mkdir(parents=True, exist_ok=True)
        suite_path.write_text(content, encoding="utf-8")
        if not record_terminal(state_file, "suite", suite_path):
            return "REFUSED: this run already ended. Stop now."
        return f"OK: wrote {suite_path}. The task is done; stop."

    @server.tool(description=(
        "TERMINAL. Write a bug report when the app is broken in a way that prevents "
        "authoring. A typed URL that redirects is NOT a bug by itself: first reach the "
        "page through the app's own navigation (sidebar, menus, mode toggles, links) "
        "and list each path you tried. On success, stop."
    ))
    def report_bug(content: str) -> str:
        if state_file.exists():
            return "REFUSED: this run already ended. Stop now."
        bug_path.parent.mkdir(parents=True, exist_ok=True)
        bug_path.write_text(content, encoding="utf-8")
        if not record_terminal(state_file, "bug", bug_path):
            return "REFUSED: this run already ended. Stop now."
        return f"OK: wrote bug report {bug_path}. The task is done; stop."

    return server


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="aitester-mcp-tools")
    ap.add_argument("--session", required=True)
    ap.add_argument("--suite-path", required=True, type=Path)
    ap.add_argument("--bug-path", required=True, type=Path)
    ap.add_argument("--state-file", required=True, type=Path)
    a = ap.parse_args(argv)
    build_server(
        session=a.session, suite_path=a.suite_path, bug_path=a.bug_path, state_file=a.state_file,
    ).run("stdio")


if __name__ == "__main__":
    main()
