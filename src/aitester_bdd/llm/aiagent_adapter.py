"""LiteLLM-backed LLM adapter for aitester-bdd's in-walker one-shot calls.

This is the NON-agentic escape hatch the walker uses when deterministic checks
can't express an assertion (no tools, no loop — prompt in, text out):

    - `judge(criterion, observation) -> bool`      — semantic StateCheck (text)
    - `judge_visual(criterion, png_bytes) -> bool` — visual_semantic (screenshot)
    - `diagnose(context) -> str`                   — failure-diagnosis aspect
    - `ask(prompt, page_context) -> str`           — the `I ask LLM` action

The AGENTIC explore/author loop does NOT go through here — it uses
`authoring.agent_loop` (deepagents + langgraph + `init_chat_model`).

Why LiteLLM for the one-shots: one call shape (`litellm.completion`) dispatches
to OpenAI, Anthropic, Azure, Bedrock, OpenAI-compat proxies, etc. Multimodal
(image) messages use the standard OpenAI shape and LiteLLM translates to each
provider's native form.

Config resolves through `llm.config.resolve_llm_config` — neutral,
aitester-owned names (this product depends on LiteLLM, not on any vendor):
  AITESTER_LLM_MODEL     — model spec (bare, e.g. "cc/claude-opus-4-7")
  AITESTER_LLM_BASE_URL  — endpoint URL (proxy default for cc/… models)
  AITESTER_LLM_API_KEY   — credential (proxy default for cc/… models)
Legacy OPENAI_BASE_URL / OPENAI_API_KEY are still honored (deprecated).
Any other model defers creds to LiteLLM's provider-native env.
"""
from __future__ import annotations

import base64
import logging

log = logging.getLogger("aitester_bdd.llm.aiagent")


SYSTEM_PROMPT_JUDGE = """You are aitester-bdd's in-walker judge — an escape
hatch for assertions that genuinely need AI-level judgment (semantic meaning
of text, visual recognition). The test author opts in by writing a `semantic`
or `visual_semantic` StateCheck.

You receive a CRITERION (what the test expects to be true) and an OBSERVATION
(page text, or a screenshot). Decide PASS or FAIL based ONLY on the
observation. Be strict — if the observation does not clearly satisfy the
criterion, FAIL it. Do not speculate about state you cannot see.

Reply with EXACTLY one word: PASS or FAIL.
"""

SYSTEM_PROMPT_DIAGNOSE = """You are aitester-bdd's failure-diagnosis aspect.

A rule in a test suite just failed. You receive:
  - the verification + scenario + rule name (what the test intends)
  - the failed step (selector, kind, position)
  - what the test expected
  - what was actually observed
  - a snapshot of the page at the moment of failure (URL + visible text)

Write a SHORT (1-3 sentence) diagnosis that:
  1. Names the most likely cause grounded in the snapshot (e.g.,
     "the page returned a 500 error", "the auth banner is still
     visible suggesting login did not complete", "the locator picks
     up the loading skeleton rather than the loaded element").
  2. If the cause is in the SYSTEM under test, say so. If the cause
     is in the TEST itself (wrong selector, race, stale expectation),
     say that.

Do NOT speculate beyond the snapshot. Do NOT propose code fixes. Just
state the cause and where it lives (SUT vs test).
"""


