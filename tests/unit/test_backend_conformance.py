"""Backend conformance — every backend must implement the full contract.

The three runtime backends share no base class; the `BrowserBackend` Protocol
is the contract. This test derives the required surface FROM the Protocol and
asserts each concrete backend implements every member — so a new surface method
(the next `preflight`) cannot be added to one backend and silently forgotten on
another.
"""
from __future__ import annotations

import pytest


def _protocol_surface() -> set[str]:
    from aitester_bdd.engine.browser import BrowserBackend

    # Prefer the real Protocol member set when available (3.12+), else derive
    # from the class namespace (public, non-dunder names).
    attrs = getattr(BrowserBackend, "__protocol_attrs__", None)
    if attrs:
        return set(attrs)
    return {n for n in vars(BrowserBackend) if not n.startswith("_")}


def _backend_classes():
    from aitester_bdd.engine.agent_browser_backend import AgentBrowserBackend
    from aitester_bdd.engine.browser import _PlaywrightBackend

    classes = [_PlaywrightBackend, AgentBrowserBackend]
    try:
        from aitester_bdd.engine.nodriver_backend import NodriverBackend
        classes.append(NodriverBackend)
    except Exception:  # nodriver extra not installed — skip it, not a failure
        pass
    return classes


@pytest.mark.parametrize("backend_cls", _backend_classes(), ids=lambda c: c.__name__)
def test_backend_implements_full_surface(backend_cls):
    surface = _protocol_surface()
    assert surface, "BrowserBackend Protocol exposed no members"
    missing = {m for m in surface if not callable(getattr(backend_cls, m, None))}
    assert not missing, f"{backend_cls.__name__} is missing backend surface: {sorted(missing)}"


def test_preflight_is_part_of_the_contract():
    """Guards the specific method v0.4.0 added by hand to all three."""
    assert "preflight" in _protocol_surface()
