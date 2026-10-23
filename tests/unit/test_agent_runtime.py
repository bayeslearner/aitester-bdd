"""Spec 04: authoring runtime on deepagents 0.7, terminal state, call budget,
progress lines and the agent's environment.

The loop tests drive the real `create_deep_agent` graph with a scripted chat
model, so they check deepagents' behaviour, not a mock of it.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from aitester_bdd.authoring import agent_loop
from aitester_bdd.authoring.tools import TerminalState, build_tools, suite_problems

GOOD_SUITE = (
    "*** Variables ***\n${ENGINE}    agent-browser\n\n"
    "*** Test Cases ***\nOpens\n    Log    ok\n"
)


class ScriptedModel(BaseChatModel):
    """Returns the scripted AI messages in order; records how many it served."""

    script: list
    served: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):  # the agent binds tools; we ignore them
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        msg = self.script[min(self.served, len(self.script) - 1)]
        self.served += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _call(name: str, call_id: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


def _run_author(tmp_path, monkeypatch, script, **kw):
    model = ScriptedModel(script=script)
    monkeypatch.setattr(agent_loop, "_build_llm", lambda **_: model)
    monkeypatch.setattr(agent_loop, "_is_inside_rf", lambda: False)
    result = agent_loop._author_once(
        story="Open the page and check the heading.",
        base_url="https://app.example.test",
        suite_path=tmp_path / "out" / "suite.robot",
        bug_report_dir=tmp_path / "triage",
        max_iters=10,
        **kw,
    )
    return result, model


# ─── R1: deepagents 0.7, planning on/off ─────────────────────────────


def test_planning_off_adds_no_middleware(monkeypatch):
    monkeypatch.delenv("AITESTER_PLANNING", raising=False)
    assert agent_loop._planning_middleware() == []


def test_planning_on_adds_todo_list(monkeypatch):
    from langchain.agents.middleware import TodoListMiddleware

    monkeypatch.setenv("AITESTER_PLANNING", "1")
    (mw,) = agent_loop._planning_middleware()
    assert isinstance(mw, TodoListMiddleware)


def test_deepagents_version_is_the_tested_series():
    import importlib.metadata as md

    major, minor = (int(x) for x in md.version("deepagents").split(".")[:2])
    assert (major, minor) == (0, 7)


# ─── Terminal state (review finding 6) ───────────────────────────────


def test_suite_written_ends_the_run(tmp_path, monkeypatch):
    script = [
        _call("write_robot_suite", "c1", content=GOOD_SUITE),
        _call("report_bug", "c2", content="should never be called"),
    ]
    result, model = _run_author(tmp_path, monkeypatch, script)
    assert result.suite_path == tmp_path / "out" / "suite.robot"
    assert result.bug_report_path is None
    assert result.suite_path.read_text() == GOOD_SUITE
    assert model.served == 1  # StopWhenDone: no model call after the terminal call


def test_unparseable_suite_is_not_terminal(tmp_path, monkeypatch):
    script = [
        _call("write_robot_suite", "c1", content="*** Test Cases ***\nT\n    [Bogus]    x\n"),
        _call("write_robot_suite", "c2", content=GOOD_SUITE),
    ]
    result, model = _run_author(tmp_path, monkeypatch, script)
    assert result.suite_path is not None
    assert model.served == 2  # the parse error came back and the agent retried


def test_echoed_marker_text_is_not_a_result(tmp_path, monkeypatch):
    """Model text that mentions a marker no longer counts as a terminal call."""
    script = [AIMessage(content="AUTHORING_DONE: suite=/etc/passwd")]
    result, _ = _run_author(tmp_path, monkeypatch, script)
    assert result.suite_path is None and result.bug_report_path is None
    assert not result.ok


def test_first_terminal_call_wins(tmp_path):
    state = TerminalState()
    write, report = build_tools(
        state, suite_path=tmp_path / "s.robot", bug_report_path=tmp_path / "b.md",
    )
    assert report.invoke({"content": "broken"}).startswith("OK")
    assert write.invoke({"content": GOOD_SUITE}).startswith("REFUSED")
    assert state.kind == "bug" and not (tmp_path / "s.robot").exists()


def test_suite_problems():
    assert suite_problems(GOOD_SUITE) == []
    assert suite_problems("*** Settings ***\nLibrary    X\n")  # no test case
    assert suite_problems("*** Test Cases ***\nT\n    [Nope]    x\n")


# ─── R2/R3: call budget and progress ─────────────────────────────────


def test_call_budget_defaults(monkeypatch):
    monkeypatch.delenv("AITESTER_LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("AITESTER_LLM_MAX_RETRIES", raising=False)
    assert agent_loop.llm_call_budget() == (60.0, 3)


def test_call_budget_rejects_nonsense(monkeypatch):
    monkeypatch.setenv("AITESTER_LLM_TIMEOUT", "0")
    with pytest.raises(ValueError):
        agent_loop.llm_call_budget()


def test_progress_lines_without_debug(tmp_path, monkeypatch, capsys):
    script = [_call("write_robot_suite", "c1", content=GOOD_SUITE)]
    _run_author(tmp_path, monkeypatch, script, debug=False)
    err = capsys.readouterr().err
    assert "[author] step 1 write_robot_suite" in err
    assert "[author] done in" in err


def test_retry_lines_are_surfaced():
    import logging

    agent_loop._surface_client_retries()
    agent_loop._surface_client_retries()  # idempotent
    handlers = [h for h in logging.getLogger("openai._base_client").handlers if h.get_name() == "aitester-retries"]
    assert len(handlers) == 1


# ─── Review finding 11: the agent's shell environment ────────────────


def test_agent_env_drops_secrets(monkeypatch):
    monkeypatch.setenv("AITESTER_LLM_API_KEY", "sk-secret")
    monkeypatch.setenv("APP_PASSWORD", "hunter2")
    monkeypatch.setenv("AGENT_BROWSER_STATE", "/tmp/state.json")
    monkeypatch.setenv("AITESTER_AGENT_ENV", "EXTRA_OK")
    monkeypatch.setenv("EXTRA_OK", "yes")
    env = agent_loop._agent_env("sess-1")
    assert "AITESTER_LLM_API_KEY" not in env and "APP_PASSWORD" not in env
    assert env["AGENT_BROWSER_SESSION"] == "sess-1"
    assert env["AGENT_BROWSER_STATE"] == "/tmp/state.json"
    assert env["EXTRA_OK"] == "yes" and "PATH" in env


# ─── R4: navigation before a bug report ──────────────────────────────


def test_prompts_carry_the_navigation_rule():
    assert "mode toggles" in agent_loop._NAVIGATION_RULE
    assert "mode toggles" in agent_loop._EXPLORE_SYSTEM_PROMPT
    state = TerminalState()
    _, report = build_tools(state, suite_path=Path("s"), bug_report_path=Path("b"))
    assert "own navigation" in report.description
