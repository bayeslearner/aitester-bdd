"""The browser command layer both authors use, and the MCP stdio server that
exposes it to an external agent over ACP (spec 04 R5, spec 05 S1).

An authoring agent gets exactly three tools and no shell:

  - `browser`           — one or more agent-browser commands, run in aitester's session
  - `write_robot_suite` — terminal: write the parsed-and-checked suite
  - `report_bug`        — terminal: write the bug report

`run_browser_commands` is the one place agent-browser is invoked for an agent:
it allowlists subcommands, pins the session, refuses session/profile/state
flags, keeps `open` on the target's origin (S4), and fails a content getter at
once when its selector matches nothing instead of letting the CLI block for
30 s (P3). `get_counts` asks the page itself how many elements each selector
matches, and reports an invalid selector as -1 rather than 0 (R6).

The MCP server runs in its own process, so the terminal outcome is written to
a JSON state file with O_EXCL: the first successful terminal call wins and
`AcpAuthor` reads the file when the prompt turn ends.

Run by `AcpAuthor` as:
  python -m aitester_bdd.authoring.mcp_tools --session S --base-url U \
      --suite-path P --bug-path B --state-file F
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from aitester_bdd.authoring.tools import suite_problems

log = logging.getLogger("aitester_bdd.authoring.mcp_tools")

# agent-browser subcommands the author may use: reading and driving the page.
# Session, profile, install and dashboard commands are excluded.
BROWSER_COMMANDS = frozenset({
    "open", "snapshot", "get", "click", "dblclick", "fill", "type", "press",
    "wait", "eval", "find", "is", "hover", "focus", "select", "check",
    "uncheck", "scroll", "screenshot", "back", "forward", "reload", "read",
})
# Content getters that block ~30 s on a selector with no match.
_CONTENT_GETTERS = frozenset({"text", "html", "attr", "value", "box"})
_MAX_OUTPUT = 200_000

# One copy of the command help both authors show the model.
BROWSER_HELP = (
    "## The browser tool\n\n"
    "Every browser action is a call to the `browser` tool with one agent-browser "
    "command line, or a list of them run in order (no `agent-browser` prefix):\n\n"
    "```\n"
    "open <url>                 # the app under test only; other origins are refused\n"
    "snapshot -c -i             # compact, interactive elements, with @refs\n"
    "get count '<css>'\nget text '<css>'\nget attr '<css>' <name>\n"
    "click '<css|@ref>'\nfill '<css>' '<text>'\ntype '<css>' '<text>'\npress <key>\n"
    "wait '<css>'|<ms>\neval '<js>'\nfind role button click --name 'Save'\n"
    "```\n\n"
    "Batch related steps in one call, e.g. [\"click @e4\", \"wait 1500\", \"snapshot -c -i\"]: "
    "the list stops at the first failing command. Refs (@e3) change after every page "
    "change: snapshot again before using one. Selectors in the suite must be plain CSS "
    "(no :has-text, text=, :visible or >>); an `a | b` fallback needs spaces around the bar.\n\n"
)


def _binary() -> str | None:
    return shutil.which("agent-browser")


def _same_origin(url: str, allowed: tuple[str, ...]) -> bool:
    try:
        u = urlsplit(url)
    except ValueError:
        return False
    if not u.scheme:  # a path on the current origin
        return True
    for a in allowed:
        b = urlsplit(a)
        if (u.scheme, u.netloc.lower()) == (b.scheme, b.netloc.lower()):
            return True
    return False


def allowed_origins(base_url: str | None) -> tuple[str, ...]:
    """The target's origin plus AITESTER_ALLOWED_ORIGINS (comma-separated), for
    sign-in redirects to another host."""
    out = []
    if base_url:
        out.append(base_url)
    out += [o.strip() for o in os.environ.get("AITESTER_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return tuple(out)


def get_counts(selectors: list[str], *, session: str, timeout_s: int = 30) -> list[int]:
    """How many elements each CSS selector matches on the current page, in one
    eval; -1 for a selector the browser cannot parse (R6)."""
    binary = _binary()
    if not binary or not selectors:
        return [-1] * len(selectors) if not binary else []
    js = (
        "(() => { const sels = " + json.dumps(selectors) + "; return JSON.stringify(sels.map(s => "
        "{ try { return document.querySelectorAll(s).length; } catch (e) { return -1; } })); })()"
    )
    r = subprocess.run(
        [binary, "--session", session, "eval", js],
        capture_output=True, text=True, timeout=timeout_s, check=False,
    )
    out = (r.stdout or "").strip()
    try:
        parsed = json.loads(out)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        if isinstance(parsed, list) and len(parsed) == len(selectors):
            return [int(x) for x in parsed]
    except (ValueError, TypeError):
        pass
    raise RuntimeError(f"agent-browser eval for element counts failed: {(r.stderr or out)[:300]}")


def run_browser_command(
    command: str, *, session: str, timeout_s: int = 60, base_url: str | None = None,
) -> str:
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
    if argv[0] == "open":
        targets = [a for a in argv[1:] if not a.startswith("-")]
        allowed = allowed_origins(base_url)
        if base_url and targets and not _same_origin(targets[0], allowed):
            return (
                f"ERROR: open refused: {targets[0]!r} is not on the app under test "
                f"({', '.join(allowed)}); set AITESTER_ALLOWED_ORIGINS for a sign-in host"
            )
    if argv[0] == "eval":
        log.info("browser eval: %s", " ".join(argv[1:])[:300])
    if argv[0] == "wait" and len(argv) >= 2 and argv[1].isdigit():
        # The CLI keeps waiting after this call times out and blocks the session's next
        # commands for the rest of the wait (seen as three 60 s timeouts in a row).
        cap_ms = max(1000, (timeout_s - 10) * 1000)
        if int(argv[1]) > cap_ms:
            return (
                f"ERROR: wait {argv[1]} ms exceeds the {cap_ms} ms a single call may wait; "
                f"wait in shorter steps and snapshot between them, or wait for a selector ('wait \'<css>\'')"
            )
    binary = _binary()
    if not binary:
        return "ERROR: agent-browser CLI not found on PATH"
    if argv[0] == "get" and len(argv) >= 3 and argv[1] in _CONTENT_GETTERS:
        sel = argv[2]
        if not sel.startswith("@"):
            try:
                (n,) = get_counts([sel], session=session)
            except RuntimeError as exc:
                return f"ERROR: {exc}"
            if n == -1:
                return f"ERROR: {sel!r} is not a valid CSS selector in the browser"
            if n == 0:
                return f"ERROR: 0 elements match {sel!r}; snapshot and pick another selector"
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


class Observed:
    """Everything the browser tool returned to the agent in this run: the text a pinned
    attribute value has to appear in (`suite_problems(observed=…)`). Bounded."""

    def __init__(self, limit: int = 4_000_000) -> None:
        self._parts: list[str] = []
        self._size = 0
        self._limit = limit

    def add(self, text: str) -> None:
        self._parts.append(text)
        self._size += len(text)
        while self._size > self._limit and len(self._parts) > 1:
            self._size -= len(self._parts.pop(0))

    @property
    def text(self) -> str:
        return "\n".join(self._parts)


def run_browser_commands(
    commands: list[str], *, session: str, timeout_s: int = 60, base_url: str | None = None,
    observed: Observed | None = None,
) -> str:
    """Run several commands in order; stop at the first that fails (P1).
    Returns one block per command, or the single command's output as is."""
    if len(commands) == 1:
        out = run_browser_command(commands[0], session=session, timeout_s=timeout_s, base_url=base_url)
        if observed is not None:
            observed.add(out)
        return out
    parts = []
    for i, c in enumerate(commands, 1):
        out = run_browser_command(c, session=session, timeout_s=timeout_s, base_url=base_url)
        if observed is not None:
            observed.add(out)
        parts.append(f"[{i}] {c}\n{out}")
        if out.startswith("ERROR") or out.startswith("exit "):
            parts.append(f"(stopped: command {i} failed; {len(commands) - i} not run)")
            break
    return "\n\n".join(parts)[:_MAX_OUTPUT]


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


