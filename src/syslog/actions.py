"""
src/syslog/actions.py — LLM-generated operator actions for a clicked event.

Given the explain-walker output (clicked event + fired upstream causes +
candidates that did not fire), this module calls HERALD's configured
large_model to produce a short markdown advisory: diagnosis paragraph,
operator actions with diagnostic commands, severity/escalation guidance.

The hot path (regex classify + ringbuffer add) never invokes an LLM.
This module is the click-time warm path — bounded by user interaction rate.
Results are cached by (effect, sorted-fired-cause-types) so repeated clicks
on the same cascade shape don't re-call the model.
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic_ai import Agent

from src.models.pydantic_ai import get_large_pydantic_model

DEFAULT_TAXONOMY_PATH = Path(__file__).parent / "event_taxonomy.md"
MAX_CACHE_ENTRIES = 256


@functools.cache
def _taxonomy_text() -> str:
    """Load and cache the 87-event taxonomy markdown."""
    path = Path(os.environ.get("HERALD_EVENT_TAXONOMY", DEFAULT_TAXONOMY_PATH))
    if not path.exists():
        logger.warning(f"event_taxonomy.md not found at {path}; actions will run without it")
        return "(event taxonomy file not available)"
    return path.read_text(encoding="utf-8")


@functools.cache
def _actions_agent() -> Agent:
    """A minimal Agent that just produces markdown advisories (no tools)."""
    return Agent(
        model=get_large_pydantic_model(),
        system_prompt=(
            "You are an HPC operations expert assistant for the Frontier supercomputer "
            "at Oak Ridge (over 9,400 nodes, 8 AMD MI250X GPUs per node, HPE Slingshot "
            "fabric, 716 PB Lustre filesystem).\n"
            "\n"
            "Given a CLICKED event and the UPSTREAM causes that fired before it on the "
            "same node, return concise markdown advice for an on-call operator. "
            "Ground your recommendations in the event taxonomy provided.\n"
            "\n"
            "Output sections, in this exact order, as markdown:\n"
            "  ### Diagnosis\n"
            "  Two or three sentences: what cascade is this likely showing, "
            "which subsystems are involved, what is the likely root cause.\n"
            "  ### Operator actions\n"
            "  A bulleted list of concrete steps, including specific diagnostic "
            "commands where applicable (slurmctld, sinfo, dmesg, lctl, "
            "rocm-smi, ipmitool, etc.). Be specific.\n"
            "  ### Severity & escalation\n"
            "  One bullet for severity (informational / warning / error / critical) "
            "and one for who to escalate to (operator on-call, vendor support, "
            "filesystem team, network team, etc.).\n"
            "\n"
            "Be terse. Do not restate the input. Do not add a preamble or sign-off.\n"
            "\n"
            "Event taxonomy reference:\n"
            f"{_taxonomy_text()}\n"
        ),
    )


@dataclass(frozen=True)
class _CacheKey:
    effect: str
    fired_causes: tuple[str, ...]   # sorted tuple


class _LRUDict:
    """Tiny FIFO-ish cache; functools.lru_cache requires hashable args."""
    def __init__(self, maxlen: int):
        self.maxlen = maxlen
        self._d: dict[_CacheKey, str] = {}

    def get(self, key: _CacheKey) -> str | None:
        return self._d.get(key)

    def put(self, key: _CacheKey, value: str) -> None:
        if len(self._d) >= self.maxlen:
            self._d.pop(next(iter(self._d)))
        self._d[key] = value


_cache = _LRUDict(MAX_CACHE_ENTRIES)


def _build_user_prompt(clicked: dict[str, Any],
                       edges_with_instances: list[dict[str, Any]],
                       candidates_without_instances: list[dict[str, Any]],
                       lookback_seconds: int) -> str:
    lines: list[str] = []
    lines.append(f"Clicked event: {clicked.get('event_type')}")
    lines.append(f"Node: {clicked.get('node')}")
    lines.append(f"Timestamp: {clicked.get('ts')}")
    lines.append(f"Lookback window: {lookback_seconds}s")
    lines.append("")
    if edges_with_instances:
        lines.append("Upstream causes that FIRED in the window:")
        for e in edges_with_instances:
            sample = e.get("instances") or [{}]
            raw = (sample[0].get("raw") or "")[:200]
            lines.append(
                f"- {e['cause']}  (tier={e['tier']}, "
                f"methods={e['num_methods']}/3, instances={e['instance_count']})"
            )
            if raw:
                lines.append(f"    example: {raw}")
    else:
        lines.append("Upstream causes that FIRED in the window: (none)")
    lines.append("")
    if candidates_without_instances:
        lines.append("Causes in the static graph that did NOT fire in the window:")
        for c in candidates_without_instances:
            lines.append(f"- {c['cause']}  (tier={c['tier']})")
    return "\n".join(lines)


async def generate_actions(
    *,
    clicked: dict[str, Any],
    edges_with_instances: list[dict[str, Any]],
    candidates_without_instances: list[dict[str, Any]],
    lookback_seconds: int,
) -> dict[str, Any]:
    """
    Return {"actions": markdown, "cached": bool, "model": name}.
    Errors are returned in {"error": ...} rather than raised, so the UI can
    show the DAG even if the LLM is unreachable.
    """
    effect = clicked.get("event_type") or "UNKNOWN"
    fired = tuple(sorted(e["cause"] for e in edges_with_instances))
    cache_key = _CacheKey(effect=effect, fired_causes=fired)

    cached = _cache.get(cache_key)
    if cached is not None:
        return {"actions": cached, "cached": True, "model": _model_name()}

    user_prompt = _build_user_prompt(
        clicked, edges_with_instances, candidates_without_instances, lookback_seconds,
    )

    try:
        agent = _actions_agent()
        result = await agent.run(user_prompt)
    except Exception as exc:
        logger.exception("operator-action generation failed")
        return {"error": f"{type(exc).__name__}: {exc}"}

    output = getattr(result, "output", None) or getattr(result, "data", None) or str(result)
    text = str(output).strip()
    _cache.put(cache_key, text)
    return {"actions": text, "cached": False, "model": _model_name()}


def _model_name() -> str:
    from src.config import get_settings
    cfg = get_settings().large_model
    return f"{cfg.type}:{cfg.name}"
