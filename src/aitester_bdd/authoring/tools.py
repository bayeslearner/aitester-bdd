"""Terminal tools for the authoring agent — WISE-style.

The agent drives the live target by shelling out to the `agent-browser`
CLI via DeepAgents' `execute` tool (from LocalShellBackend). The Python
side keeps only the **terminal** tools:

  - author mode: `write_robot_suite`, `report_bug`
  - explore mode: `journey_complete`, `journey_blocked`

Their outcome is held in a `TerminalState` owned by the caller, not read
back from the transcript: the first successful terminal call wins, later
ones are refused, and `StopWhenDone` ends the agent loop before the next
model call. A rejected call (an unparseable suite) comes back to the agent
as an error and the loop goes on. A subagent that calls a terminal tool
updates the same state.

This mirrors wise-rpa-bdd: no wrappers around individual browser
operations — the agent uses bash directly, batches calls with `&&`, and
reads JSON from `agent-browser --json` output natively.
"""
from __future__ import annotations

import atexit
import io
import logging
import os
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

log = logging.getLogger("aitester_bdd.authoring.tools")


# ─── agent-browser session ───────────────────────────────────────────────


_SESSION_ID: str | None = None
_AGENT_BROWSER_BIN: str | None = None


def _resolve_bin() -> str:
    global _AGENT_BROWSER_BIN
    if _AGENT_BROWSER_BIN is not None:
        return _AGENT_BROWSER_BIN
    bin_path = shutil.which("agent-browser")
    if not bin_path:
        raise RuntimeError(
            "agent-browser CLI not found on PATH. Install via "
            "`npm i -g agent-browser`."
        )
    _AGENT_BROWSER_BIN = bin_path
    return bin_path


def session_id() -> str:
    """Per-process agent-browser session — fresh per authoring run.

    AITESTER_AUTHOR_SESSION names an existing session instead, for example one
    a fixture signed in through the app's own form, so the agent starts signed
    in and no password reaches the model. Such a session is left open.
    """
    global _SESSION_ID
    if _SESSION_ID is None:
        given = os.environ.get("AITESTER_AUTHOR_SESSION", "").strip()
        if given:
            _SESSION_ID = given
        else:
            _SESSION_ID = f"aitester-author-{uuid.uuid4().hex[:8]}"
            atexit.register(_cleanup_session)
    return _SESSION_ID


def _cleanup_session() -> None:
    if _SESSION_ID is None:
        return
    try:
        subprocess.run(
            [_resolve_bin(), "--session", _SESSION_ID, "close", "--json"],
            timeout=10, capture_output=True, check=False,
        )
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        log.warning("could not close agent-browser session %s: %s", _SESSION_ID, exc)


# ─── Terminal state ──────────────────────────────────────────────────────


@dataclass
class TerminalState:
    """The one terminal outcome of an agent run. First call wins.

    kind: "suite" | "bug" (author mode), "complete" | "blocked" (explore mode).
    """

    kind: str | None = None
    path: Path | None = None
    text: str = ""

    @property
    def done(self) -> bool:
        return self.kind is not None

    def _refusal(self) -> str | None:
        if self.done:
            return (
                f"REFUSED: this run already ended with {self.kind}"
                f"{f' ({self.path})' if self.path else ''}. Stop now."
            )
        return None


# Selector syntax the agent-browser and nodriver runtimes cannot run (spec 05 R1).
# Playwright accepts these; the suite must stay portable across the three engines.
_NON_CSS = (
    (":has-text(", ":has-text() is Playwright-only; use a CSS attribute or an @ref-free selector"),
    (":text(", ":text() is Playwright-only"),
    (":text-is(", ":text-is() is Playwright-only"),
    ("text=", "text= is Playwright-only; use 'When I click text \"…\"' for text clicks"),
    (":visible", ":visible is Playwright-only; use 'is visible' as a check"),
    (":nth-match(", ":nth-match() is Playwright-only"),
    (">>", ">> is Playwright-only; use descendant CSS or set child scope"),
)
# Keyword arguments that hold a selector: quoted CSS after these words, or k=v options.
_SELECTOR_KEYWORDS = ("locator", "selector", "into locator", "await=", "css=", "locator=", "scope ")
_COUNT_EQ = re.compile(r'count of locator\s+"[^"]*"\s+equals\s+(\d+)', re.I)
# A locator that is only a tag name matches the first such element on the page: the first
# <button> on a projects page is rarely the one the author clicked during exploration.
_BARE_TAG = re.compile(r"^(?:[a-z][a-z0-9]*)(?:\s*,\s*[a-z][a-z0-9]*)*$", re.I)
# An id captured while exploring (a project or chat created in that session) is gone at replay.
# Three or more chained utility classes (Tailwind) describe styling, not the element.
_UTILITY_CHAIN = re.compile(r"(\.[a-z0-9:_\-\[\]/]+){3,}", re.I)
# Steps that act on or read one element: a selector that matches several at write time
# will act on the first, which is rarely the one the author used.
_SINGLE_ELEMENT = re.compile(
    r"I click locator|into locator|I type|locator \"[^\"]+\" (has text|contains|matches|is visible|is hidden|"
    r"is enabled|is disabled|has attribute|has class)|input \"[^\"]+\" has value|content of locator",
)
# [attr=value] and #id pieces of a selector: each value must have been seen in the browser
# output of this run (a `get attr`, `get html`, `eval`), since a snapshot shows accessible
# names and not attributes, and the author kept inferring aria-labels from them.
_ATTR_VALUE = re.compile(r"\[\s*([a-zA-Z_:][-\w:.]*)\s*[~|^$*]?=\s*(\"([^\"]*)\"|'([^']*)'|([^\]\s]+))\s*\]")
_ID_VALUE = re.compile(r"#([-\w]+)")
_UNCHECKED_ATTRS = {"role", "type", "disabled", "checked", "hidden", "selected", "open", "required", "readonly", "aria-selected", "aria-expanded", "aria-disabled", "aria-checked", "aria-hidden", "data-state"}
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_SELECTOR_RE = re.compile(r'(?:locator|selector|scope)\s+"([^"]+)"|(?:await|css|locator)=("?)([^\s"]+)\2')


