"""Spec 04 R7: a pinned step passes only when its check ran against a matched
element and held (review findings 1–4)."""
from __future__ import annotations

import pytest

from tests.unit.test_walker_with_fake_browser import FakeBrowser


def _make():
    from aitester_bdd.AITester import AITester

    t = AITester()
    t.start_verification('"v"')
    t.start_scenario_at('"flow"', '"http://x"')
    return t


def _walk(t, fake, monkeypatch):
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)
    return walk_verification(t.get_verification())


# ─── Finding 1: await= ────────────────────────────────────────────────


def test_await_that_never_appears_fails_the_step(monkeypatch):
    t = _make()
    t.define_rule('"save"')
    t.when_click_locator('".save"', "await=.toast-ok")
    fake = FakeBrowser(current_url="http://x/", selector_present={".save": True})
    verdict = _walk(t, fake, monkeypatch)
    assert verdict.failed
    assert "await='.toast-ok'" in verdict.results[0].failure_message


def test_await_that_appears_passes(monkeypatch):
    t = _make()
    t.define_rule('"save"')
    t.when_click_locator('".save"', "await=.toast-ok")
    fake = FakeBrowser(current_url="http://x/", selector_present={".save": True, ".toast-ok": True})
    assert _walk(t, fake, monkeypatch).passed


# ─── Finding 3: checks on a selector that matches nothing ─────────────


@pytest.mark.parametrize(
    "add_check",
    [
        lambda t: t.then_not_contains('".typo"', '"error"'),
        lambda t: t.then_disabled('".typo"'),
        lambda t: t.then_not_class_kw('".typo"', '"active"'),
        lambda t: t.then_enabled('".typo"'),
    ],
    ids=["not_contains", "disabled", "not_class", "enabled"],
)
def test_check_on_missing_element_fails(add_check, monkeypatch):
    t = _make()
    t.define_rule('"r"')
    add_check(t)
    verdict = _walk(t, FakeBrowser(current_url="http://x/"), monkeypatch)
    assert verdict.failed
    assert "no element matched" in verdict.results[0].observed


def test_hidden_on_missing_element_passes_and_says_absent(monkeypatch):
    t = _make()
    t.define_rule('"r"')
    t.then_hidden('".spinner"')
    verdict = _walk(t, FakeBrowser(current_url="http://x/"), monkeypatch)
    assert verdict.passed


def test_not_contains_on_present_element_still_works(monkeypatch):
    t = _make()
    t.define_rule('"r"')
    t.then_not_contains('"h1"', '"error"')
    fake = FakeBrowser(current_url="http://x/", text_for={"h1": "All good"})
    assert _walk(t, fake, monkeypatch).passed


# ─── Finding 2: navigation sentinel (agent-browser) ───────────────────


def test_closed_page_does_not_read_as_visible(monkeypatch):
    from aitester_bdd.engine.agent_browser_backend import AgentBrowserBackend

    b = AgentBrowserBackend()
    monkeypatch.setattr(b, "evaluate_js", lambda s: "__NAVIGATED__")
    for getter in (b.is_visible, b.is_enabled, b.is_checked):
        with pytest.raises(RuntimeError, match="navigated or closed"):
            getter("#x")


def test_only_true_reads_as_true(monkeypatch):
    from aitester_bdd.engine.agent_browser_backend import AgentBrowserBackend

    b = AgentBrowserBackend()
    for value, expected in ((True, True), (False, False), (None, False), ("", False), ("x", False)):
        monkeypatch.setattr(b, "evaluate_js", lambda s, v=value: v)
        assert b.is_enabled("#x") is expected


# ─── Finding 4: actions on a missing element ──────────────────────────


@pytest.mark.parametrize("action", ["double_click", "select", "hover", "focus"])
def test_agent_browser_action_on_missing_element_raises(action, monkeypatch):
    from aitester_bdd.engine.agent_browser_backend import AgentBrowserBackend

    b = AgentBrowserBackend()
    monkeypatch.setattr(b, "evaluate_js", lambda s: False)
    args = ("#typo", "v") if action == "select" else ("#typo",)
    with pytest.raises(LookupError, match="no element matched '#typo'"):
        getattr(b, action)(*args)


def test_agent_browser_click_text_miss_raises(monkeypatch):
    from aitester_bdd.engine.agent_browser_backend import AgentBrowserBackend

    b = AgentBrowserBackend()
    monkeypatch.setattr(b, "get_count", lambda s: 0)
    monkeypatch.setattr(b, "evaluate_js", lambda s: False)
    with pytest.raises(LookupError, match="no visible element contains 'Save'"):
        b.click_text("Save")


# ─── Finding 7: secret values stay out of error text ──────────────────


def test_secret_value_is_redacted_from_timeout_error(monkeypatch):
    import subprocess

    from aitester_bdd.engine.agent_browser_backend import AgentBrowserBackend

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="agent-browser", timeout=1)

    monkeypatch.setattr(subprocess, "run", _timeout)
    b = AgentBrowserBackend()
    with pytest.raises(RuntimeError) as exc:
        b.type("#password", "hunter2-secret", secret=True)
    assert "hunter2-secret" not in str(exc.value) and "***" in str(exc.value)
    with pytest.raises(RuntimeError) as exc:
        b.type("#name", "alice")  # not secret: the value may show
    assert "alice" in str(exc.value)


# ─── Finding 9: other fail-open places ────────────────────────────────


def test_zero_rules_is_not_a_pass():
    from aitester_bdd.engine.verdict import Verdict

    assert Verdict(verification_name="v").passed is False


def test_preflight_that_raises_fails_closed(monkeypatch):
    from aitester_bdd.engine import walk

    monkeypatch.delenv("AITESTER_ALLOW_STUB_BROWSER", raising=False)

    class Broken:
        def preflight(self):
            raise OSError("cannot reach the browser")

    with pytest.raises(walk.NullBrowserError, match="cannot reach the browser"):
        walk._assert_real_browser(Broken())


def test_failed_setup_step_raises_without_the_value():
    from aitester_bdd.engine import walk

    class Fake(FakeBrowser):
        def type(self, css, v, *, secret=False):
            raise LookupError(f"no element matched {css!r}")

    v = type("V", (), {})()
    v.state_setup = type("S", (), {"actions": [{"action": "password", "css": "#pw", "value": "hunter2"}], "skip_when": ""})()
    with pytest.raises(walk.StateSetupError) as exc:
        walk._run_state_setup(Fake(current_url="http://x/"), v)
    assert "'#pw'" in str(exc.value) and "hunter2" not in str(exc.value)
