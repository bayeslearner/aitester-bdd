"""Plan-then-Execute rule DAG engine for BDD test execution.

The walker and browser adapter are ports from the WISE RPA BDD engine,
adapted from web extraction to web verification. The vendored WISE
source was used as the reference during the port and has been removed
once the relevant logic landed here. See engine/README.md for the
ported method map and what was deliberately dropped.
"""
from aitester_bdd.engine.context import WalkContext

__all__ = ["WalkContext"]
