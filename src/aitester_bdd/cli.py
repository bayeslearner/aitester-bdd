"""aitester CLI — author / run / doctor.

  aitester author --story "..." --base-url http://localhost:5173
  aitester run path/to/suite.robot
  aitester doctor
  aitester version
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import typer

app = typer.Typer(
    name="aitester",
    help="Agent-loop authoring of Robot Framework BDD test suites.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the package version."""
    from aitester_bdd import __version__
    typer.echo(__version__)


@app.command()
def author(
    story: str = typer.Option(..., "--story", "-s", help="Plain-English intention to verify."),
    base_url: str = typer.Option(..., "--base-url", "-u", help="URL of the live target app."),
    out: str = typer.Option("suite.robot", "--out", "-o", help="Output path for the .robot suite."),
    triage_dir: str = typer.Option("triage", "--triage-dir", help="Directory for bug reports when authoring is blocked."),
    source_root: str | None = typer.Option(None, "--source-root", help="Optional source root for white-box read_file access."),
    engine: str = typer.Option(
        "agent-browser", "--engine", "-e",
        help="Runtime engine to declare in the authored suite (agent-browser | playwright | nodriver). "
             "All three accept CSS selectors so the suite is portable; `aitester run` reads ${ENGINE} "
             "from the suite and sets AITESTER_BROWSER accordingly.",
    ),
    max_iters: int = typer.Option(100, "--max-iters", help="Max agent iterations per attempt before bailing."),
    max_attempts: int = typer.Option(2, "--max-attempts", help="Retry the whole authoring loop up to N times on crash / recursion limit."),
    llm_model: str | None = typer.Option(None, "--llm-model", help="LLM model spec (overrides AITESTER_LLM_MODEL). Bare name, e.g. claude-sonnet-5-5 or cc/claude-opus-4-7."),
    llm_base_url: str | None = typer.Option(None, "--llm-base-url", help="LLM endpoint URL (overrides AITESTER_LLM_BASE_URL / OPENAI_BASE_URL)."),
    llm_api_key: str | None = typer.Option(None, "--llm-api-key", help="LLM API key (overrides AITESTER_LLM_API_KEY / OPENAI_API_KEY)."),
    debug: bool = typer.Option(
        False, "--debug", "-d",
        help="Stream each agent step (tool calls + results) to stderr so you can watch the explorer work.",
    ),
    signin: str | None = typer.Option(
        None, "--signin",
        help="A sign-in fixture file: one state-setup action per line (action=open url=…; "
             "action=input css=… value=env:APP_USER; action=password css=… value=env:APP_PASSWORD; "
             "action=click css=…; skip_when=<signed-in marker css>). aitester signs the browser in "
             "before the agent starts, so the agent never sees a credential, and writes the same "
             "block into the authored suite so a replay signs in the same way.",
    ),
    agent: str = typer.Option(
        "deepagents", "--agent",
        help="Who authors: 'deepagents' (in-process, default) or 'acp:<command>' for an external "
             "agent over ACP, e.g. 'acp:npx -y @agentclientprotocol/claude-agent-acp'. Needs the "
             "[acp] extra; the agent's own model settings go in AITESTER_AGENT_ENV.",
    ),
) -> None:
    """Run the authoring agent loop.

    Exploration uses Playwright sync API in a worker thread, producing
    CSS-grounded snapshots. The agent grounds every selector in real DOM
    attributes — no inference. Authored suite declares ${ENGINE} so
    `aitester run` picks the matching runtime backend.
    """
    if engine not in ("agent-browser", "playwright", "nodriver"):
        typer.echo(f"[author] ✗ unknown engine {engine!r}; expected agent-browser | playwright | nodriver")
        raise typer.Exit(code=2)

    suite_path = Path(out)
    triage_path = Path(triage_dir)
    src_root = Path(source_root) if source_root else None

    typer.echo(f"[author] story={story!r}")
    typer.echo(f"[author] base_url={base_url}")
    typer.echo(f"[author] engine={engine} (declared in suite as ${{ENGINE}})")
    typer.echo(f"[author] suite_path={suite_path}, triage_dir={triage_path}")
    if src_root:
        typer.echo(f"[author] source_root={src_root}")

    if signin:
        from aitester_bdd.authoring.signin import prepare_signed_in_session

        try:
            session = prepare_signed_in_session(Path(signin))
        except Exception as exc:
            typer.echo(f"[author] ✗ sign-in fixture failed: {exc}")
            raise typer.Exit(code=2) from exc
        os.environ["AITESTER_AUTHOR_SESSION"] = session
        typer.echo(f"[author] signed in (fixture {signin}); session {session}")

    if agent.startswith("acp:"):
        try:
            from aitester_bdd.authoring.acp_author import author_with_acp
        except ImportError as exc:
            typer.echo(f"[author] ✗ --agent acp needs the [acp] extra (pip install aitester-bdd[acp]): {exc}")
            raise typer.Exit(code=2) from exc
        typer.echo(f"[author] agent=ACP {agent[4:]!r}")
        result = author_with_acp(
            agent_command=agent[4:],
            story=story,
            base_url=base_url,
            suite_path=suite_path,
            bug_report_dir=triage_path,
            engine=engine,
            debug=debug,
        )
    elif agent == "deepagents":
        from aitester_bdd.authoring.agent_loop import author_with_agent

        result = author_with_agent(
            story=story,
            base_url=base_url,
            suite_path=suite_path,
            bug_report_dir=triage_path,
            source_root=src_root,
            engine=engine,
            max_iters=max_iters,
            max_attempts=max_attempts,
            debug=debug,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
        )
    else:
        typer.echo(f"[author] ✗ unknown --agent {agent!r}; expected deepagents or acp:<command>")
        raise typer.Exit(code=2)

    if result.suite_path and signin:
        from aitester_bdd.authoring.signin import inject_signin_block

        inject_signin_block(result.suite_path, Path(signin))
    if signin and os.environ.get("AITESTER_AUTHOR_SESSION"):
        # The fixture opened this browser for the run; close it, or every authoring run leaves a
        # Chrome behind (a thousand of them on 2026-10-24 made a sign-in time out).
        from aitester_bdd.authoring.signin import close_session

        close_session(os.environ["AITESTER_AUTHOR_SESSION"])
        typer.echo("[author] sign-in block written into the suite (values stay env: references)")
    if result.suite_path:
        typer.echo(f"[author] ✓ wrote suite: {result.suite_path} ({result.elapsed_s:.0f}s)")
    elif result.bug_report_path:
        # No suite was written, so this is not a success for a caller or CI.
        typer.echo(f"[author] ! filed bug report: {result.bug_report_path} ({result.elapsed_s:.0f}s)")
        raise typer.Exit(code=2)
    else:
        typer.echo(f"[author] ✗ agent did not reach a terminal call in {result.iterations} steps")
        typer.echo(f"  final message: {result.final_message[:300]}")
        raise typer.Exit(code=1)


