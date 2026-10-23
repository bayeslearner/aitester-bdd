"""Spec 04 R5: the ACP author's permission policy, MCP browser allowlist and
write-once terminal state. Skipped without the [acp] extra."""
from __future__ import annotations

import pytest

pytest.importorskip("acp")
pytest.importorskip("mcp")

from aitester_bdd.authoring.acp_author import allow_tool_call, build_prompt  # noqa: E402
from aitester_bdd.authoring.mcp_tools import (  # noqa: E402
    read_terminal,
    record_terminal,
    run_browser_command,
)


@pytest.mark.parametrize(
    ("title", "raw", "allowed"),
    [
        ("mcp__aitester__browser", None, True),
        ("aitester:write_robot_suite", None, True),
        (None, "mcp__aitester__report_bug", True),
        ("Bash", None, False),
        ("mcp__other__browser", None, False),
        ("Write /etc/hosts", None, False),
        (None, None, False),
    ],
)
def test_permission_policy(title, raw, allowed):
    assert allow_tool_call(title, raw) is allowed


@pytest.mark.parametrize(
    "command",
    ["install", "session list", "close --all", "dashboard start", "open x --profile Default", "click a --session other", ""],
)
def test_browser_tool_refuses_outside_the_allowlist(command):
    assert run_browser_command(command, session="s").startswith("ERROR")


def test_browser_tool_strips_the_binary_name(monkeypatch):
    import subprocess

    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr("aitester_bdd.authoring.mcp_tools.shutil.which", lambda _: "/bin/agent-browser")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert run_browser_command("agent-browser snapshot -c -i", session="s1") == "ok"
    assert seen["argv"] == ["/bin/agent-browser", "--session", "s1", "snapshot", "-c", "-i"]


def test_terminal_state_is_written_once(tmp_path):
    f = tmp_path / "t.json"
    assert record_terminal(f, "bug", tmp_path / "b.md") is True
    assert record_terminal(f, "suite", tmp_path / "s.robot") is False
    assert read_terminal(f) == ("bug", tmp_path / "b.md")
    assert read_terminal(tmp_path / "none.json") == (None, None)


def test_prompt_names_only_aitester_tools_and_the_navigation_rule():
    p = build_prompt(story="check logs", base_url="https://app.example.test", engine="agent-browser")
    assert "Use only the `aitester` tools" in p
    assert "mode toggles" in p
    assert "${ENGINE}    agent-browser" in p