def _selectors_in(line: str) -> list[str]:
    out = []
    for m in _SELECTOR_RE.finditer(line):
        sel = m.group(1) or m.group(3)
        if sel and not sel.startswith("@") and "${" not in sel and "%{" not in sel:
            out.append(sel)
    return out


def _rules(content: str) -> list[tuple[str, list[str]]]:
    """(rule name, its body lines) for every `I define rule` block in the suite."""
    out: list[tuple[str, list[str]]] = []
    for line in content.splitlines():
        m = re.match(r'\s*I define rule\s+"([^"]+)"', line)
        if m:
            out.append((m.group(1), []))
        elif out and line.startswith("        ") and line.strip():
            out[-1][1].append(line.strip())
    return out


def _unseen_values(sel: str, observed: str) -> list[str]:
    """The attribute values in `sel` that never appeared in `observed`."""
    out = []
    for m in _ATTR_VALUE.finditer(sel):
        attr, value = m.group(1), m.group(3) if m.group(3) is not None else m.group(4) if m.group(4) is not None else m.group(5)
        if attr.lower() in _UNCHECKED_ATTRS or not value or "${" in value or "%{" in value:
            continue
        if not re.search(re.escape(attr) + r"\s*=\s*[\"']?" + re.escape(value), observed, re.I):
            out.append(f"{attr}={value}")
    for m in _ID_VALUE.finditer(sel):
        value = m.group(1)
        if not re.search(r"\bid\s*=\s*[\"']?" + re.escape(value) + r"\b", observed, re.I):
            out.append(f"id={value}")
    return out


