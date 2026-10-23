"""LLM configuration: resolution, validation, and model-name normalization.

aitester-bdd is provider-agnostic — it depends on **litellm** (multi-provider)
and **langchain-openai** (which speaks the OpenAI *protocol*, not the OpenAI
service). It has NO dependency on any specific vendor (no `anthropic`, no
`openai`). So its own config surface uses NEUTRAL, aitester-owned names rather
than borrowing OpenAI's:

  * ``AITESTER_LLM_MODEL``     — model spec (bare, e.g. ``claude-sonnet-5-5``)
  * ``AITESTER_LLM_BASE_URL``  — endpoint URL
  * ``AITESTER_LLM_API_KEY``   — credential

Resolution precedence for each value (`resolve_llm_config`):

  1. an explicit argument passed by the caller (programmatic use),
  2. the neutral ``AITESTER_LLM_*`` env var,
  3. the legacy ``OPENAI_BASE_URL`` / ``OPENAI_API_KEY`` env var (deprecated,
     still honored for back-compat),
  4. otherwise ``None``: **litellm** / the LangChain integration resolve
     creds from their own provider-native env (``OPENAI_API_KEY``,
     ``ANTHROPIC_API_KEY``, ``GEMINI_API_KEY``, …).

There is no shipped default model or endpoint (spec 04, review finding 5): a
fluid run with no model configured fails loud instead of calling a private
address or api.openai.com with a made-up model name.

Two consumers want the MODEL in different formats — a footgun the walker used
to hit deep inside an HTTP client:

  * the fluid explore/author agent uses ``langchain_openai.ChatOpenAI`` — wants
    the model WITHOUT a litellm provider prefix → ``claude-sonnet-5-5``
  * the in-walker judge uses ``litellm.completion`` — wants a provider-prefixed
    spec → ``openai/claude-sonnet-5-5``

`strip_openai_prefix` / `ensure_openai_prefix` normalize between them so ONE
``AITESTER_LLM_MODEL`` feeds both paths.

`validate_llm_env` turns a blank/malformed cred into a loud, actionable error
at suite start, naming the exact variable and an example. It complains ONLY
when a var is SET but unusable; UNSET vars fall through to the precedence above.
"""
from __future__ import annotations

import os
import re

# Shown in error messages only; never used as a value.
EXAMPLE_MODEL = "claude-sonnet-5-5"
EXAMPLE_BASE_URL = "https://llm-gateway.example.com/v1"

# Neutral (aitester-owned) env var names, and the legacy OpenAI-named ones we
# still read for back-compat.
ENV_MODEL = "AITESTER_LLM_MODEL"
ENV_BASE_URL = "AITESTER_LLM_BASE_URL"
ENV_API_KEY = "AITESTER_LLM_API_KEY"
LEGACY_BASE_URL = "OPENAI_BASE_URL"
LEGACY_API_KEY = "OPENAI_API_KEY"


def _env(name: str) -> str | None:
    """os.environ.get with blank-as-unset semantics."""
    v = os.environ.get(name)
    return v if (v and v.strip()) else None


def resolve_llm_config(
    *, model: str | None = None, base_url: str | None = None, api_key: str | None = None,
) -> tuple[str, str | None, str | None]:
    """Resolve (model, base_url, api_key) by the precedence documented above.

    `base_url`/`api_key` may come back ``None`` — that is intentional: it lets
    litellm / the LangChain integration use their provider-native env.
    Raises LLMConfigError when no model is configured anywhere.
    """
    model = model or _env(ENV_MODEL)
    if not model:
        raise LLMConfigError(
            f"aitester-bdd: no LLM configured. Set {ENV_MODEL} (e.g. "
            f"{ENV_MODEL}={EXAMPLE_MODEL}) and, for an OpenAI-compatible gateway, "
            f"{ENV_BASE_URL} and {ENV_API_KEY}; or pass --llm-model."
        )
    base_url = base_url or _env(ENV_BASE_URL) or _env(LEGACY_BASE_URL)
    api_key = api_key or _env(ENV_API_KEY) or _env(LEGACY_API_KEY)
    return model, base_url, api_key


