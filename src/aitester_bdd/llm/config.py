"""LLM configuration: validation + model-name normalization.

Two consumers read the SAME three env vars but want the model in DIFFERENT
formats, which is a footgun the walker used to hit deep inside an HTTP client
with no hint:

  * the fluid explore/author agent uses ``langchain_openai.ChatOpenAI`` — it
    talks to the OpenAI-compatible endpoint directly, so it wants the model
    WITHOUT a litellm provider prefix  → ``cc/claude-opus-4-7``
  * the in-walker judge / finalize path uses ``litellm.completion`` — it wants
    a provider-prefixed spec                → ``openai/cc/claude-opus-4-7``

Same value, two formats. `strip_openai_prefix` / `ensure_openai_prefix`
normalize between them so a user only ever sets ONE ``AITESTER_LLM_MODEL`` and
both paths work.

`validate_llm_env` turns a blank/malformed cred into a loud, actionable error
at suite start — naming the exact variable and an example value — instead of a
cryptic failure mid-run. It complains ONLY when a var is SET but unusable; an
UNSET var is fine (the defaults below apply).
"""
from __future__ import annotations

import os
import re

# Kept in sync with the two adapters' defaults (aiagent_adapter / agent_loop).
DEFAULT_MODEL_BARE = "cc/claude-opus-4-7"
DEFAULT_MODEL_LITELLM = "openai/cc/claude-opus-4-7"
DEFAULT_BASE_URL = "http://localhost:20128/v1"
DEFAULT_API_KEY = "placeholder"

# Recognized litellm provider prefixes — if the model already starts with one
# of these it is left untouched (the user chose their provider explicitly).
_LITELLM_PROVIDERS = (
    "openai/", "anthropic/", "azure/", "azure_ai/", "bedrock/", "vertex_ai/",
    "gemini/", "ollama/", "openrouter/", "groq/", "mistral/", "cohere/",
    "together_ai/", "fireworks_ai/", "deepseek/", "xai/", "huggingface/",
)


class LLMConfigError(RuntimeError):
    """Raised when AITESTER_LLM_MODEL / OPENAI_BASE_URL / OPENAI_API_KEY are
    set to blank or malformed values."""


def strip_openai_prefix(model: str) -> str:
    """Drop a leading ``openai/`` so ChatOpenAI gets a bare model name."""
    return model[len("openai/"):] if model.startswith("openai/") else model


def ensure_openai_prefix(model: str) -> str:
    """Ensure a litellm provider prefix; assume the OpenAI-compat proxy when
    none is present (this project's default deployment)."""
    if any(model.startswith(p) for p in _LITELLM_PROVIDERS):
        return model
    return "openai/" + model


def validate_llm_env() -> None:
    """Raise LLMConfigError if any LLM env var is SET but blank/malformed.

    Unset vars are OK — the defaults (claude-code-proxy) apply. This is meant
    to be called once at the start of a fluid run, where the LLM is mandatory.
    """
    problems: list[str] = []

    model = os.environ.get("AITESTER_LLM_MODEL")
    if model is not None and not model.strip():
        problems.append(
            "AITESTER_LLM_MODEL is set but BLANK — unset it to use the default "
            f"({DEFAULT_MODEL_BARE!r}), or set e.g. "
            f"AITESTER_LLM_MODEL={DEFAULT_MODEL_BARE}"
        )

    base = os.environ.get("OPENAI_BASE_URL")
    if base is not None:
        b = base.strip()
        if not b:
            problems.append(
                "OPENAI_BASE_URL is set but BLANK — unset it to use the default "
                f"({DEFAULT_BASE_URL!r}), or set e.g. "
                f"OPENAI_BASE_URL={DEFAULT_BASE_URL}"
            )
        elif not re.match(r"^https?://[^/]+", b):
            problems.append(
                f"OPENAI_BASE_URL={base!r} is malformed — it needs a scheme and "
                f"host (e.g. {DEFAULT_BASE_URL}). A bare path like '/v1' fails "
                "deep in the HTTP client with no useful message."
            )

    key = os.environ.get("OPENAI_API_KEY")
    if key is not None and not key.strip():
        problems.append(
            "OPENAI_API_KEY is set but BLANK — unset it (the default "
            f"placeholder {DEFAULT_API_KEY!r} works against claude-code-proxy) "
            "or set a real key, e.g. OPENAI_API_KEY=sk-..."
        )

    if problems:
        raise LLMConfigError(
            "aitester-bdd: LLM configuration is invalid — the fluid agent "
            "cannot start:\n  - " + "\n  - ".join(problems)
        )
