"""Spec 05: restricted browser tool (S1), credentials by name (S2), shell
default-deny (S3), origin pinning (S4), batched commands (P1), fast selector
miss (P3), selector lint (R1, R5), sign-in marker (R2), run budget (R3),
clean-up in finally (R4), invalid selector is not zero (R6)."""
from __future__ import annotations

import subprocess

import pytest

from aitester_bdd.authoring import mcp_tools
from aitester_bdd.authoring.tools import (
    TerminalState,
    build_browser_tool,
    build_tools,
    suite_problems,
)
from tests.unit.test_walker_with_fake_browser import FakeBrowser

GOOD = "*** Variables ***\n${ENGINE}    agent-browser\n\n*** Test Cases ***\nT\n    I define rule \"r\"\n        Then selector \"#ok\" exists\n"


# ─── S1: the in-process author has no shell ───────────────────────────


def test_author_tools_are_browser_and_terminal_only(monkeypatch):
    from langchain_core.messages import AIMessage

    from aitester_bdd.authoring import agent_loop
    from tests.unit.test_agent_runtime import ScriptedModel

    seen: dict = {}
    real = agent_loop.__dict__

    def fake_create(**kwargs):
        seen["tools"] = [t.name for t in kwargs["tools"]]
        raise RuntimeError("stop here")

    monkeypatch.setattr(agent_loop, "_build_llm", lambda **_: ScriptedModel(script=[AIMessage(content="x")]))
    monkeypatch.setattr(agent_loop, "_is_inside_rf", lambda: False)
    monkeypatch.setitem(__import__("sys").modules, "deepagents", type("M", (), {"create_deep_agent": staticmethod(fake_create)}))
    import pathlib
    with pytest.raises(RuntimeError, match="stop here"):
        agent_loop._author_once(
            story="s", base_url="https://app.example.test", suite_path=pathlib.Path("/tmp/x.robot"),
            bug_report_dir=pathlib.Path("/tmp"), max_iters=3,
        )
    assert set(seen["tools"]) == {"browser", "write_robot_suite", "report_bug"}
    assert real  # keep the reference alive for readability


# ─── S4 / P1 / P3: the browser command layer ─────────────────────────


def _stub_run(monkeypatch, outputs):
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        out = outputs.pop(0) if outputs else ""
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")

    monkeypatch.setattr(mcp_tools, "_binary", lambda: "/bin/agent-browser")
    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_open_is_pinned_to_the_target_origin(monkeypatch):
    calls = _stub_run(monkeypatch, [])
    out = mcp_tools.run_browser_command("open https://evil.example/x", session="s", base_url="https://app.example.test")
    assert out.startswith("ERROR: open refused") and calls == []
    monkeypatch.setenv("AITESTER_ALLOWED_ORIGINS", "https://sso.example.test")
    assert not mcp_tools.run_browser_command("open https://sso.example.test/login", session="s", base_url="https://app.example.test").startswith("ERROR")
    assert not mcp_tools.run_browser_command("open /relative", session="s", base_url="https://app.example.test").startswith("ERROR")


def test_content_getter_fails_fast_on_a_missing_selector(monkeypatch):
    calls = _stub_run(monkeypatch, ['"[0]"'])
    out = mcp_tools.run_browser_command("get text '#nope'", session="s")
    assert out.startswith("ERROR: 0 elements match")
    assert len(calls) == 1 and calls[0][3] == "eval"  # the count probe, never `get text`


def test_content_getter_names_an_invalid_selector(monkeypatch):
    _stub_run(monkeypatch, ['"[-1]"'])
    out = mcp_tools.run_browser_command("get text 'a:has-text(\"x\")'", session="s")
    assert "not a valid CSS selector" in out