@app.command(name="init-browser")
def init_browser() -> None:
    """Install browsers needed for authoring + runtime.

    Two install steps, both required for the default configuration:

      1. `python -m playwright install chromium` — Playwright Python's
         own browser binary, used by the AUTHORING explorer (the agent
         drives this Playwright browser to take CSS-grounded snapshots).

      2. `rfbrowser init` — robotframework-browser's bundled Playwright
         + browsers, used by the `playwright` runtime backend.

    Total download is large (~600MB combined). You can skip step 2 if
    you only use the `agent-browser` or `nodriver` runtime backends.
    """
    typer.echo("[1/2] Installing Playwright Python browsers (used by the authoring explorer)...")
    rc1 = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"]
    ).returncode
    if rc1 == 0:
        typer.echo("    ✓ Playwright Python chromium installed.")
    else:
        typer.echo(f"    ✗ Playwright Python install failed (exit {rc1}).")

    typer.echo("[2/2] Running `rfbrowser init` (used by the playwright runtime backend)...")
    rc2 = subprocess.run(
        [sys.executable, "-m", "Browser.entry", "init"]
    ).returncode
    if rc2 == 0:
        typer.echo("    ✓ rfbrowser init complete.")
    else:
        typer.echo(f"    ✗ rfbrowser init failed (exit {rc2}).")

    raise typer.Exit(code=(rc1 or rc2))


