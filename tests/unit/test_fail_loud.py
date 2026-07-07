"""Fail-loud guarantees — the harness must never lie about its own verdict.

Two properties this suite locks in:

  1. INV-4: a NullBrowser / stub run is a FAILURE, never a silent PASS.
     `walk_verification` refuses to start when a backend's `preflight()`
     reports it cannot actually drive.

  2. Blank / malformed LLM creds fail loud at config time, naming the exact
     variable — not deep inside an HTTP client mid-run.
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# 1. NullBrowser fail-loud (INV-4)
# ---------------------------------------------------------------------------


class _StubBrowser:
    """A backend that admits (via preflight) it cannot drive."""

    def __init__(self, reason="stub not initialized"):
        self._reason = reason

    def preflight(self):
        return (False, self._reason)

    # Should never be reached — preflight fails first.
    def new_session(self, **kw):  # pragma: no cover
        raise AssertionError("new_session must not be called after failed preflight")


def _build_min_verification():
    from aitester_bdd.AITester import AITester

    t = AITester()
    t.start_verification('"v"')
    t.start_scenario_at('"flow"', '"http://x"')
    t.define_rule('"r"')
    t.when_click_locator('"button"')
    return t.get_verification()


def test_walker_refuses_stub_browser(monkeypatch):
    from aitester_bdd.engine import walk
    from aitester_bdd.engine.walk import NullBrowserError, walk_verification

    monkeypatch.delenv("AITESTER_ALLOW_STUB_BROWSER", raising=False)
    monkeypatch.setattr(walk, "BrowserAdapter", lambda: _StubBrowser("RF-Browser not initialized"))

    with pytest.raises(NullBrowserError) as exc:
        walk_verification(_build_min_verification())
    assert "silent PASS" in str(exc.value)
    assert "RF-Browser not initialized" in str(exc.value)


def test_allow_stub_env_bypasses_preflight(monkeypatch):
    """The bypass exists for tests that deliberately drive a stub."""
    from aitester_bdd.engine import walk

    monkeypatch.setenv("AITESTER_ALLOW_STUB_BROWSER", "1")
    # A stub that also survives being driven (all no-ops) — bypass means we
    # get past preflight; the run itself is allowed to proceed.
    walk._assert_real_browser(_StubBrowser("would fail without bypass"))  # no raise


def test_fakebrowser_without_preflight_is_trusted(monkeypatch):
    """A backend with no preflight() (unit-test FakeBrowser) is not blocked."""
    from aitester_bdd.engine import walk

    class NoPreflight:
        pass

    monkeypatch.delenv("AITESTER_ALLOW_STUB_BROWSER", raising=False)
    walk._assert_real_browser(NoPreflight())  # no raise


def test_playwright_backend_preflight_detects_nullbrowser(monkeypatch):
    from aitester_bdd.engine.browser import _NullBrowser, _PlaywrightBackend

    be = _PlaywrightBackend()
    monkeypatch.setattr(be, "_rf_browser", lambda: _NullBrowser())
    ok, reason = be.preflight()
    assert ok is False
    assert "init-browser" in reason


def test_agent_browser_backend_preflight_missing_cli(monkeypatch):
    from aitester_bdd.engine.agent_browser_backend import AgentBrowserBackend

    monkeypatch.setattr("shutil.which", lambda _n: None)
    ok, reason = AgentBrowserBackend().preflight()
    assert ok is False
    assert "not found on PATH" in reason


# ---------------------------------------------------------------------------
# 2. LLM cred validation + model-prefix normalization
# ---------------------------------------------------------------------------


def _clear_llm_env(monkeypatch):
    for v in (
        "AITESTER_LLM_MODEL", "AITESTER_LLM_BASE_URL", "AITESTER_LLM_API_KEY",
        "OPENAI_BASE_URL", "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(v, raising=False)


def test_validate_llm_env_ok_when_unset(monkeypatch):
    from aitester_bdd.llm.config import validate_llm_env

    _clear_llm_env(monkeypatch)
    validate_llm_env()  # unset → defaults apply → no raise


def test_validate_llm_env_blank_base_url(monkeypatch):
    from aitester_bdd.llm.config import LLMConfigError, validate_llm_env

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    with pytest.raises(LLMConfigError) as exc:
        validate_llm_env()
    assert "OPENAI_BASE_URL" in str(exc.value)


def test_validate_llm_env_malformed_base_url(monkeypatch):
    from aitester_bdd.llm.config import LLMConfigError, validate_llm_env

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_BASE_URL", "/v1")  # bare path, no scheme+host
    with pytest.raises(LLMConfigError) as exc:
        validate_llm_env()
    msg = str(exc.value)
    assert "OPENAI_BASE_URL" in msg and "malformed" in msg


def test_validate_llm_env_blank_api_key_and_model(monkeypatch):
    from aitester_bdd.llm.config import LLMConfigError, validate_llm_env

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    monkeypatch.setenv("AITESTER_LLM_MODEL", "")
    with pytest.raises(LLMConfigError) as exc:
        validate_llm_env()
    msg = str(exc.value)
    assert "OPENAI_API_KEY" in msg
    assert "AITESTER_LLM_MODEL" in msg


def test_model_prefix_normalization():
    from aitester_bdd.llm.config import ensure_openai_prefix, strip_openai_prefix

    # bare → langchain form stays bare; litellm form gets prefixed
    assert strip_openai_prefix("cc/claude-opus-4-7") == "cc/claude-opus-4-7"
    assert strip_openai_prefix("openai/cc/claude-opus-4-7") == "cc/claude-opus-4-7"
    assert ensure_openai_prefix("cc/claude-opus-4-7") == "openai/cc/claude-opus-4-7"
    assert ensure_openai_prefix("openai/cc/claude-opus-4-7") == "openai/cc/claude-opus-4-7"
    # a recognized non-openai provider is left untouched
    assert ensure_openai_prefix("anthropic/claude-opus-4-7") == "anthropic/claude-opus-4-7"


def test_resolve_defaults_to_proxy_for_cc_model(monkeypatch):
    from aitester_bdd.llm.config import DEFAULT_BASE_URL, resolve_llm_config

    _clear_llm_env(monkeypatch)
    model, base, key = resolve_llm_config()
    assert model.startswith("cc/")
    assert base == DEFAULT_BASE_URL and key  # proxy defaults applied


def test_resolve_defers_creds_for_non_proxy_model(monkeypatch):
    """A non-cc/ model leaves base/key None so litellm uses its own env."""
    from aitester_bdd.llm.config import resolve_llm_config

    _clear_llm_env(monkeypatch)
    model, base, key = resolve_llm_config(model="anthropic/claude-opus-4-8")
    assert model == "anthropic/claude-opus-4-8"
    assert base is None and key is None


def test_resolve_precedence_explicit_over_neutral_over_legacy(monkeypatch):
    from aitester_bdd.llm.config import resolve_llm_config

    _clear_llm_env(monkeypatch)
    # legacy only
    monkeypatch.setenv("OPENAI_BASE_URL", "http://legacy/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "legacy-key")
    _, base, key = resolve_llm_config()
    assert base == "http://legacy/v1" and key == "legacy-key"
    # neutral overrides legacy
    monkeypatch.setenv("AITESTER_LLM_BASE_URL", "http://neutral/v1")
    monkeypatch.setenv("AITESTER_LLM_API_KEY", "neutral-key")
    _, base, key = resolve_llm_config()
    assert base == "http://neutral/v1" and key == "neutral-key"
    # explicit arg overrides everything
    _, base, key = resolve_llm_config(base_url="http://explicit/v1", api_key="explicit-key")
    assert base == "http://explicit/v1" and key == "explicit-key"


def test_validate_llm_env_neutral_names(monkeypatch):
    from aitester_bdd.llm.config import LLMConfigError, validate_llm_env

    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("AITESTER_LLM_BASE_URL", "/v1")  # malformed
    with pytest.raises(LLMConfigError) as exc:
        validate_llm_env()
    assert "AITESTER_LLM_BASE_URL" in str(exc.value)


def test_split_provider_maps_litellm_prefix_to_langchain():
    from aitester_bdd.llm.config import split_provider

    # no prefix / cc proxy → openai-compatible endpoint
    assert split_provider("cc/claude-opus-4-7") == ("openai", "cc/claude-opus-4-7")
    # explicit litellm prefixes map to langchain provider names + strip prefix
    assert split_provider("openai/cc/claude-opus-4-7") == ("openai", "cc/claude-opus-4-7")
    assert split_provider("anthropic/claude-opus-4-8") == ("anthropic", "claude-opus-4-8")
    assert split_provider("gemini/gemini-2.0-flash") == ("google_genai", "gemini-2.0-flash")
    assert split_provider("groq/llama-3.1-70b") == ("groq", "llama-3.1-70b")


def test_resolve_chat_model_default_and_native(monkeypatch):
    from aitester_bdd.llm.config import DEFAULT_BASE_URL, resolve_chat_model

    _clear_llm_env(monkeypatch)
    provider, model, base, key = resolve_chat_model()
    assert provider == "openai" and model.startswith("cc/")
    assert base == DEFAULT_BASE_URL and key  # proxy creds applied

    # native provider → creds deferred to its own LangChain env
    provider, model, base, key = resolve_chat_model(model="anthropic/claude-opus-4-8")
    assert provider == "anthropic" and model == "claude-opus-4-8"
    assert base is None and key is None
