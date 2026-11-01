"""
src/models/pydantic_ai.py — Convert ModelConfig into PydanticAI model instances.

Supports four backends:
  - openai     → Azure OpenAI (or any OpenAI-API endpoint with a deployment URL)
  - anthropic  → Anthropic Claude
  - vllm       → Self-hosted vLLM HTTP server (OpenAI-compatible, e.g. Nemotron/Llama)
  - local      → Rejected: PydanticAI is async; serve HF models via vLLM and use type="vllm"
"""
import functools
import os
from src.config import ModelConfig, get_settings


def _client_timeout(extra: dict | None) -> float:
    """Per-model EXTRA_ARGS={"timeout": ...} overrides the global default
    (settings.llm_request_timeout_seconds) -- see that field's docstring for
    why every client needs one set explicitly."""
    if extra and "timeout" in extra:
        return extra["timeout"]
    return get_settings().llm_request_timeout_seconds


def _parse_azure_url(url: str) -> tuple[str, str]:
    """Split 'https://host/path?api-version=X' into (endpoint, api_version)."""
    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(url)
    api_version = parse_qs(parsed.query).get("api-version", ["2025-01-01-preview"])[0]
    endpoint = f"{parsed.scheme}://{parsed.netloc}"
    return endpoint, api_version


def _openai_settings_from_extra_args(extra: dict | None):
    """Map a model's `extra_args` into OpenAIChatModelSettings so they reach the
    PydanticAI agent's requests (e.g. reasoning_effort, verbosity). Known OpenAI
    sampling fields map directly; `reasoning_effort` maps to the dedicated field;
    anything else (e.g. `verbosity`) is forwarded via `extra_body`. Returns None
    when there's nothing to set."""
    if not extra:
        return None
    from pydantic_ai.models.openai import OpenAIChatModelSettings
    direct = {"max_tokens", "temperature", "top_p", "timeout", "seed",
              "presence_penalty", "frequency_penalty", "stop_sequences"}
    kwargs: dict = {}
    extra_body: dict = {}
    for k, v in extra.items():
        if k == "reasoning_effort":
            kwargs["openai_reasoning_effort"] = v
        elif k in direct:
            kwargs[k] = v
        else:
            extra_body[k] = v
    if extra_body:
        kwargs["extra_body"] = extra_body
    return OpenAIChatModelSettings(**kwargs)


def _responses_settings_from_extra_args(extra: dict | None):
    """Same mapping as above but for the Responses API. `verbosity` has a
    dedicated field here (openai_text_verbosity)."""
    if not extra:
        return None
    from pydantic_ai.models.openai import OpenAIResponsesModelSettings
    direct = {"max_tokens", "temperature", "top_p", "timeout", "seed",
              "presence_penalty", "frequency_penalty", "stop_sequences"}
    kwargs: dict = {}
    extra_body: dict = {}
    for k, v in extra.items():
        if k == "reasoning_effort":
            kwargs["openai_reasoning_effort"] = v
        elif k == "verbosity":
            kwargs["openai_text_verbosity"] = v
        elif k in direct:
            kwargs[k] = v
        else:
            extra_body[k] = v
    if extra_body:
        kwargs["extra_body"] = extra_body
    return OpenAIResponsesModelSettings(**kwargs)


def _build_openai_model(config: ModelConfig):
    """OpenAI or Azure OpenAI.

    Routes to the Responses API (/v1/responses) ONLY when this model opts into
    `reasoning_effort` — because /v1/chat/completions rejects reasoning_effort
    together with function tools on GPT-5.x. Everything else stays on the chat
    completions endpoint (today's behavior).
    """
    from openai import AsyncAzureOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    endpoint, api_version = _parse_azure_url(config.url)
    extra = config.extra_args or {}
    client = AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        api_version=api_version,
        api_key=config.key or os.environ.get("AZURE_OPENAI_API_KEY", ""),
        timeout=_client_timeout(extra),
        # The SDK's own default (2) retries a failed/timed-out request, each
        # retry taking up to the FULL timeout again -- found in practice a
        # chat request can hang 5+ minutes even with timeout=120, because
        # that's 3 attempts (1 + 2 retries) each allowed 120s, not a single
        # 120s-bounded attempt. 0 makes `timeout` the actual ceiling.
        max_retries=0,
    )
    provider = OpenAIProvider(openai_client=client)
    if "reasoning_effort" in extra:
        return OpenAIResponsesModel(
            config.name, provider=provider,
            settings=_responses_settings_from_extra_args(extra),
        )
    return OpenAIChatModel(
        config.name, provider=provider,
        settings=_openai_settings_from_extra_args(extra),
    )


def _build_anthropic_model(config: ModelConfig):
    """Claude via the Anthropic API."""
    from anthropic import AsyncAnthropic
    from pydantic_ai.models.anthropic import AnthropicModel
    from pydantic_ai.providers.anthropic import AnthropicProvider

    client = AsyncAnthropic(
        api_key=config.key or os.environ.get("ANTHROPIC_API_KEY"),
        base_url=config.url,  # None unless user is proxying
        timeout=_client_timeout(config.extra_args),
        max_retries=0,  # see _build_openai_model's max_retries comment
    )
    return AnthropicModel(config.name, provider=AnthropicProvider(anthropic_client=client))


def _build_vllm_model(config: ModelConfig):
    """vLLM-served model via its OpenAI-compatible HTTP endpoint."""
    from openai import AsyncOpenAI
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    client = AsyncOpenAI(
        base_url=config.url,
        api_key=config.key or "vllm",  # vLLM doesn't require auth by default
        timeout=_client_timeout(config.extra_args),
        max_retries=0,  # see _build_openai_model's max_retries comment
    )
    return OpenAIChatModel(
        config.name,
        provider=OpenAIProvider(openai_client=client),
        settings=_openai_settings_from_extra_args(config.extra_args),
    )


_BUILDERS = {
    "openai":    _build_openai_model,
    "anthropic": _build_anthropic_model,
    "vllm":      _build_vllm_model,
}


def get_pydantic_ai_model(config: ModelConfig):
    """Build a PydanticAI model instance from a ModelConfig."""
    if config.type == "local":
        raise ValueError(
            "type='local' (in-process HuggingFace) is not supported for the PydanticAI agent — "
            "it blocks the event loop. Serve the model via vLLM and use type='vllm' instead, "
            "with url pointing to the vLLM server (e.g. http://localhost:8000/v1)."
        )
    builder = _BUILDERS.get(config.type)
    if builder is None:
        raise ValueError(f"Unsupported model type {config.type!r}. Valid: {list(_BUILDERS) + ['local']}")
    return builder(config)


@functools.cache
def get_large_pydantic_model():
    """Cached PydanticAI model for the large (orchestrator) model."""
    return get_pydantic_ai_model(get_settings().large_model)
