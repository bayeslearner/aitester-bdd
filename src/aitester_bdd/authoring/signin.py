"""The sign-in fixture for authoring (spec 05 S2).

A fixture file holds state-setup actions, one per line, in the suite grammar:

    action=open url=https://app.example.test/auth/sign-in
    action=input css=input[type=email] value=env:APP_USER
    action=password css=input[type=password] value=env:APP_PASSWORD
    action=click css=button[type=submit]
    skip_when=[data-sidebar=footer]

`prepare_signed_in_session` runs it in aitester's own agent-browser session and
returns that session's name; the authoring agent then starts signed in and
never sees a credential (values are `env:NAME` references, resolved by Python,
masked in logs). `inject_signin_block` writes the same lines into the authored
suite after its first `[Setup]`, so a replay signs in the same way.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from aitester_bdd.AITester import StateSetup, Verification


def parse_fixture(path: Path) -> StateSetup:
    ss = StateSetup()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kv: dict[str, str] = {}
        for item in line.split():
            if "=" in item:
                k, _, v = item.partition("=")
                kv[k.strip()] = v.strip()
        if "skip_when" in kv:
            ss.skip_when = kv["skip_when"]
        elif "action" in kv:
            ss.actions.append(kv)
        else:
            raise ValueError(f"sign-in fixture: cannot read line {line!r}")
    if not ss.actions:
        raise ValueError("sign-in fixture: no actions")
    if not ss.skip_when:
        raise ValueError("sign-in fixture: skip_when=<signed-in marker> is required so sign-in is verified")
    return ss


def prepare_signed_in_session(fixture: Path, *, session: str | None = None) -> str:
    """Sign a fresh agent-browser session in with the fixture; return its name."""
    import os

    from aitester_bdd.engine.agent_browser_backend import AgentBrowserBackend
    from aitester_bdd.engine.walk import _run_state_setup

    name = session or f"aitester-author-{uuid.uuid4().hex[:8]}"
    os.environ["AITESTER_RUN_SESSION"] = name  # the backend takes its session from here
    browser = AgentBrowserBackend()
    v = Verification(name="signin")
    v.state_setup = parse_fixture(fixture)
    _run_state_setup(browser, v)
    return name


def fixture_robot_lines(fixture: Path) -> list[str]:
    """The fixture as `And I configure state setup` lines, env: references kept."""
    ss = parse_fixture(fixture)
    lines = []
    for a in ss.actions:
        args = "    ".join(f"{k}={v}" for k, v in a.items())
        lines.append(f"    And I configure state setup    {args}")
    lines.append(f"    And I configure state setup    skip_when={ss.skip_when}")
    return lines


def inject_signin_block(suite_path: Path, fixture: Path) -> None:
    """Insert the sign-in block right after the first test case's [Setup] line
    unless the suite already configures state setup."""
    text = suite_path.read_text(encoding="utf-8")
    if "I configure state setup" in text:
        return
    block = "\n".join(fixture_robot_lines(fixture))
    new, n = re.subn(r"(\n    \[Setup\][^\n]*\n)", lambda m: m.group(1) + block + "\n", text, count=1)
    if n != 1:
        raise ValueError("suite has no [Setup] line to attach the sign-in block to")
    suite_path.write_text(new, encoding="utf-8")