# litellm provider prefix → langchain `init_chat_model` model_provider. The
# fluid agent uses `init_chat_model` (multi-provider), so a litellm-style
# ``provider/model`` spec must map onto langchain's provider name.
_LITELLM_TO_LANGCHAIN_PROVIDER = {
    "openai": "openai",
    "anthropic": "anthropic",
    "azure": "azure_openai",
    "azure_ai": "azure_openai",
    "bedrock": "bedrock_converse",
    "vertex_ai": "google_vertexai",
    "gemini": "google_genai",
    "ollama": "ollama",
    "openrouter": "openai",  # OpenAI-compatible — pair with base_url
    "groq": "groq",
    "mistral": "mistralai",
    "cohere": "cohere",
    "together_ai": "together",
    "fireworks_ai": "fireworks",
    "deepseek": "deepseek",
    "xai": "xai",
    "huggingface": "huggingface",
}


def split_provider(model: str) -> tuple[str, str]:
    """Split a litellm-style ``provider/model`` spec into
    ``(langchain_provider, bare_model)`` for `init_chat_model`.

    A spec with no recognized provider prefix (e.g. ``cc/…`` or a gateway's
    bare model name) is assumed to be an OpenAI-compatible endpoint → provider
    ``openai``, model unchanged.
    """
    head = model.split("/", 1)[0]
    if head in _LITELLM_TO_LANGCHAIN_PROVIDER and "/" in model:
        return _LITELLM_TO_LANGCHAIN_PROVIDER[head], model.split("/", 1)[1]
    return "openai", model


def resolve_chat_model(
    *, model: str | None = None, base_url: str | None = None, api_key: str | None = None,
) -> tuple[str, str, str | None, str | None]:
    """Resolve everything `init_chat_model` needs for the fluid agent:
    ``(provider, model, base_url, api_key)``.

    Composes `resolve_llm_config` (precedence) with
    `split_provider` (litellm prefix → langchain provider). When nothing sets
    them, base_url/api_key come back ``None`` so the provider's own
    LangChain integration resolves creds from its native env.
    """
    model, base_url, api_key = resolve_llm_config(
        model=model, base_url=base_url, api_key=api_key,
    )
    provider, bare_model = split_provider(model)
    return provider, bare_model, base_url, api_key

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
    none is present (an OpenAI-compatible gateway)."""
    if any(model.startswith(p) for p in _LITELLM_PROVIDERS):
        return model
    return "openai/" + model


def validate_llm_env() -> None:
    """Raise LLMConfigError if any LLM env var is SET but blank/malformed.

    Checks the neutral ``AITESTER_LLM_*`` names and the legacy ``OPENAI_*``
    ones. Unset vars are OK — resolution precedence applies. Meant to be called
    once at the start of a fluid run, where the LLM is mandatory.
    """
    problems: list[str] = []

    def _blank_if_set(name: str, example: str) -> None:
        raw = os.environ.get(name)
        if raw is not None and not raw.strip():
            problems.append(
                f"{name} is set but BLANK — unset it, or set e.g. {name}={example}"
            )

    def _url_if_set(name: str) -> None:
        raw = os.environ.get(name)
        if raw is None:
            return
        v = raw.strip()
        if not v:
            problems.append(
                f"{name} is set but BLANK — unset it, or set e.g. {name}={EXAMPLE_BASE_URL}"
            )
        elif not re.match(r"^https?://[^/]+", v):
            problems.append(
                f"{name}={raw!r} is malformed — it needs a scheme and host "
                f"(e.g. {EXAMPLE_BASE_URL}). A bare path like '/v1' fails deep "
                "in the HTTP client with no useful message."
            )

    _blank_if_set(ENV_MODEL, EXAMPLE_MODEL)
    _url_if_set(ENV_BASE_URL)
    _url_if_set(LEGACY_BASE_URL)
    _blank_if_set(ENV_API_KEY, "sk-...")
    _blank_if_set(LEGACY_API_KEY, "sk-...")

    if problems:
        raise LLMConfigError(
            "aitester-bdd: LLM configuration is invalid — the fluid agent "
            "cannot start:\n  - " + "\n  - ".join(problems)
        )