class AIAgentLLM:
    """LiteLLM-backed LLM adapter. Same instance is reused for authoring
    and in-walker judge calls — one credential set, one config.

    Config is resolved via `llm.config.resolve_llm_config` (explicit args →
    neutral ``AITESTER_LLM_*`` env → legacy ``OPENAI_*`` env → proxy defaults
    for ``cc/…`` models, else provider-native litellm env). Creds are passed
    directly to ``litellm.completion`` as ``api_base``/``api_key`` — no global
    env mutation — so non-proxy providers resolve their own creds normally."""

    def __init__(
        self, *, model: str | None = None, base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        from aitester_bdd.llm.config import ensure_openai_prefix, resolve_llm_config

        m, b, k = resolve_llm_config(model=model, base_url=base_url, api_key=api_key)
        # litellm wants a provider-prefixed spec; normalize (the same
        # AITESTER_LLM_MODEL also feeds the bare-name langchain path).
        self.model = ensure_openai_prefix(m)
        self.base_url = b
        self.api_key = k

    def _completion(self, messages: list[dict], *, max_tokens: int = 2048) -> str:
        """Single litellm completion call. Returns the assistant text.

        opus-4.7 rejects `temperature` as deprecated. Setting it to None
        (not omitting it!) is what litellm respects — its default would
        otherwise inject a value. `drop_params=True` is belt-and-suspenders
        for other unsupported params per provider. `api_base`/`api_key` are
        passed only when resolved; otherwise litellm uses provider-native env."""
        import litellm

        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=None,
            drop_params=True,
        )
        if self.base_url:
            kwargs["api_base"] = self.base_url
        if self.api_key:
            kwargs["api_key"] = self.api_key
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content or ""

    def _chat(self, system: str, user: str, *, max_tokens: int = 4096) -> str:
        return self._completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # In-walker escape hatch — keep it small + cheap
    # ------------------------------------------------------------------

    def ask(self, *, prompt: str, page_context: str) -> str:
        """General-purpose LLM ask with page context. Returns raw response.

        Used by the `I ask LLM` keyword for validate/extract/transform."""
        system = (
            "You are aitester-bdd's in-walker assistant. You receive a question "
            "and the current page state. Answer concisely and precisely based on "
            "what you can see in the page context. For yes/no questions, start "
            "your answer with 'yes' or 'no'. For extraction questions, return "
            "only the extracted value. For generation questions, return only the "
            "generated content. No commentary, no markdown fences."
        )
        user = (
            f"# Page context\n```\n{page_context[:8000]}\n```\n\n"
            f"# Question\n{prompt}"
        )
        return self._chat(system, user, max_tokens=1024).strip()

    def judge(self, *, criterion: str, observation: str) -> bool:
        """Text-based semantic judge. Returns True if the observation
        satisfies the criterion. Used by the `semantic` StateCheck."""
        user = (
            f"# Criterion\n{criterion}\n\n"
            f"# Observation\n```\n{observation[:6000]}\n```\n\n"
            f"Reply PASS or FAIL."
        )
        out = self._chat(SYSTEM_PROMPT_JUDGE, user, max_tokens=8).strip().upper()
        return out.startswith("PASS")

    def diagnose(self, *, context: str) -> str:
        """AOP aspect: explain why a rule failed.

        `context` is a structured plain-text block carrying the verification
        name, scenario, rule, failed step, expected/observed, and a page
        snapshot. Returns 1-3 sentences naming the likely cause and where
        it lives (SUT vs test). Empty string on any error so the walker
        can still report the deterministic failure cleanly."""
        try:
            out = self._chat(SYSTEM_PROMPT_DIAGNOSE, context, max_tokens=300)
            return out.strip()
        except Exception as exc:
            log.warning("diagnose call failed: %s", exc)
            return ""

    def judge_visual(self, *, criterion: str, png_bytes: bytes) -> bool:
        """Multimodal judge over a screenshot. Returns True if the screenshot
        satisfies the criterion. Used by `visual_semantic` StateCheck.

        Uses the standard OpenAI multimodal message shape; LiteLLM
        translates for non-OpenAI providers automatically.
        """
        data_url = f"data:image/png;base64,{base64.b64encode(png_bytes).decode()}"
        out = self._completion(
            [
                {"role": "system", "content": SYSTEM_PROMPT_JUDGE},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"# Criterion\n{criterion}\n\nReply PASS or FAIL."},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            max_tokens=8,
        ).strip().upper()
        return out.startswith("PASS")