def suite_problems(
    content: str, *, engine: str = "agent-browser", probe: Callable[[list[str]], list[int]] | None = None,
    observed: str | None = None,
) -> list[str]:
    """Why `content` is not a runnable .robot suite; empty when it is.

    Checks, in order: Robot syntax; at least one test case; selectors the
    declared engine cannot run (R1); exact element counts above 1 (R5, flaky
    by construction unless the story names the number); shell actions (S3,
    opt in with `# allow-shell`); and, with `probe`, that every pinned CSS
    selector parses in the live browser (-1 from the probe = invalid).
    """
    from robot.api import TestSuite
    from robot.api.parsing import ModelVisitor, get_model

    problems: list[str] = []

    class _Errors(ModelVisitor):
        def generic_visit(self, node):  # noqa: N802 — robot visitor API
            problems.extend(getattr(node, "errors", ()) or ())
            if getattr(node, "error", None):
                problems.append(node.error)
            super().generic_visit(node)

    model = get_model(io.StringIO(content))
    _Errors().visit(model)
    if not problems and not TestSuite.from_model(model).tests:
        problems.append("the suite has no test case under *** Test Cases ***")
    if problems:
        return problems

    selectors: list[tuple[int, str]] = []
    for n, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("*** "):
            continue
        if _UUID.search(line) and "fixed-id" not in line:
            problems.append(
                f"line {n}: a UUID in the suite is the id of something that existed while you explored; "
                f"a project, chat or run created by the suite gets a new id at replay. Reach it by name or "
                f"position instead, or append '# fixed-id: intended' when the thing is permanent (an agent, a user)"
            )
        if stripped.startswith("${"):
            continue
        for sel in _selectors_in(line):
            selectors.append((n, sel))
            if engine != "playwright":
                for bad, why in _NON_CSS:
                    if bad in sel:
                        problems.append(f"line {n}: selector {sel!r}: {why}")
                        break
                if re.search(r"\S\|\S", sel):
                    problems.append(f"line {n}: selector {sel!r}: a fallback needs spaces around the bar ('a | b')")
            if _UTILITY_CHAIN.search(sel) and "[" not in sel.split(".")[0]:
                problems.append(
                    f"line {n}: selector {sel!r} is a chain of styling classes that changes with the theme; "
                    f"use a data attribute, id, aria-label, href or 'When I click text \"…\"'"
                )
            if observed is not None:
                unseen = _unseen_values(sel, observed)
                if unseen:
                    problems.append(
                        f"line {n}: selector {sel!r} pins {', '.join(unseen)}, which never appeared in this "
                        f"run's browser output; a snapshot shows accessible names, not attributes. Read the "
                        f"element with get attr / get html / eval and pin what it returns, or use 'When I click text \"…\"'"
                    )
            if _BARE_TAG.match(sel):
                problems.append(
                    f"line {n}: selector {sel!r} is only a tag name and matches the first such element on the "
                    f"page (for body: the whole page, so 'contains' is true wherever the words appear); pin the "
                    f"one you used (data-testid, id, aria-label, href, name) or use 'When I click text \"…\"'"
                )
        m = _COUNT_EQ.search(line)
        if m and int(m.group(1)) >= 2 and "exact-count" not in line:
            problems.append(
                f"line {n}: exact count {m.group(1)} breaks on unrelated UI changes; use "
                f"'count of locator … is at least N', or append '# exact-count: intended' when the story names the number"
            )
        if re.search(r"I run shell\s+\"", line) and "# allow-shell" not in content:
            problems.append(
                f"line {n}: a shell action runs a command on the test machine at replay time; "
                f"only when the story asks for shell checks, and then add a '# allow-shell' comment to the suite"
            )
    for name, body in _rules(content):
        meaningful = [ln for ln in body if not re.search(r'declare parents|selector "(body|html)" exists', ln)]
        if not meaningful:
            problems.append(
                f"rule {name!r} does nothing: it has no action and no check beyond the page existing; "
                f"write the steps the story asks for or drop the rule"
            )
    if probe is not None and not problems and selectors:
        unique = sorted({sel for _, sel in selectors})
        try:
            counts = probe(unique)
        except Exception as exc:  # the probe is advisory; a broken probe must not pass a bad suite silently
            problems.append(f"selector check could not run in the browser: {exc}")
            return problems
        count_of = dict(zip(unique, counts, strict=True))
        lines = content.splitlines()
        for n, sel in selectors:
            c = count_of[sel]
            if c == -1:
                problems.append(f"line {n}: selector {sel!r} does not parse in the browser (not CSS)")
            elif c > 1 and _SINGLE_ELEMENT.search(lines[n - 1]) and "first-match" not in lines[n - 1]:
                problems.append(
                    f"line {n}: selector {sel!r} matches {c} elements on the page right now and this step "
                    f"acts on one; pin it further (an attribute, a scope, 'When I click text \"…\"'), or append "
                    f"'# first-match: intended' when the first one is the one you mean"
                )
    return problems


def stop_when_done(state: TerminalState):
    """Middleware that ends the agent loop once `state` holds a result.

    Runs before each model call, so the turn that made the terminal call is
    the last one; no further model call is made.
    """
    from langchain.agents.middleware import AgentMiddleware, hook_config

    class StopWhenDone(AgentMiddleware):
        @hook_config(can_jump_to=["end"])
        def before_model(self, agent_state, runtime):  # noqa: ARG002 — hook API
            return {"jump_to": "end"} if state.done else None

    return StopWhenDone()


# ─── Author-mode terminal tools ──────────────────────────────────────────


class WriteRobotSuiteParams(BaseModel):
    content: str = Field(description="Complete .robot file body. Must be valid Robot Framework.")


class ReportBugParams(BaseModel):
    content: str = Field(
        description=(
            "Bug report body: what you tried (including every UI navigation path), "
            "what you observed, why testing this story is blocked."
        )
    )


