"""
src/models — Central repository of common LLM model factories.

Two entry points:
  - configured.py        : raw AsyncOpenAI clients for direct chat completions
                            (used by SQL / RAG / job-pred chain code)
  - pydantic_ai.py       : PydanticAI model instances (used by the agent)

Submodules are loaded lazily on first attribute access so that importing one
adapter does not pull in the other's dependencies.
"""
import importlib
from typing import TYPE_CHECKING

_LAZY = {
    # configured.py exports
    "make_openai_client":         ("configured", "make_openai_client"),
    "get_large_model_client":     ("configured", "get_large_model_client"),
    "get_small_model_client":     ("configured", "get_small_model_client"),
    "get_small_model_client_opt": ("configured", "get_small_model_client_opt"),
    "get_sql_model_client":       ("configured", "get_sql_model_client"),
    "get_sql_model_client_opt":   ("configured", "get_sql_model_client_opt"),
    "get_large_model_name":       ("configured", "get_large_model_name"),
    "get_small_model_name":       ("configured", "get_small_model_name"),
    "get_sql_model_name":         ("configured", "get_sql_model_name"),
    # pydantic_ai.py exports
    "get_pydantic_ai_model":      ("pydantic_ai", "get_pydantic_ai_model"),
    "get_large_pydantic_model":   ("pydantic_ai", "get_large_pydantic_model"),
}


def __getattr__(name: str):
    if name not in _LAZY:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = _LAZY[name]
    module = importlib.import_module(f"{__name__}.{module_name}")
    value = getattr(module, attr)
    globals()[name] = value
    return value


def __dir__():
    return sorted(list(_LAZY.keys()) + list(globals().keys()))


if TYPE_CHECKING:
    from .configured import (
        make_openai_client,
        get_large_model_client, get_small_model_client, get_small_model_client_opt,
        get_sql_model_client, get_sql_model_client_opt,
        get_large_model_name, get_small_model_name, get_sql_model_name,
    )
    from .pydantic_ai import get_pydantic_ai_model, get_large_pydantic_model