def _read_engine_from_suite(suite_path: str) -> str | None:
    """Parse `${ENGINE}    <name>` out of the .robot Variables section.

    Returns the engine name or None if not declared. Authored suites set
    ${ENGINE} to declare which runtime backend they want; this allows
    `aitester run` to set AITESTER_BROWSER automatically so the user
    doesn't have to remember.
    """
    import re

    try:
        text = Path(suite_path).read_text(encoding="utf-8")
    except Exception:
        return None
    in_vars = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("***"):
            in_vars = "Variables" in stripped
            continue
        if not in_vars:
            continue
        m = re.match(r"\$\{ENGINE\}\s+(\S+)", line)
        if m:
            return m.group(1).strip()
    return None


@app.command()
def run(
    suite: str = typer.Argument(..., help="Path to a .robot suite"),
    base_url: str | None = typer.Option(None, "--base-url", help="Override BASE_URL variable"),
    engine: str | None = typer.Option(
        None, "--engine", "-e",
        help="Override the suite's declared ${ENGINE}. Default: read from the suite.",
    ),
    headed: bool = typer.Option(
        False, "--headed",
        help="Run with visible browser window (headful mode). Sets AITESTER_HEADED=1.",
    ),
    step_delay: int | None = typer.Option(
        None, "--step-delay",
        help="Pause N milliseconds after each action (for visual observation). Sets AITESTER_STEP_DELAY_MS.",
    ),
) -> None:
    """Run a .robot suite via Robot Framework (no LLM in the loop).

    Reads the suite's `${ENGINE}` declaration and sets AITESTER_BROWSER
    so the walker picks the matching runtime backend. CLI --engine
    overrides the suite. Environment AITESTER_BROWSER overrides both.

    Use --headed to watch the browser execute tests. Combine with
    --step-delay 500 to slow down execution for visual observation.
    """
    declared = _read_engine_from_suite(suite)
    chosen = engine or declared
    if chosen and not os.environ.get("AITESTER_BROWSER"):
        if chosen not in ("agent-browser", "playwright", "nodriver"):
            typer.echo(f"[run] ⚠ unknown engine {chosen!r} in suite; ignoring")
        else:
            os.environ["AITESTER_BROWSER"] = chosen
            src = "--engine" if engine else "suite ${ENGINE}"
            typer.echo(f"[run] AITESTER_BROWSER={chosen} (from {src})")
    elif os.environ.get("AITESTER_BROWSER"):
        typer.echo(f"[run] AITESTER_BROWSER={os.environ['AITESTER_BROWSER']} (from env)")
    if headed:
        os.environ["AITESTER_HEADED"] = "1"
        typer.echo("[run] headed mode ON — browser window visible")
    if step_delay is not None:
        os.environ["AITESTER_STEP_DELAY_MS"] = str(step_delay)
        typer.echo(f"[run] step delay {step_delay}ms after each action")
    cmd = [sys.executable, "-m", "robot"]
    if base_url:
        cmd.extend(["--variable", f"BASE_URL:{base_url}"])
    cmd.append(suite)
    rc = subprocess.run(cmd).returncode
    raise typer.Exit(code=rc)


