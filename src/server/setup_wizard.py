"""
src/server/setup_wizard.py — in-app config wizard, the web equivalent of setup.sh.

Writes .env directly (same file, same format setup.sh / .env.example use),
then clears every cache that would otherwise hold onto the pre-reconfigure
model/settings, so the *next* request picks up the new config with no
backend restart. See api.py's /api/chat: it explicitly re-fetches
get_large_pydantic_model() per request rather than relying on herald_agent's
model (bound once at import time) for exactly this reason.

Never returns secret values back to the client — GET /api/setup/status
reports structure (which backend type, is a key present) not contents.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import JSONResponse

from src.config import PROJECT_ROOT

router = APIRouter(prefix="/api/setup", tags=["setup"])

ENV_PATH = PROJECT_ROOT / ".env"


def _read_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    out: dict[str, str] = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _write_env(updates: dict[str, str]) -> None:
    """Merge `updates` into .env, preserving every other existing line."""
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    seen: set[str] = set()
    out_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                out_lines.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out_lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            out_lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(out_lines) + "\n")


def _reload_config() -> None:
    """Drop every cache downstream of .env so the next request rebuilds
    fresh from the file just written. See module docstring."""
    import src.config as config_module
    config_module._get_settings.cache_clear()

    import src.models.configured as configured_module
    configured_module.get_large_model_client.cache_clear()
    configured_module.get_small_model_client.cache_clear()
    configured_module.get_small_model_client_opt.cache_clear()
    configured_module.get_sql_model_client.cache_clear()
    configured_module.get_sql_model_client_opt.cache_clear()

    import src.models.pydantic_ai as pydantic_ai_module
    pydantic_ai_module.get_large_pydantic_model.cache_clear()


@router.get("/status")
async def status() -> JSONResponse:
    """Current config, non-secret fields only — lets the wizard show
    'already configured, reconfigure?' the same way setup.sh does."""
    env = _read_env()
    configured = bool(env.get("LARGE_MODEL__TYPE"))
    sub_configured = bool(env.get("SMALL_MODEL__TYPE") == "openai" or env.get("SMALL_MODEL__TYPE") == "vllm") \
        and env.get("SMALL_MODEL__TYPE") != "disabled"
    return JSONResponse({
        "configured": configured,
        "large_model_type": env.get("LARGE_MODEL__TYPE"),
        "large_model_name": env.get("LARGE_MODEL__NAME"),
        "sub_agents_configured": sub_configured,
        "enabled_tools": env.get("ENABLED_TOOLS", '["jobpred"]'),
    })


class SubModelConfig(BaseModel):
    type: Literal["openai", "vllm"]
    name: str
    url: str
    key: str | None = None


class ConfigureRequest(BaseModel):
    large_model_type: Literal["anthropic", "openai", "vllm"]
    large_model_name: str
    large_model_url: str | None = None
    large_model_key: str | None = None

    configure_sub_agents: bool = False
    # Independent on purpose — e.g. SQLcoder-8B for SQL vs. a general chat
    # model for RAG/jobpred is a real, intentional combination (see README's
    # "Tested combinations" table), not an edge case to collapse into one.
    small_model: SubModelConfig | None = None  # RAG + job-prediction
    sql_model: SubModelConfig | None = None


@router.post("/configure")
async def configure(req: ConfigureRequest) -> JSONResponse:
    # Always write URL/KEY explicitly (empty string when unused by this type),
    # not just when truthy — otherwise switching e.g. openai -> anthropic
    # leaves the old URL/KEY line stale in .env instead of clearing it.
    updates: dict[str, str] = {
        "LARGE_MODEL__TYPE": req.large_model_type,
        "LARGE_MODEL__NAME": req.large_model_name,
        "LARGE_MODEL__URL": req.large_model_url or "",
        "LARGE_MODEL__KEY": req.large_model_key or "",
    }

    if req.configure_sub_agents and req.small_model and req.sql_model:
        for prefix, cfg in (("SMALL_MODEL", req.small_model), ("SQL_MODEL", req.sql_model)):
            updates[f"{prefix}__TYPE"] = cfg.type
            updates[f"{prefix}__NAME"] = cfg.name
            updates[f"{prefix}__URL"] = cfg.url
            updates[f"{prefix}__KEY"] = cfg.key or ""

    # ENABLED_TOOLS is derived from the RESULTING .env state, not from this
    # request's configure_sub_agents flag -- that flag only reflects whether
    # THIS particular submission touched the sub-agent fields. Deriving it
    # from the flag directly meant re-submitting the form for any other
    # reason (e.g. just changing the orchestrator), with the "configure
    # sub-agents" checkbox back at its unchecked default (the frontend never
    # pre-populates it from current status), silently reset ENABLED_TOOLS to
    # jobpred-only -- while SMALL_MODEL/SQL_MODEL stayed correctly configured
    # in .env the whole time, since _write_env only touches keys it's given.
    # Reading the actual post-write state instead makes this self-healing
    # regardless of which submission set SMALL_MODEL/SQL_MODEL, or whether
    # they were set by setup.sh/manual .env editing instead of this form.
    merged = {**_read_env(), **updates}
    sub_agents_present = merged.get("SMALL_MODEL__TYPE") in ("openai", "vllm") \
        and merged.get("SQL_MODEL__TYPE") in ("openai", "vllm")
    updates["ENABLED_TOOLS"] = '["sql", "rag", "jobpred"]' if sub_agents_present else '["jobpred"]'

    # Defaults every install needs, same as setup.sh — harmless to rewrite
    # on every configure call since they're not user-chosen.
    updates.setdefault("DB_MODULE", "src.site.ornl.frontier.db")
    updates.setdefault("CUDA_VISIBLE_DEVICES", "0")
    updates.setdefault("DATA_BASE", ".data/shared")
    updates.setdefault("DATA_PRIV_BASE", ".data/private")
    updates.setdefault("HERALD_API_URL", "http://localhost:8000")

    _write_env(updates)
    _reload_config()

    return JSONResponse({"ok": True})
