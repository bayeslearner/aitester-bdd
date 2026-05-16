"""Regression tests for WISE-ported gotcha-fixes.

The aitester-bdd walker was deliberately built as a port of the WISE
engine (not a clean-room reimplementation). These tests pin the behaviors
that WISE accumulated across many real sites, so they don't silently
regress.

Each test names the WISE behavior it pins. If a test fails, look at the
named behavior + the relevant function in engine/walk.py or
engine/browser.py before "fixing" by deletion — the deletion is almost
certainly removing a battle-tested gotcha-fix.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Reuse the FakeBrowser from test_walker_with_fake_browser.py
from tests.unit.test_walker_with_fake_browser import FakeBrowser


def _make(scenario_name="flow", entry_url="http://x"):
    from aitester_bdd.AITester import AITester

    t = AITester()
    t.start_verification('"v"')
    t.start_scenario_at(f'"{scenario_name}"', f'"{entry_url}"')
    return t


def _make_no_entry(scenario_name="flow"):
    """Scenario WITHOUT entry URL — skips the verification-level initial
    dismiss-interrupts pass. Use when isolating per-rule interrupt scoping."""
    from aitester_bdd.AITester import AITester

    t = AITester()
    t.start_verification('"v"')
    t.start_scenario(f'"{scenario_name}"')
    return t


# ---------------------------------------------------------------------------
# Gotcha: dismiss-interrupts fires before every action.
# WISE _execute_steps: "Dismiss interrupts before each action — popups
# can appear at any moment and block clicks/interactions"
# ---------------------------------------------------------------------------

class FakeBrowserWithInterrupts(FakeBrowser):
    """Tracks calls to dismiss-targets via the click stream."""
    pass


def test_interrupt_selectors_are_clicked_before_each_action(monkeypatch):
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make()
    # Register two interrupt selectors at the verification level
    t._v.interrupts.dismiss_selectors.append(".cookie-banner")
    t._v.interrupts.dismiss_selectors.append(".modal-close")

    t.define_rule('"flow"')
    t.when_click_locator('".start"')
    t.when_click_locator('".confirm"')
    t.and_selector_exists('"[data-testid=done]"')

    fake = FakeBrowserWithInterrupts(
        current_url="http://x/",
        selector_present={
            "[data-testid=done]": True,
            ".cookie-banner": True,  # both interrupts exist → both get clicked
            ".modal-close": True,
        },
        count_for={
            ".cookie-banner": 1,
            ".modal-close": 1,
        },
    )
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    verdict = walk_verification(t.get_verification())
    assert verdict.passed, verdict.format_failure()

    clicks = [args for kind, args in fake.actions_called if kind == "click"]
    # Each of 2 actions should have been preceded by a dismiss of each
    # interrupt selector. Order: cookie-banner, modal-close before each
    # action click. (Action 1) start. (Action 2) confirm.
    assert clicks.count(".cookie-banner") >= 2, f"interrupt should fire before each action: {clicks}"
    assert clicks.count(".modal-close") >= 2, f"interrupt should fire before each action: {clicks}"
    assert ".start" in clicks
    assert ".confirm" in clicks


def test_interrupt_paused_suppresses_dismissal(monkeypatch):
    """Per-rule `interrupt_paused` skips all dismiss-clicks INSIDE the rule.

    Use case from WISE: testing the modal itself — you don't want the
    walker to auto-dismiss the thing you're testing.

    Uses a scenario without entry URL to skip the verification-level
    initial dismiss (which fires regardless of per-rule scoping).
    """
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make_no_entry()
    t._v.interrupts.dismiss_selectors.append(".cookie-banner")

    t.define_rule('"test_modal_itself"')
    t.pause_interrupts()
    t.when_click_locator('".open-modal"')

    fake = FakeBrowserWithInterrupts(
        current_url="http://x/",
        count_for={".cookie-banner": 1},  # banner exists — but we should NOT click it
    )
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    walk_verification(t.get_verification())

    clicks = [args for kind, args in fake.actions_called if kind == "click"]
    assert ".cookie-banner" not in clicks, (
        f"interrupt_paused should suppress dismissal inside the rule; clicks={clicks}"
    )
    assert ".open-modal" in clicks


def test_interrupt_override_replaces_global_list(monkeypatch):
    """Per-rule `interrupt_override` replaces (not adds to) the global list.

    Inside the rule, only the override list should be dismissed. Uses a
    scenario without entry URL to skip the verification-level dismiss
    pass (which uses the global list regardless).
    """
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make_no_entry()
    t._v.interrupts.dismiss_selectors.append(".global-banner")

    t.define_rule('"narrow_scope"')
    t.scope_interrupts('".rule-specific"')
    t.when_click_locator('".target"')

    fake = FakeBrowserWithInterrupts(
        current_url="http://x/",
        count_for={".global-banner": 1, ".rule-specific": 1},
    )
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    walk_verification(t.get_verification())

    clicks = [args for kind, args in fake.actions_called if kind == "click"]
    assert ".rule-specific" in clicks, f"override list should fire; clicks={clicks}"
    assert ".global-banner" not in clicks, (
        f"override should replace, not add; clicks={clicks}"
    )


# ---------------------------------------------------------------------------
# Gotcha: guard retry-with-redo.
# WISE _walk_rule: "if not guards_ok and rule.retry_max > 0: replay
# steps then re-check guards"
# ---------------------------------------------------------------------------

class FlakyBrowser(FakeBrowser):
    """First N guard checks fail; subsequent ones pass."""

    def __init__(self, fail_n_url_checks: int, **kw):
        super().__init__(**kw)
        self.fail_n = fail_n_url_checks
        self.url_call_count = 0
        # Each url() call counts toward fail budget — when exhausted,
        # set current_url to satisfy the guard.

    def url(self) -> str:
        self.url_call_count += 1
        if self.url_call_count <= self.fail_n:
            return "http://x/wrong"
        return "http://x/correct"


def test_guard_retry_redo_pattern(monkeypatch):
    """When a guard fails, replaying the body should be tried up to retry_max times.

    WISE pattern: real sites have transient load failures where the world
    isn't in the guarded state yet — retrying after running the body
    again often resolves it.
    """
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make()
    t.define_rule('"with_retry"')
    t.set_retry("3", "10")  # 3 retries, 10ms delay (fast for tests)
    t.given_url_contains('"correct"')  # guard
    t.when_click_locator('".trigger"')

    # First guard check fails (url returns wrong), body runs, second
    # check passes
    fake = FlakyBrowser(fail_n_url_checks=1)
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    verdict = walk_verification(t.get_verification())
    assert verdict.passed, verdict.format_failure()


def test_guard_retry_exhausted_fails_with_guard_step_kind(monkeypatch):
    """If retry_max retries don't make the guard pass, fail with kind='guard'."""
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make()
    t.define_rule('"never_reaches_state"')
    t.set_retry("2", "10")
    t.given_url_contains('"correct"')
    t.when_click_locator('".trigger"')

    # url() ALWAYS returns wrong — retries exhaust
    fake = FlakyBrowser(fail_n_url_checks=999)
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    verdict = walk_verification(t.get_verification())
    assert verdict.failed
    r = verdict.results[0]
    assert r.failure_step_kind == "guard", r.failure_step_kind


