"""A dry replay of an authored suite before the writer accepts it (spec 07 R0).

The write-time checks judge the suite's text. They cannot see a click made before the
page it opens has rendered, the wrong element chosen for a step, or three clicks with
no wait between them; the rc.6 rounds of 2026-10-23 ended on exactly those. So the
suite runs once, with Robot, in a fresh browser session, from its own sign-in block,
and the first failing step goes back to the author.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


def enabled() -> bool:
    return os.environ.get("AITESTER_DRY_REPLAY", "1").strip() != "0"


def retries() -> int:
    try:
        return max(0, int(os.environ.get("AITESTER_DRY_REPLAY_RETRIES", "3")))
    except ValueError:
        return 3


def timeout_s() -> float:
    try:
        return max(30.0, float(os.environ.get("AITESTER_DRY_REPLAY_TIMEOUT", "600")))
    except ValueError:
        return 600.0


def _first_failure(out_dir: Path) -> str | None:
    """The first failing check or action in the walk log, in words the author can act on."""
    log = next(iter(out_dir.rglob("walk_log.jsonl")), None)
    if log is None:
        return None
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("kind") == "state_check" and e.get("ok") is False:
            return (
                f"rule {e.get('rule')!r}: check {e.get('check')} on {e.get('locator')!r} failed; "
                f"expected {e.get('expected')!r}, observed {str(e.get('observed'))[:200]!r}"
            )
        if e.get("kind") == "after_action" and e.get("raised"):
            return f"rule {e.get('rule')!r}: action {e.get('action')} on {e.get('target')!r} raised"
        if e.get("kind") == "rule_exit" and e.get("passed") is False:
            return f"rule {e.get('rule')!r} failed: {e.get('failure_step_kind')}"
    return None


def dry_replay(suite_text: str, *, before: str | None = None, timeout: float | None = None) -> tuple[bool, str]:
    """Run `suite_text` once with Robot in a fresh browser session; (ok, summary).

    `before` is a shell command run first (the Archestra wrapper points it at its lab
    clean-up, since the dry replay creates what the exploration created). The process
    environment is inherited, so the suite's `env:` references resolve here and never
    in the agent. `AITESTER_RUN_SESSION` is set to a fresh name so the replay's browser
    is not the author's.
    """
    before = before if before is not None else os.environ.get("AITESTER_DRY_REPLAY_BEFORE")
    timeout = timeout or timeout_s()
    tmp = Path(tempfile.mkdtemp(prefix="aitester-dry-"))
    try:
        if before:
            pre = subprocess.run(before, shell=True, capture_output=True, text=True, timeout=120, check=False)
            if pre.returncode != 0:
                return False, f"dry replay not run: the before-command failed ({pre.returncode}): {(pre.stderr or pre.stdout)[-300:]}"
        suite = tmp / "dry.robot"
        suite.write_text(suite_text, encoding="utf-8")
        env = dict(os.environ)
        env["AITESTER_RUN_SESSION"] = f"aitester-dry-{uuid.uuid4().hex[:8]}"
        env.setdefault("AITESTER_AI_DIAGNOSIS", "off")
        env["AITESTER_BROWSER"] = env.get("AITESTER_BROWSER") or "agent-browser"
        try:
            r = subprocess.run(
                [sys.executable, "-m", "robot", "--outputdir", str(tmp / "out"), str(suite)],
                capture_output=True, text=True, timeout=timeout, check=False, env=env, cwd=str(tmp),
            )
        except subprocess.TimeoutExpired:
            return False, f"dry replay did not finish in {timeout:.0f} s (AITESTER_DRY_REPLAY_TIMEOUT); shorten the waits or split the rule"
        if r.returncode == 0:
            return True, "dry replay passed: every rule ran and every check found its element"
        first = _first_failure(tmp / "out")
        if first is None:
            tail = "\n".join((r.stdout or "").splitlines()[-12:])
            first = f"Robot: {tail[-600:]}"
        return False, f"dry replay failed at {first}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