def build_tools(
    state: TerminalState, *, suite_path: Path, bug_report_path: Path,
    engine: str = "agent-browser", probe: Callable[[list[str]], list[int]] | None = None,
    observed: Any = None,
) -> list[StructuredTool]:
    """The two author-mode terminal tools, writing to fixed paths. The agent
    drives the page through the `browser` tool (`build_browser_tool`)."""

    def write_robot_suite(content: str) -> str:
        if refusal := state._refusal():
            return refusal
        problems = suite_problems(
            content, engine=engine, probe=probe,
            observed=observed.text if observed is not None else None,
        )
        if problems:
            # Not terminal: the agent fixes the suite and calls again.
            return (
                "ERROR: not a runnable suite: " + "; ".join(problems[:8])
                + ". Fix these lines and call write_robot_suite again; a refused write is not a "
                "reason to file a bug report."
            )
        suite_path.parent.mkdir(parents=True, exist_ok=True)
        suite_path.write_text(content, encoding="utf-8")
        state.kind, state.path = "suite", suite_path
        return f"OK: wrote {len(content)} bytes to {suite_path}. Authoring is done."

    def report_bug(content: str) -> str:
        if refusal := state._refusal():
            return refusal
        bug_report_path.parent.mkdir(parents=True, exist_ok=True)
        bug_report_path.write_text(content, encoding="utf-8")
        state.kind, state.path, state.text = "bug", bug_report_path, content
        return f"OK: wrote bug report to {bug_report_path}. Authoring is done."

    return [
        StructuredTool.from_function(
            func=write_robot_suite, name="write_robot_suite",
            args_schema=WriteRobotSuiteParams,
            description=(
                "TERMINAL TOOL. Write the complete .robot suite. Call only when "
                "every selector traces to a stable attribute observed on the "
                "live page. The suite is parsed and its selectors checked first "
                "(plain CSS that parses in the browser); any problem comes back "
                "so you can fix it. On success the run ends."
            ),
        ),
        StructuredTool.from_function(
            func=report_bug, name="report_bug",
            args_schema=ReportBugParams,
            description=(
                "TERMINAL TOOL. Write a bug report when the app is broken in a "
                "way that prevents authoring (missing feature, error page, "
                "untestable terminal state). A typed URL that redirects is NOT "
                "a bug by itself: first reach the page through the app's own "
                "navigation (sidebar, menus, mode toggles, links) and list every "
                "path you tried in the report. Do NOT use for selector difficulty "
                "or async timing. The run ends."
            ),
        ),
    ]


class BrowserParams(BaseModel):
    command: str | None = Field(default=None, description="One agent-browser command line, e.g. \"snapshot -c -i\".")
    commands: list[str] | None = Field(default=None, description="Several command lines run in order; stops at the first failure.")


def build_browser_tool(*, session: str, base_url: str | None, observed: Any = None) -> StructuredTool:
    """The one way an in-process author drives the page: an allowlisted
    agent-browser command in a pinned session, no shell (spec 05 S1).
    `observed` (mcp_tools.Observed) collects what the agent saw for the suite lint."""
    from aitester_bdd.authoring.mcp_tools import run_browser_commands

    def browser(command: str | None = None, commands: list[str] | None = None) -> str:
        cmds = list(commands or []) + ([command] if command else [])
        if not cmds:
            return "ERROR: give command or commands"
        return run_browser_commands(cmds, session=session, base_url=base_url, observed=observed)

    return StructuredTool.from_function(
        func=browser, name="browser", args_schema=BrowserParams,
        description=(
            "Run agent-browser commands in the test's browser session and return their output. "
            "Pass one command, or a list run in order that stops at the first failure, e.g. "
            "['open https://app/', 'wait 1500', 'snapshot -c -i'], 'click @e3', 'get count .row', "
            "'fill #q hello', 'eval \"document.title\"'. Add --json for JSON."
        ),
    )


# ─── Explore-mode terminal tools ─────────────────────────────────────────


class JourneyCompleteParams(BaseModel):
    notes: str = Field(description="Step-by-step summary of what you did and observed. Include selectors clicked, values typed, toasts seen, state verified.")


class JourneyBlockedParams(BaseModel):
    report: str = Field(description="What you tried, what you observed, why the journey could not be completed.")


def build_explore_tools(state: TerminalState) -> list[StructuredTool]:
    """Terminal tools for explore mode (no suite writing)."""

    def journey_complete(notes: str) -> str:
        if refusal := state._refusal():
            return refusal
        state.kind, state.text = "complete", notes
        return f"EXPLORE_DONE: passed=true\n{notes}"

    def journey_blocked(report: str) -> str:
        if refusal := state._refusal():
            return refusal
        state.kind, state.text = "blocked", report
        return f"EXPLORE_DONE: passed=false\n{report}"

    return [
        StructuredTool.from_function(
            func=journey_complete, name="journey_complete",
            args_schema=JourneyCompleteParams,
            description=(
                "TERMINAL TOOL. Call when you have successfully completed "
                "the entire journey described in the story. Provide a "
                "step-by-step summary of what you did and observed."
            ),
        ),
        StructuredTool.from_function(
            func=journey_blocked, name="journey_blocked",
            args_schema=JourneyBlockedParams,
            description=(
                "TERMINAL TOOL. Call when the journey cannot be completed — "
                "the page doesn't render, a required element is missing, or "
                "an action fails. A typed URL that redirects is not enough: "
                "try the app's own navigation first. Describe what you tried "
                "and what blocked you."
            ),
        ),
    ]