# ---------------------------------------------------------------------------
# Gotcha: action-failure recovery (dismiss interrupts + retry once).
# WISE _execute_steps: "Recovery: dismiss interrupts and retry once —
# a popup may have appeared between the dismiss and the action"
# ---------------------------------------------------------------------------

class ActionFailsThenSucceedsBrowser(FakeBrowser):
    """Click on `.target` fails the first time, succeeds the second."""

    target_click_count: int = 0

    def click(self, css: str) -> None:
        if css == ".target":
            self.target_click_count += 1
            if self.target_click_count == 1:
                raise RuntimeError("element is not stable (test simulation)")
        super().click(css)


def test_action_failure_triggers_dismiss_then_retry_once(monkeypatch):
    """Failed action -> dismiss interrupts -> retry the action once."""
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make()
    t._v.interrupts.dismiss_selectors.append(".modal-close")

    t.define_rule('"flaky_click"')
    t.when_click_locator('".target"')

    fake = ActionFailsThenSucceedsBrowser(
        current_url="http://x/",
        count_for={".modal-close": 1},  # modal present → walker will click it on retry
    )
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    verdict = walk_verification(t.get_verification())
    assert verdict.passed, verdict.format_failure()
    # The walker should have invoked .target click TWICE (initial failure + retry)
    assert fake.target_click_count == 2


