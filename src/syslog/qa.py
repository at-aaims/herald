"""
src/syslog/qa.py 
"""
from __future__ import annotations

import functools
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.syslog import state
from src.syslog.actions import DEFAULT_TAXONOMY_PATH, generate_actions
from src.syslog.causal import explain_click
from src.syslog.classifier import StreamingClassifier
from src.syslog.patterns import LOG_PATTERNS, subsystem_for
from src.syslog.ringbuffer import PerNodeRingBuffer

MAX_INSTANCES_RETURNED = 5
MAX_NODES_IN_SUMMARY = 8


@functools.cache
def _taxonomy_lines() -> dict[str, str]:
    """
    Pre-index the taxonomy markdown by event-type label so describe_event()
    is a dict lookup. Rows look like:
        | 0 | NET_CXI_RAW_DATA | CXI raw data event  |
    """
    path = Path(os.environ.get("HERALD_EVENT_TAXONOMY", DEFAULT_TAXONOMY_PATH))
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) == 3:
            _idx, label, desc = parts
            if label in LOG_PATTERNS or label.startswith(("HW_", "CTX_")):
                out[label] = desc
    return out


def known_event_types() -> list[str]:
    """All event-type labels known to the classifier (sorted)."""
    return sorted(LOG_PATTERNS.keys())


def describe_event(
    event_type: str,
    *,
    classifier: StreamingClassifier | None = None,
    ringbuffer: PerNodeRingBuffer | None = None,
) -> dict[str, Any]:
    """
    Look up an event type in the causal graph + taxonomy + recent ringbuffer.

    If event_type is unknown, returns {"error": ..., "suggestions": [...]}.
    """
    classifier = classifier or state.classifier
    ringbuffer = ringbuffer or state.ringbuffer

    if event_type not in LOG_PATTERNS:
        suggestions = [t for t in LOG_PATTERNS if event_type.upper() in t.upper()][:10]
        return {
            "error": f"Unknown event type {event_type!r}.",
            "suggestions": suggestions,
            "hint": "Use one of the labels from known_event_types().",
        }

    graph = state.causal_graph()
    upstream = [e.to_dict() for e in graph.causes_of(event_type)]
    downstream = [e.to_dict() for e in graph.effects_of(event_type)]
    description = _taxonomy_lines().get(event_type) or "(no taxonomy entry)"

    # Pull recent instances of this type across all nodes.
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=1)
    instances: list[dict[str, Any]] = []
    for node in ringbuffer.nodes():
        for ev in ringbuffer.events_for_node(node, since=since, until=now, of_types=[event_type]):
            instances.append({
                "ts": ev.ts.isoformat(),
                "node": ev.node,
                "raw": ev.raw,
                "severity": ev.severity,
            })
    instances.sort(key=lambda x: x["ts"], reverse=True)

    return {
        "event_type": event_type,
        "subsystem": subsystem_for(event_type),
        "description": description,
        "upstream_causes": upstream,
        "downstream_effects": downstream,
        "is_independent_source": not upstream,
        "is_terminal_effect": not downstream,
        "recent_instances": instances[:MAX_INSTANCES_RETURNED],
        "recent_instance_count": len(instances),
    }


def _max_event_ts(ringbuffer: PerNodeRingBuffer) -> datetime | None:
    """Latest event timestamp across all nodes (for replay-aware windowing)."""
    best: datetime | None = None
    for node in ringbuffer.nodes():
        events = ringbuffer.events_for_node(
            node,
            since=datetime.fromtimestamp(0, tz=timezone.utc),
            until=datetime.now(timezone.utc) + timedelta(days=365),
        )
        if events:
            ts = max(ev.ts for ev in events)
            if best is None or ts > best:
                best = ts
    return best