def test_batched_commands_stop_at_the_first_failure(monkeypatch):
    calls = _stub_run(monkeypatch, ["ok1", "exit 1\nboom", "never"])
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: (
        calls.append(argv) or subprocess.CompletedProcess(argv, 0 if len(calls) == 1 else 1, stdout="ok" if len(calls) == 1 else "", stderr="boom")
    ))
    out = mcp_tools.run_browser_commands(["snapshot -c -i", "click @e9", "snapshot -c -i"], session="s")
    assert "[1] snapshot -c -i" in out and "[2] click @e9" in out and "[3]" not in out
    assert "stopped: command 2 failed; 1 not run" in out
    assert len(calls) == 2


def test_browser_tool_wraps_the_same_layer(monkeypatch):
    _stub_run(monkeypatch, ["done"])
    tool = build_browser_tool(session="s", base_url=None)
    assert tool.name == "browser"
    assert tool.invoke({"command": "snapshot -c -i"}) == "done"


# ─── R1 / R5 / S3: the suite lint ────────────────────────────────────


def test_lint_rejects_playwright_only_selectors():
    bad = GOOD.replace('"#ok"', '"button:has-text(\'Save\')"')
    (problem,) = suite_problems(bad, engine="agent-browser")
    assert "Playwright-only" in problem and "line 7" in problem
    assert suite_problems(bad, engine="playwright") == []


def test_lint_rejects_a_fallback_without_spaces():
    bad = GOOD.replace('"#ok"', '"#a|#b"')
    assert any("spaces around the bar" in p for p in suite_problems(bad))
    assert suite_problems(GOOD.replace('"#ok"', '"#a | #b"')) == []


def test_lint_rejects_exact_counts_above_one():
    s = GOOD + "        Then count of locator \"[role=combobox]\" equals 4\n"
    assert any("exact count 4" in p for p in suite_problems(s))
    assert suite_problems(GOOD + "        Then count of locator \"[role=combobox]\" equals 1\n") == []
    assert suite_problems(s.replace("equals 4", "equals 4    # exact-count: intended")) == []


def test_lint_rejects_shell_unless_allowed():
    s = GOOD + "        When I run shell \"rm -rf /\"\n"
    assert any("shell action" in p for p in suite_problems(s))
    assert suite_problems(s + "# allow-shell\n") == []


def test_lint_probe_reports_selectors_the_browser_cannot_parse():
    s = GOOD.replace('"#ok"', '"[data-x=1]"')
    assert suite_problems(s, probe=lambda sels: [-1] * len(sels)) == [
        "line 7: selector '[data-x=1]' does not parse in the browser (not CSS)"
    ]
    assert suite_problems(s, probe=lambda sels: [0] * len(sels)) == []  # absent now is fine; invalid is not


def test_write_robot_suite_uses_the_lint(tmp_path):
    state = TerminalState()
    write, _ = build_tools(state, suite_path=tmp_path / "s.robot", bug_report_path=tmp_path / "b.md")
    out = write.invoke({"content": GOOD.replace('"#ok"', '"a:visible"')})
    assert out.startswith("ERROR") and "Playwright-only" in out and not state.done


# ─── S2: credentials by name ─────────────────────────────────────────


def test_secret_ref_resolves_and_masks(monkeypatch):
    from aitester_bdd.engine.walk import Secret, StateSetupError, resolve_secret_ref

    monkeypatch.setenv("APP_PW", "hunter2-secret")
    v = resolve_secret_ref("env:APP_PW")
    assert isinstance(v, Secret) and v.reveal() == "hunter2-secret"
    assert repr(v) == "***" and str(v) == "***" and "hunter2" not in f"{v}"
    assert resolve_secret_ref("plain") == "plain"
    monkeypatch.delenv("MISSING_PW", raising=False)
    with pytest.raises(StateSetupError) as exc:
        resolve_secret_ref("env:MISSING_PW")
    assert "MISSING_PW" in str(exc.value)