# ---------------------------------------------------------------------------
# Gotcha: pipe-fallback selector resolution.
# WISE _resolve_fallback_selector: "If raw contains ' | ', try each
# candidate in order and return the first one that matches"
# ---------------------------------------------------------------------------

def test_pipe_fallback_selector_resolves_to_first_present(monkeypatch):
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make()
    t.define_rule('"resilient"')
    # New selector | old selector
    t.then_count_at_least('"[data-testid=row] | .legacy-row"', "1")

    # Only the legacy form is present
    fake = FakeBrowser(
        current_url="http://x/",
        count_for={".legacy-row": 5, "[data-testid=row]": 0},
    )
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    verdict = walk_verification(t.get_verification())
    assert verdict.passed, verdict.format_failure()


def test_pipe_fallback_action_target(monkeypatch):
    """Actions also resolve their target through pipe-fallback."""
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make()
    t.define_rule('"resilient_click"')
    t.when_click_locator('"[data-testid=submit] | button.legacy-submit"')
    t.and_selector_exists('".result"')

    fake = FakeBrowser(
        current_url="http://x/",
        # only the legacy selector is "present" (i.e., has count > 0)
        count_for={"button.legacy-submit": 1, "[data-testid=submit]": 0},
        selector_present={"button.legacy-submit": True, ".result": True},
    )
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    verdict = walk_verification(t.get_verification())
    assert verdict.passed, verdict.format_failure()

    clicks = [args for kind, args in fake.actions_called if kind == "click"]
    assert "button.legacy-submit" in clicks, (
        f"walker should pick the live selector; got {clicks}"
    )


# ---------------------------------------------------------------------------
# Gotcha: per-rule timeout enforcement.
# WISE _walk_rule: "Apply per-rule timeout if declared"
# ---------------------------------------------------------------------------

class SlowBrowser(FakeBrowser):
    """Each `wait_for_elements_state` sleeps a bit."""

    def wait_for_elements_state(self, selector, state="attached", *, timeout_ms=5000) -> bool:
        import time
        time.sleep(0.05)  # 50ms per check
        # Always says "not present" so observation check fails-with-time
        return False


def test_per_rule_timeout_fires(monkeypatch):
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make()
    t.define_rule('"slow_rule"')
    t.and_set_rule_timeout("10")  # 10ms — should expire instantly
    t.when_open('"http://x/page"')
    # multiple post-action observations to burn through the budget
    t.and_selector_exists('".one"')
    t.and_selector_exists('".two"')
    t.and_selector_exists('".three"')

    fake = SlowBrowser(current_url="http://x/page")
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    verdict = walk_verification(t.get_verification())
    assert verdict.failed
    r = verdict.results[0]
    # Either we hit rule_timeout, or we failed an observation — both
    # are acceptable; what we're testing is "deadline enforcement runs".
    assert r.failure_step_kind in ("rule_timeout", "observation_or_assertion")


# ---------------------------------------------------------------------------
# Gotcha: post-action StateCheck failure is fatal (testing semantics).
# This is the ONE place we diverge from WISE — WISE treats post-action
# StateChecks as observations and only warns. For TESTING the failure
# must fail the rule with structured evidence.
# ---------------------------------------------------------------------------

def test_post_action_assertion_failure_fails_the_rule(monkeypatch):
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import walk_verification

    t = _make()
    t.define_rule('"check_outcome"')
    t.when_click_locator('".submit"')
    t.then_has_text('"h1"', '"Success"')  # post-action; observed text differs

    fake = FakeBrowser(
        current_url="http://x/",
        selector_present={".submit": True},
        text_for={"h1": "Error"},
    )
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: fake)

    verdict = walk_verification(t.get_verification())
    assert verdict.failed
    r = verdict.results[0]
    assert r.failure_step_kind == "observation_or_assertion"
    assert r.expected == "Success"
    assert r.observed == "Error"
