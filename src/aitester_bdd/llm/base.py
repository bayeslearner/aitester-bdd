"""LLMClient Protocol — the in-walker one-shot interface aitester-bdd needs.

The default adapter (`AIAgentLLM`, LiteLLM-backed) implements these NON-agentic
calls the walker makes when a deterministic check can't express an assertion.
The agentic explore/author loop is a separate concern — it uses
`authoring.agent_loop` (deepagents + langgraph + `init_chat_model`), not this
Protocol.
"""
from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """Minimal in-walker interface aitester-bdd needs from an LLM provider."""

    # ------------------------------------------------------------------
    # In-walker escape hatch
    # ------------------------------------------------------------------

    def judge(self, *, criterion: str, observation: str) -> bool:
        """True if the observation (page text) satisfies the criterion.
        Used sparingly — deterministic checks preferred."""
        ...

    def judge_visual(self, *, criterion: str, png_bytes: bytes) -> bool:
        """True if the screenshot satisfies the criterion. Used by the
        walker's `visual_semantic` StateCheck."""
        ...

    def diagnose(self, *, context: str) -> str:
        """AOP failure aspect: hand the failure context to the LLM, get
        a short natural-language explanation. The walker calls this on
        every rule failure. Empty return = no diagnosis available."""
        ...