def _smoke_agent_browser() -> tuple[bool, list[str]]:
    """Drive `agent-browser` through the exact command shapes the runtime
    backend depends on, against a self-contained data: URL (no network).

    Returns (ok, lines). Catches the real drift modes: a `get count` that
    prints "count: 3" instead of "3", a `type`/`get text` selector-form
    mismatch, a missing `screenshot` subcommand, etc.
    """
    import tempfile
    import uuid

    session = f"aitester-doctor-{uuid.uuid4().hex[:6]}"
    html = (
        "data:text/html,"
        "<button id=b>hi</button>"
        "<input id=i><span class=n>x</span><span class=n>y</span>"
    )
    lines: list[str] = []
    ok = True

    def _ab(*args: str, timeout: int = 30) -> tuple[int, str, str]:
        r = subprocess.run(
            ["agent-browser", "--session", session, *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()

    def _check(label: str, cond: bool, got: str) -> None:
        nonlocal ok
        if cond:
            lines.append(f"    ✓ {label}")
        else:
            ok = False
            lines.append(f"    ✗ {label} — got: {got[:80]!r}")

    shot = str(Path(tempfile.gettempdir()) / f"{session}.png")
    try:
        rc, out, err = _ab("open", html, timeout=60)
        _check("open <url>", rc == 0, err or out)
        rc, out, err = _ab("snapshot", "-c", "-i", "--json")
        _check("snapshot -c -i --json", rc == 0 and bool(out), err or out)
        rc, out, err = _ab("get", "count", "#b")
        _check("get count <css> → parseable int", any(c.isdigit() for c in out), out)
        rc, out, err = _ab("get", "text", "#b")
        _check("get text <css>", rc == 0 and "hi" in out, err or out)
        rc, out, err = _ab("type", "#i", "hello")
        _check("type <css> <val>", rc == 0, err or out)
        rc, out, err = _ab("click", "#b")
        _check("click <css>", rc == 0, err or out)
        rc, out, err = _ab("press", "Escape")
        _check("press <key>", rc == 0, err or out)
        rc, out, err = _ab("screenshot", shot)
        _check("screenshot <path>", rc == 0 and Path(shot).exists(), err or out)
    except subprocess.TimeoutExpired:
        ok = False
        lines.append("    ✗ smoke test timed out (agent-browser hung)")
    except Exception as exc:  # noqa: BLE001
        ok = False
        lines.append(f"    ✗ smoke test error: {type(exc).__name__}: {exc}")
    finally:
        try:
            _ab("close", timeout=10)
        except Exception:
            pass
        try:
            Path(shot).unlink(missing_ok=True)
        except Exception:
            pass
    return ok, lines


@app.command()
def doctor(
    smoke: bool = typer.Option(
        True, "--smoke/--no-smoke",
        help="Run the agent-browser command-shape smoke test (launches a browser "
             "against a local data: URL). Use --no-smoke in headless CI.",
    ),
) -> None:
    """Check environment readiness."""
    typer.echo("aitester-bdd doctor:")

    # Python interpreter — surfaces a dead venv (the consumer's .venv-e2e
    # pointing at a since-deleted interpreter fails with a bare 'bad
    # interpreter' and nothing says so). If we're running at all our own
    # sys.executable resolves, but report it explicitly + flag a venv whose
    # base prefix vanished.
    exe = Path(sys.executable)
    venv = os.environ.get("VIRTUAL_ENV")
    py_ver = ".".join(str(x) for x in sys.version_info[:3])
    if exe.exists():
        typer.echo(f"  ✓ python {py_ver} at {exe}")
    else:
        typer.echo(f"  ✗ python interpreter path does not exist: {exe} (dead venv?)")
    if venv:
        vpy = Path(venv) / "bin" / "python"
        if vpy.exists() or exe.exists():
            typer.echo(f"  ✓ virtualenv: {venv}")
        else:
            typer.echo(
                f"  ✗ VIRTUAL_ENV={venv} but its interpreter is missing — "
                f"recreate it (`python -m venv {venv}` or `uv venv {venv}`)"
            )

    try:
        import robot
        typer.echo(f"  ✓ robotframework {robot.__version__}")
    except Exception as e:
        typer.echo(f"  ✗ robotframework: {e}")
    # Playwright explorer — used during authoring.
    try:
        import playwright  # noqa: F401
        try:
            import importlib.metadata
            v = importlib.metadata.version("playwright")
        except Exception:
            v = "?"
        # Actually try launching chromium — that's the real check.
        # The cache directory location varies (PLAYWRIGHT_BROWSERS_PATH,
        # rfbrowser's own playwright install, system Chrome, etc.), so
        # probing paths is fragile.
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                browser.close()
            typer.echo(f"  ✓ playwright explorer: {v} (chromium launchable)")
        except Exception as exc:
            typer.echo(
                f"  ⚠ playwright explorer: {v} installed but chromium not launchable "
                f"({type(exc).__name__}) — run `aitester init-browser`"
            )
    except ImportError as e:
        typer.echo(f"  ✗ playwright explorer: {e}")

    chosen = os.environ.get("AITESTER_BROWSER", "playwright").lower()
    typer.echo(f"  ℹ AITESTER_BROWSER={chosen} (default: playwright)")

    # agent-browser RUNTIME backend.
    agent_browser_present = False
    try:
        r = subprocess.run(["agent-browser", "--version"], capture_output=True, text=True, timeout=5)
        ver = r.stdout.strip() or r.stderr.strip()
        typer.echo(f"  ✓ agent-browser runtime backend: {ver} (zero install)")
        agent_browser_present = True
    except FileNotFoundError:
        tag = "⚠" if chosen == "agent-browser" else "ℹ"
        typer.echo(
            f"  {tag} agent-browser runtime backend: CLI not found "
            f"(install: `npm i -g @bayeslearner/agent-browser`)"
        )

    # Command-shape smoke test — verifies the exact subcommands the backend
    # shells out to still behave as expected (guards against CLI drift).
    if agent_browser_present and smoke:
        typer.echo("    running agent-browser command-shape smoke test...")
        sm_ok, sm_lines = _smoke_agent_browser()
        for ln in sm_lines:
            typer.echo(ln)
        if sm_ok:
            typer.echo("    ✓ agent-browser command shapes OK")
        else:
            typer.echo(
                "    ⚠ agent-browser command shapes DRIFTED — the backend may "
                "misbehave; check your agent-browser version"
            )
    elif agent_browser_present and not smoke:
        typer.echo("    ℹ agent-browser smoke test skipped (--no-smoke)")

    # Playwright backend status
    try:
        import Browser  # type: ignore[import-not-found]
        ver = getattr(Browser, '__version__', '?')
        wrapper_dir = Path(Browser.__file__).parent / "wrapper"
        node_modules = wrapper_dir / "node_modules"
        if node_modules.is_dir():
            typer.echo(f"  ✓ playwright backend: rfbrowser {ver} (initialized)")
        else:
            tag = "⚠" if chosen == "playwright" else "ℹ"
            typer.echo(
                f"  {tag} playwright backend: rfbrowser {ver} installed but NOT initialized"
                f" — run `aitester init-browser` (only needed if AITESTER_BROWSER=playwright)"
            )
    except Exception as e:
        typer.echo(f"  ✗ playwright backend (rfbrowser): {e}")

    # Nodriver backend status
    try:
        import nodriver  # type: ignore[import-not-found]  # noqa: F401

        from aitester_bdd.engine.nodriver_backend import _find_browser_binary
        binary = _find_browser_binary()
        if binary:
            typer.echo(f"  ✓ nodriver backend: installed, Chrome/Edge at {binary}")
        else:
            typer.echo("  ⚠ nodriver backend: installed but no Chrome/Edge found on system")
    except ImportError:
        tag = "⚠" if chosen == "nodriver" else "ℹ"
        typer.echo(
            f"  {tag} nodriver backend: not installed"
            f" (install with `pip install aitester-bdd[stealth]` for bot-detected sites)"
        )
    try:
        import importlib.metadata
        for pkg in ("deepagents", "langgraph", "langchain", "langchain-openai", "litellm"):
            try:
                v = importlib.metadata.version(pkg)
                typer.echo(f"  ✓ {pkg} {v}")
            except importlib.metadata.PackageNotFoundError:
                typer.echo(f"  ✗ {pkg} not installed")
    except Exception as e:
        typer.echo(f"  ✗ {e}")
    model = os.environ.get("AITESTER_LLM_MODEL")
    base = os.environ.get("AITESTER_LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    if model:
        typer.echo(f"  ✓ AITESTER_LLM_MODEL={model}")
    else:
        typer.echo("  ✗ AITESTER_LLM_MODEL not set — authoring and fluid steps will refuse to start")
    if base:
        typer.echo(f"  ✓ LLM base URL={base}")
    else:
        typer.echo("  ~ AITESTER_LLM_BASE_URL not set (the provider's own endpoint is used)")


if __name__ == "__main__":
    app()
