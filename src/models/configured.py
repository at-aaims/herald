"""
src.models.configured — Factories for model clients.

Replaces the old LangChain-wrapped factories. Returns raw `AsyncOpenAI` clients
for openai/vllm backends (used by the SQL / RAG / job-pred chain code that
calls models directly). The PydanticAI orchestrator uses
src/models/pydantic_ai.py instead, which wraps the same configs into
PydanticAI model instances.

Backend support:
  - openai     : Azure OpenAI deployment via AsyncAzureOpenAI
  - vllm       : self-hosted vLLM, OpenAI-compatible, via AsyncOpenAI
  - anthropic  : NOT supported here (use the PydanticAI agent path)
  - local      : NOT supported (serve via vLLM and switch type to 'vllm')
"""
import functools
import os
from openai import AsyncOpenAI, AsyncAzureOpenAI
from src.config import ModelConfig, OptModelConfig, get_settings


def make_openai_client(config: ModelConfig) -> AsyncOpenAI:
    """Build an AsyncOpenAI client from a ModelConfig. Used by SQL/RAG/jobpred."""
    if config.type == "openai":
        from src.models.pydantic_ai import _parse_azure_url, _client_timeout
        endpoint, api_version = _parse_azure_url(config.url)
        return AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_version=api_version,
            api_key=config.key or os.environ.get("AZURE_OPENAI_API_KEY", ""),
            timeout=_client_timeout(config.extra_args),
            # See src/models/pydantic_ai.py's _build_openai_model: the SDK's
            # default (2) retries, each re-allowed the full timeout, means
            # timeout alone doesn't bound total wait -- 0 makes it the
            # actual ceiling.
            max_retries=0,
        )
    if config.type == "vllm":
        from src.models.pydantic_ai import _client_timeout
        return AsyncOpenAI(
            base_url=config.url, api_key=config.key or "vllm",
            max_retries=0,
            timeout=_client_timeout(config.extra_args),
        )
    if config.type == "local":
        raise ValueError(
            "type='local' (in-process HuggingFace) is no longer supported. "
            "Serve the model via vLLM and use type='vllm' (with url=http://host:port/v1)."
        )
    if config.type == "anthropic":
        raise ValueError(
            "type='anthropic' is only supported for the large/orchestrator model. "
            "The SQL/RAG/jobpred sub-agents need an OpenAI-compatible endpoint."
        )
    raise ValueError(f"Unsupported model type: {config.type!r}")


def _client_for(cfg: OptModelConfig) -> AsyncOpenAI | None:
    if cfg == "disabled":
        return None
    return make_openai_client(cfg)


def _name_for(cfg: OptModelConfig) -> str | None:
    if cfg == "disabled":
        return None
    return cfg.name


# ── Large model (orchestrator) ──────────────────────────────────────────────
# The PydanticAI agent uses src.models.pydantic_ai.get_large_pydantic_model().
# This client is kept for ad-hoc direct usage.

@functools.cache
def get_large_model_client() -> AsyncOpenAI:
    return make_openai_client(get_settings().large_model)


def get_large_model_name() -> str:
    return get_settings().large_model.name


# ── Small model (RAG + job_pred feature extraction) ─────────────────────────

@functools.cache
def get_small_model_client() -> AsyncOpenAI:
    """Required: raises if small_model is disabled."""
    client = _client_for(get_settings().small_model)
    if client is None:
        raise RuntimeError("small_model is disabled in settings — cannot run RAG / jobpred")
    return client


@functools.cache
def get_small_model_client_opt() -> AsyncOpenAI | None:
    return _client_for(get_settings().small_model)


def get_small_model_name() -> str | None:
    return _name_for(get_settings().small_model)


def _extra_args_for(cfg: OptModelConfig) -> dict:
    if cfg == "disabled":
        return {}
    return dict(getattr(cfg, "extra_args", {}) or {})


def get_small_model_extra_args() -> dict:
    """Per-model generation kwargs (e.g. {'temperature': 0.1}) forwarded to the
    RAG chat calls. Empty for models like gpt-5.x that reject custom sampling
    params; set SMALL_MODEL__EXTRA_ARGS in .env for models that accept them."""
    return _extra_args_for(get_settings().small_model)


# ── SQL model (SQL Q&A) ──────────────────────────────────────────────────────

@functools.cache
def get_sql_model_client() -> AsyncOpenAI:
    """Required: raises if sql_model is disabled."""
    client = _client_for(get_settings().sql_model)
    if client is None:
        raise RuntimeError("sql_model is disabled in settings — cannot run SQL Q&A")
    return client


@functools.cache
def get_sql_model_client_opt() -> AsyncOpenAI | None:
    return _client_for(get_settings().sql_model)


def get_sql_model_name() -> str | None:
    return _name_for(get_settings().sql_model)