def build_server(
    *, session: str, suite_path: Path, bug_path: Path, state_file: Path,
    base_url: str | None = None, engine: str = "agent-browser",
):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(
        name="aitester",
        instructions=(
            "Drive the web app only through the `browser` tool (agent-browser commands, "
            "e.g. `snapshot -c -i`, `click @e3`, `open https://…`). End the task by calling "
            "write_robot_suite or report_bug exactly once."
        ),
    )

    def probe(selectors: list[str]) -> list[int]:
        return get_counts(selectors, session=session)

    observed = Observed()

    @server.tool(description=(
        "Run agent-browser commands in the test's browser session and return their output. "
        "Pass one command, or a list run in order that stops at the first failure, e.g. "
        "['open https://app/', 'wait 1500', 'snapshot -c -i'], 'click @e3', "
        "'get count .row', 'fill #q hello', 'eval \"document.title\"'. Add --json for JSON."
    ))
    def browser(command: str | None = None, commands: list[str] | None = None) -> str:
        cmds = list(commands or []) + ([command] if command else [])
        if not cmds:
            return "ERROR: give command or commands"
        return run_browser_commands(cmds, session=session, base_url=base_url, observed=observed)

    @server.tool(description=(
        "TERMINAL. Write the complete .robot suite. It is parsed and its selectors are "
        "checked first (plain CSS only; each must parse in the browser); any problem comes "
        "back so you can fix it. On success, stop: the task is done."
    ))
    def write_robot_suite(content: str) -> str:
        problems = suite_problems(content, engine=engine, probe=probe, observed=observed.text)
        if problems:
            return (
                "ERROR: not a runnable suite: " + "; ".join(problems[:8])
                + ". Fix these lines and call write_robot_suite again; a refused write is not a "
                "reason to file a bug report."
            )
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
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--engine", default="agent-browser")
    a = ap.parse_args(argv)
    build_server(
        session=a.session, suite_path=a.suite_path, bug_path=a.bug_path, state_file=a.state_file,
        base_url=a.base_url, engine=a.engine,
    ).run("stdio")


if __name__ == "__main__":
    main()