def test_signin_fixture_parses_and_injects(tmp_path, monkeypatch):
    from aitester_bdd.authoring.signin import inject_signin_block, parse_fixture

    f = tmp_path / "signin.txt"
    f.write_text(
        "action=open url=https://app/auth\naction=input css=input[type=email] value=env:U\n"
        "action=password css=input[type=password] value=env:P\naction=click css=button[type=submit]\n"
        "skip_when=[data-sidebar=footer]\n"
    )
    ss = parse_fixture(f)
    assert len(ss.actions) == 4 and ss.skip_when == "[data-sidebar=footer]"
    suite = tmp_path / "s.robot"
    suite.write_text("*** Test Cases ***\nT\n    [Setup]    Given I start scenario \"x\" at \"u\"\n    I define rule \"r\"\n")
    inject_signin_block(suite, f)
    text = suite.read_text()
    assert "value=env:P" in text and "skip_when=[data-sidebar=footer]" in text
    assert text.index("[Setup]") < text.index("state setup") < text.index('I define rule')
    inject_signin_block(suite, f)  # idempotent
    assert text == suite.read_text()


# ─── R2 / R3 / R4 / S3 on the walker ─────────────────────────────────


def _make():
    from aitester_bdd.AITester import AITester

    t = AITester()
    t.start_verification('"v"')
    t.start_scenario_at('"flow"', '"http://x"')
    return t


def _walk(t, fake, monkeypatch, **ctx_kw):
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.context import WalkContext
    from aitester_bdd.engine.walk import walk_verification

    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)
    return walk_verification(t.get_verification(), WalkContext(**ctx_kw))


def test_skip_when_is_the_setup_success_marker(monkeypatch):
    from aitester_bdd.engine.walk import StateSetupError

    t = _make()
    t.configure_state_setup("action=open", "url=http://x/login")
    t.configure_state_setup("skip_when=.signed-in")
    t.define_rule('"r"')
    t.then_selector_exists('"#ok"')
    fake = FakeBrowser(current_url="http://x/", selector_present={"#ok": True})
    with pytest.raises(StateSetupError, match="marker '.signed-in' did not appear"):
        _walk(t, fake, monkeypatch)
    fake = FakeBrowser(current_url="http://x/", selector_present={"#ok": True, ".signed-in": True})
    assert _walk(t, fake, monkeypatch).passed


def test_run_budget_marks_later_rules_not_run(monkeypatch):
    import time

    class Slow(FakeBrowser):
        def get_count(self, css):
            time.sleep(0.6)
            return super().get_count(css)

        def wait_for_selector(self, css, *, present=True, timeout_ms=5000):
            time.sleep(0.6)
            return super().wait_for_selector(css, present=present, timeout_ms=timeout_ms)

        def wait_for_elements_state(self, selector, state="attached", *, timeout_ms=5000):
            time.sleep(0.6)
            return super().wait_for_elements_state(selector, state, timeout_ms=timeout_ms)

    def suite():
        t = _make()
        t.define_rule('"slow"')
        t.then_selector_exists('"#a"')
        t.then_selector_exists('"#a"')
        t.define_rule('"next"')
        t.then_selector_exists('"#a"')
        return t

    present = {"#a": True}
    assert _walk(suite(), Slow(current_url="http://x/", selector_present=present), monkeypatch, run_timeout_s=0).passed
    verdict = _walk(suite(), Slow(current_url="http://x/", selector_present=present), monkeypatch, run_timeout_s=1)
    assert verdict.results[0].passed
    assert verdict.results[1].failure_step_kind == "run_budget"
    assert "not run" in verdict.results[1].failure_message
    # the suite's own budget wins over the context
    t = suite()
    t.set_run_timeout("1")
    verdict = _walk(t, Slow(current_url="http://x/", selector_present=present), monkeypatch, run_timeout_s=0)
    assert verdict.results[1].failure_step_kind == "run_budget"


def test_cleanup_runs_even_when_a_rule_raises(monkeypatch):
    t = _make()
    t.configure_cleanup("action=click", "css=#delete")
    t.define_rule('"r"')
    t.when_click_locator('"#boom"')

    class Boom(FakeBrowser):
        def click(self, css):
            if css == "#boom":
                raise RuntimeError("kaboom")
            super().click(css)

    fake = Boom(current_url="http://x/", selector_present={"#boom": True, "#delete": True})
    verdict = _walk(t, fake, monkeypatch)
    assert verdict.failed
    assert ("click", "#delete") in fake.actions_called
    assert verdict.cleanup_failures == []