def recent_activity(
    *,
    classifier: StreamingClassifier | None = None,
    ringbuffer: PerNodeRingBuffer | None = None,
    window_seconds: int = 300,
) -> dict[str, Any]:
    """
    """
    classifier = classifier or state.classifier
    ringbuffer = ringbuffer or state.ringbuffer

    now_wall = datetime.now(timezone.utc)
    now_data = _max_event_ts(ringbuffer)
    anchor = now_data or now_wall
    since = anchor - timedelta(seconds=window_seconds)

    window_counts: Counter[str] = Counter()
    per_node: dict[str, dict[str, Any]] = {}
    nodes = ringbuffer.nodes()[:MAX_NODES_IN_SUMMARY]
    for node in nodes:
        node_counts = ringbuffer.counts_window(node, since=since, until=anchor)
        window_counts.update(node_counts)
        per_node[node] = {
            "total_events": sum(node_counts.values()),
            "top_types": dict(node_counts.most_common(5)),
        }

    return {
        "window_seconds": window_seconds,
        "anchor_ts": anchor.isoformat(),
        "anchor_source": "latest_event" if now_data else "wallclock",
        "wallclock_lag_seconds": int((now_wall - anchor).total_seconds()),
        "classifier_stats": classifier.stats_snapshot(),
        "ringbuffer_nodes": ringbuffer.nodes(),
        "events_in_window": sum(window_counts.values()),
        "top_event_types_in_window": dict(window_counts.most_common(10)),
        "per_node": per_node,
    }


def _latest_instance(
    ringbuffer: PerNodeRingBuffer,
    event_type: str,
    *,
    node: str | None = None,
) -> tuple[datetime, str] | None:
    """Most recent (ts, node) for `event_type` in the ringbuffer, or None.

    """
    nodes = [node] if node else ringbuffer.nodes()
    since = datetime.fromtimestamp(0, tz=timezone.utc)
    until = datetime.now(timezone.utc) + timedelta(days=365)
    best: tuple[datetime, str] | None = None
    for n in nodes:
        for ev in ringbuffer.events_for_node(n, since=since, until=until, of_types=[event_type]):
            if best is None or ev.ts > best[0]:
                best = (ev.ts, ev.node)
    return best


async def explain_event_occurrence(
    event_type: str,
    *,
    node: str | None = None,
    ts: str | None = None,
    lookback_seconds: int = 60,
    max_depth: int = 5,
    include_advisory: bool = True,
    ringbuffer: PerNodeRingBuffer | None = None,
) -> dict[str, Any]:
    """
    """
    ringbuffer = ringbuffer or state.ringbuffer

    if event_type not in LOG_PATTERNS:
        suggestions = [t for t in LOG_PATTERNS if event_type.upper() in t.upper()][:10]
        return {
            "error": f"Unknown event type {event_type!r}.",
            "suggestions": suggestions,
            "hint": "Use one of the labels from known_event_types().",
        }

    resolved_ts: datetime | None = None
    if ts:
        try:
            resolved_ts = datetime.fromisoformat(ts)
        except ValueError:
            return {"error": f"Could not parse ts {ts!r}; expected ISO8601 "
                             "(e.g. '2026-06-03T14:22:01+00:00')."}
        if resolved_ts.tzinfo is None:
            resolved_ts = resolved_ts.replace(tzinfo=timezone.utc)

    if node is None or resolved_ts is None:
        latest = _latest_instance(ringbuffer, event_type, node=node)
        if latest is None:
            return {
                "error": (
                    f"No recent instance of {event_type!r}"
                    + (f" on node {node!r}" if node else "")
                    + " in the live ringbuffer (~1h)."
                ),
                "hint": "Pass an explicit `node` and `ts` (ISO8601) to explain an "
                        "older occurrence, or use query_syslog_history for "
                        "historical aggregates.",
            }
        inst_ts, inst_node = latest
        if resolved_ts is None:
            resolved_ts = inst_ts
        if node is None:
            node = inst_node

    graph = state.causal_graph()
    resp = explain_click(
        graph, ringbuffer,
        event_type=event_type, node=node, ts=resolved_ts,
        lookback_seconds=lookback_seconds, max_depth=max_depth,
    )
    out = resp.to_dict()
    out["resolved_anchor"] = {"node": node, "ts": resolved_ts.isoformat()}

    if include_advisory:
        if resp.independent:
            out["operator_advisory"] = {
                "note": "Event is independent — no upstream causes fired in the "
                        "lookback window, so no cascade advisory was generated.",
            }
        else:
            out["operator_advisory"] = await generate_actions(
                clicked=out["clicked"],
                edges_with_instances=out["edges_with_instances"],
                candidates_without_instances=out["candidates_without_instances"],
                lookback_seconds=lookback_seconds,
            )

    return out
