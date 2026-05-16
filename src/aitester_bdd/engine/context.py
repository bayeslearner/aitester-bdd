"""WalkContext — runtime configuration bag for the walker.

Replaces scattered os.environ.get() calls with a single dataclass that
is built once at walk_verification() entry and threaded to subsystems:

  - BrowserAdapter.new_session() reads `headed`
  - _build_default_registry() reads `step_delay_ms` and `disabled_aspects`
  - _execute_body() no longer reads env vars directly
  - walk_verification() reads `run_timeout_s`

All values are resolved from env vars + CLI flags at construction time.
Downstream code operates on the resolved values — no env lookups past
construction.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WalkContext:
    """Immutable runtime config for a single walk_verification() call."""

    headed: bool = False
    step_delay_ms: int = 0
    run_timeout_s: int = 300
    disabled_aspects: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_env(cls) -> WalkContext:
        """Build from environment variables (the default entry path)."""
        headed = os.environ.get("AITESTER_HEADED", "").strip() in ("1", "true", "yes")
        step_delay_ms = int(os.environ.get("AITESTER_STEP_DELAY_MS", "0"))
        run_timeout_s = int(os.environ.get("AITESTER_RUN_TIMEOUT", "300"))
        disabled = frozenset(
            a.strip()
            for a in os.environ.get("AITESTER_DISABLE_ASPECTS", "").split(",")
            if a.strip()
        )
        return cls(
            headed=headed,
            step_delay_ms=step_delay_ms,
            run_timeout_s=run_timeout_s,
            disabled_aspects=disabled,
        )