def test_shell_action_is_denied_by_default(monkeypatch):
    t = _make()
    t.define_rule('"r"')
    t.when_run_shell('"echo hi"')
    verdict = _walk(t, FakeBrowser(current_url="http://x/"), monkeypatch)
    assert verdict.failed and "shell actions are disabled" in verdict.results[0].failure_message
    verdict = _walk(t, FakeBrowser(current_url="http://x/"), monkeypatch, allow_shell=True)
    assert verdict.passed


# ─── R6: invalid selector is not zero ────────────────────────────────


def test_agent_browser_get_count_raises_on_invalid_selector(monkeypatch):
    from aitester_bdd.engine.agent_browser_backend import AgentBrowserBackend

    b = AgentBrowserBackend()
    monkeypatch.setattr(b, "evaluate_js", lambda s: -1)
    with pytest.raises(ValueError, match="not a valid CSS selector"):
        b.get_count("a:has-text('x')")
    monkeypatch.setattr(b, "evaluate_js", lambda s: 3)
    assert b.get_count("#x") == 3


def test_lint_rejects_bare_tag_locators_and_exploration_ids():
    s = GOOD.replace('"#ok"', '"button"')
    assert any("only a tag name" in p for p in suite_problems(s))
    s = GOOD + '\n${PROJECT_ID}    50a9ccfa-e576-4abf-9496-805663976365\n'
    assert any("UUID" in p for p in suite_problems(s))
    assert suite_problems(GOOD + '\n${AGENT_ID}    50a9ccfa-e576-4abf-9496-805663976365  # fixed-id: intended\n') == []


def test_browser_wait_longer_than_the_call_timeout_is_refused():
    from aitester_bdd.authoring.mcp_tools import run_browser_command
    out = run_browser_command("wait 240000", session="s", timeout_s=60)
    assert out.startswith("ERROR") and "50000 ms" in out


def test_lint_rejects_body_locators_and_empty_rules():
    s = GOOD.replace('"#ok"', '"body"')
    assert any("only a tag name" in p for p in suite_problems(s))
    s = GOOD + '    I define rule "cancel"\n        And I declare parents "r"\n        Then selector "html" exists\n'
    assert any("does nothing" in p and "cancel" in p for p in suite_problems(s))


def test_lint_rejects_utility_class_chains():
    s = GOOD.replace('"#ok"', '"button.flex.flex-1.items-center.justify-center.gap-1"')
    assert any("styling classes" in p for p in suite_problems(s))
    assert suite_problems(GOOD.replace('"#ok"', '"button.primary"')) == []


def test_failed_check_after_a_click_retries_the_click_once(monkeypatch):
    from aitester_bdd.AITester import Action, Rule, StateCheck, Verification
    from aitester_bdd.engine import walk

    class B:
        clicks = 0
        def click(self, sel, **kw):
            self.clicks += 1
        def get_count(self, sel):
            return 1 if self.clicks >= 2 else 0

    b = B()
    checks = {"n": 0}

    def fake_check(browser, step, timeout_ms, scope):
        checks["n"] += 1
        return (browser.get_count(step.locator) > 0, "present", str(browser.get_count(step.locator)))

    monkeypatch.setattr(walk, "_eval_state_check", fake_check)
    monkeypatch.setattr(walk, "_eval_action", lambda browser, step, scope: browser.click(step.target))
    monkeypatch.setattr(walk, "_await_after_action", lambda browser, step: None)
    monkeypatch.setattr(walk, "_effective_interrupt_selectors", lambda rule, verification: [])
    body = [Action(kind="click", target="#studio"), StateCheck(kind="selector_exists", locator="a[href='/agents']")]
    ok, *_ = walk._execute_body(b, Rule(name="r"), Verification(name="v"), body)
    assert ok and b.clicks == 2 and checks["n"] == 2
