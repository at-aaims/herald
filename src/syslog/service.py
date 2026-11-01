"""
src/syslog/service.py — FastAPI router for the syslog monitor.

Endpoints (mounted under /api/syslog so the Next.js /api rewrite proxies them):
  GET  /api/syslog/stream?source=&speed=&node=&include_residuals=&severities=
       SSE stream of ParsedEvent JSON. `severities` (CSV) restricts which
       levels are emitted; ingestion/buffering/persistence cover all events.
  GET  /api/syslog/stats
       Live classifier counters.
  POST /api/syslog/explain
       Causal walker: clicked event -> upstream causes within lookback window.
  GET  /api/syslog/graph
       Full causal DAG (tier1+tier2 edges).

Later phases:
  POST /api/syslog/actions  - LLM-generated operator guidance (P3)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse, StreamingResponse

from collections import Counter

from src.syslog import state, proposals_queue
from src.syslog.actions import generate_actions
from src.syslog.causal import explain_click
from src.syslog.ingest import replay_source

router = APIRouter(prefix="/api/syslog", tags=["syslog"])

_classifier = state.classifier
_ringbuffer = state.ringbuffer
_graph = state.causal_graph


_last_flushed_type_counts: Counter[str] = Counter()


def _flush_true_counts(store) -> None:
    
    
    global _last_flushed_type_counts
    current = _classifier.stats.counts_by_type
    delta = {
        et: current[et] - _last_flushed_type_counts.get(et, 0)
        for et in current
        if current[et] > _last_flushed_type_counts.get(et, 0)
    }
    if delta:
        bucket_ts = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        try:
            store.record_true_counts(bucket_ts, delta)
        except Exception:
            pass  # never let this kill the live stream
    _last_flushed_type_counts = Counter(current)


_DEMO_JSONL = str(Path(__file__).resolve().parent.parent.parent / ".data" / "syslog_demo.jsonl")
_LEGACY_CSV = str(Path(__file__).resolve().parent.parent.parent / ".data" / "sample_data_logs.csv")
DEFAULT_SAMPLE = _DEMO_JSONL if Path(_DEMO_JSONL).exists() else _LEGACY_CSV


_WRITE_BATCH_SIZE = 64

VALID_SEVERITIES = frozenset({"critical", "error", "warning", "info", "residual"})


def _parse_severities(raw: str | None) -> frozenset[str] | None:
    """Parse the ?severities= CSV into a set of levels to emit.

    Returns None (no filter — emit everything) when the param is absent,
    empty, or contains no recognized level. Unknown tokens are dropped so a
    typo can't silently blackhole the whole stream.
    """
    if not raw:
        return None
    wanted = {s.strip().lower() for s in raw.split(",") if s.strip()}
    wanted &= VALID_SEVERITIES
    return frozenset(wanted) if wanted else None


async def _sse_stream(
    source: str,
    speed_eps: float,
    node: str,
    include_residuals: bool,
    loop: bool,
    severities: frozenset[str] | None = None,
):
    """Async generator that yields SSE-framed JSON events.

    Every classified event is added to the ring buffer and persisted so the
    causal walker and store see the full picture; `severities`, when set,
    only restricts which events are *emitted* over this SSE channel.
    """
    _classifier.emit_residuals = include_residuals
    write_buffer: list = []
    store = None  # lazy-init on first event so a missing DB file doesn't kill the stream
    loop_clock = asyncio.get_event_loop()
    last_true_flush = loop_clock.time()
    try:
        async for raw in replay_source(
            source, speed_eps=speed_eps, default_node=node, loop=loop,
        ):
            ev = _classifier.classify(
                raw.log_message,
                node=raw.node,
                ts=raw.ts,
                pid=raw.pid,
                identifier=raw.identifier,
            )
            now_mono = loop_clock.time()
            if now_mono - last_true_flush >= 2.0:
                if store is None:
                    try:
                        store = state.syslog_store()
                    except Exception:
                        store = False
                if store:
                    _flush_true_counts(store)
                last_true_flush = now_mono
            if ev is None:
                continue
            _ringbuffer.add(ev)
            write_buffer.append(ev)
            if len(write_buffer) >= _WRITE_BATCH_SIZE:
                if store is None:
                    try:
                        store = state.syslog_store()
                    except Exception:
                        store = False  # disable for this stream; ringbuffer still works
                if store:
                    try:
                        store.write_events(write_buffer)
                    except Exception:
                        pass  # never let the persistent store kill the live stream
                write_buffer.clear()
            
            if severities is not None and ev.severity not in severities:
                continue
            yield f"data: {json.dumps(ev.to_dict())}\n\n"
    except asyncio.CancelledError:
        # Client disconnected — flush any partial batch.
        if write_buffer and store:
            try: store.write_events(write_buffer)
            except Exception: pass
        if store:
            _flush_true_counts(store)
        return
    except FileNotFoundError as exc:
        err = json.dumps({"error": str(exc)})
        yield f"event: error\ndata: {err}\n\n"
    finally:
        # End-of-stream (replay finished, loop=False): flush remainder.
        if write_buffer and store:
            try: store.write_events(write_buffer)
            except Exception: pass
        if store:
            _flush_true_counts(store)
        try:
            yield "event: end\ndata: {}\n\n"
        except Exception:
            pass


@router.get("/stream")
async def stream(
    source: str = Query(DEFAULT_SAMPLE, description="Path to CSV log source"),
    speed: float = Query(50.0, ge=0.1, le=10_000.0, description="Events per second"),
    node: str = Query("node-0", description="Synthetic node id for the replay"),
    include_residuals: bool = Query(True, description="Emit unmatched lines"),
    loop: bool = Query(False, description="Restart the CSV at EOF"),
    severities: str | None = Query(
        None,
        description="CSV of severity levels to emit (e.g. 'critical,error'). "
                    "Absent/empty = emit all. The backend always classifies, "
                    "buffers, and persists every event regardless of this filter.",
    ),
):
    """
    SSE replay of classified syslog events.

    Each `data:` frame is a JSON ParsedEvent:
      { ts, node, event_type|null, raw, severity, subsystem, pid, identifier }
    """
    if not Path(source).exists():
        return JSONResponse({"error": f"source not found: {source}"}, status_code=404)

    return StreamingResponse(
        _sse_stream(source, speed, node, include_residuals, loop,
                    severities=_parse_severities(severities)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )


RATE_FLAG_RATIO = 10.0
RATE_FLAG_MIN_PER_SEC = 0.05


def _flag_high_frequency(
    since_buckets: dict[str, list[int]], bucket_seconds: int, recent_buckets: int = 3,
) -> list[dict]:

    window_seconds = recent_buckets * bucket_seconds
    rates: dict[str, float] = {}
    for et, buckets in since_buckets.items():
        recent = buckets[-recent_buckets:] if len(buckets) >= recent_buckets else buckets
        if not recent:
            continue
        rate = sum(recent) / window_seconds
        if rate > 0:
            rates[et] = rate
    if len(rates) < 2:
        return []
    sorted_rates = sorted(rates.values())
    mid = len(sorted_rates) // 2
    median_rate = (
        sorted_rates[mid] if len(sorted_rates) % 2
        else (sorted_rates[mid - 1] + sorted_rates[mid]) / 2
    )
    if median_rate <= 0:
        return []
    flags = []
    for et, rate in rates.items():
        ratio = rate / median_rate
        if ratio >= RATE_FLAG_RATIO and rate >= RATE_FLAG_MIN_PER_SEC:
            flags.append({
                "event_type": et,
                "rate_per_sec": round(rate, 4),
                "median_rate_per_sec": round(median_rate, 4),
                "ratio": round(ratio, 1),
            })
    flags.sort(key=lambda f: f["ratio"], reverse=True)
    return flags


@router.get("/stats")
async def stats(since_hours: float = Query(24.0, gt=0, le=168)) -> JSONResponse:

    since_counts: dict[str, int] | None = None
    since_buckets: dict[str, list[int]] | None = None
    try:
        store = state.syslog_store()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        since_counts = store.counts_since(cutoff)

        all_types = sorted(since_counts, key=since_counts.get, reverse=True)[:200]
        bucket_seconds = max(60, int(since_hours * 3600 / 24))
        since_buckets = store.bucketed_counts(cutoff, bucket_seconds, all_types)
    except Exception:
        pass
    rate_flags = _flag_high_frequency(since_buckets, bucket_seconds) if since_buckets else []
    return JSONResponse({
        "classifier": _classifier.stats_snapshot(),
        "ringbuffer": {
            "nodes": _ringbuffer.nodes(),
            "total_bins": _ringbuffer.total_bins(),
        },
        "since_hours": since_hours,
        "since_counts": since_counts,
        "since_buckets": since_buckets,
        "rate_flags": rate_flags,
    })


class ExplainRequest(BaseModel):
    event_type: str = Field(..., description="Clicked event type label")
    node: str = Field(..., description="Node where the event fired")
    ts: datetime = Field(..., description="Timestamp of the clicked event (ISO8601)")
    lookback_seconds: int = Field(
        60, ge=1, le=3600,
        description="How far back to scan for upstream causes (sliding per hop)",
    )
    max_depth: int = Field(
        1, ge=1, le=10,
        description=(
            "Maximum hops to walk upstream through the causal graph. "
            "1 = direct causes only (original behavior). "
            "5 = full cascade trace, UI default."
        ),
    )


@router.post("/explain")
async def explain(req: ExplainRequest = Body(...)) -> JSONResponse:
    """
    """
    try:
        graph = _graph()
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)

    resp = explain_click(
        graph,
        _ringbuffer,
        event_type=req.event_type,
        node=req.node,
        ts=req.ts,
        lookback_seconds=req.lookback_seconds,
        max_depth=req.max_depth,
    )
    return JSONResponse(resp.to_dict())


@router.get("/graph")
async def graph() -> JSONResponse:
    """Full causal DAG (tier1+tier2 edges) for sidebar visualization."""
    try:
        return JSONResponse(_graph().to_dict())
    except FileNotFoundError as exc:
        return JSONResponse({"error": str(exc)}, status_code=503)


class ActionsRequest(BaseModel):
    """Mirror of the ExplainResponse fields that the action generator needs."""
    clicked: dict
    edges_with_instances: list[dict] = Field(default_factory=list)
    candidates_without_instances: list[dict] = Field(default_factory=list)
    lookback_seconds: int = 60


class ApproveProposalRequest(BaseModel):
    file: str = Field(..., description="Proposals file name, e.g. syslog_proposals_<ts>.json")
    index: int = Field(..., ge=0)
    overrides: dict | None = Field(
        default=None,
        description="Optional per-field overrides before approval (event_type, regex, "
                    "subsystem, severity, description, ignorecase).",
    )
    keep_upstream: list[str] | None = Field(
        default=None,
        description="Subset of LLM-proposed upstream labels to keep. "
                    "None = keep all; [] = drop all.",
    )
    keep_downstream: list[str] | None = Field(
        default=None,
        description="Subset of LLM-proposed downstream labels to keep. "
                    "None = keep all; [] = drop all.",
    )


class RejectProposalRequest(BaseModel):
    file: str
    index: int = Field(..., ge=0)
    reason: str | None = None


@router.get("/proposals")
async def list_proposals() -> JSONResponse:
    """
    Pending proposals across all .data/syslog_proposals_*.json files,
    minus anything already approved (in extension JSONL) or already
    rejected (in rejected JSONL). Newest proposer files first.
    """
    return JSONResponse({
        "pending": proposals_queue.list_pending(),
        "summary": proposals_queue.summary(),
    })


@router.post("/proposals/approve")
async def approve_proposal(req: ApproveProposalRequest = Body(...)) -> JSONResponse:
    """Append the proposal to the extension JSONL. Restart the API for
    the new pattern to be picked up by patterns_extension.py."""
    try:
        entry = proposals_queue.approve(
            req.file, req.index,
            overrides=req.overrides,
            keep_upstream=req.keep_upstream,
            keep_downstream=req.keep_downstream,
        )
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"approved": entry, "restart_required": True})


@router.post("/proposals/reject")
async def reject_proposal(req: RejectProposalRequest = Body(...)) -> JSONResponse:
    """Append a rejection entry so this (event_type, regex) stops showing
    up in /api/syslog/proposals. No restart required."""
    try:
        entry = proposals_queue.reject(req.file, req.index, reason=req.reason)
    except KeyError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"rejected": entry})


@router.post("/actions")
async def actions(req: ActionsRequest = Body(...)) -> JSONResponse:
    """
    Generate operator-action markdown for a clicked event + cause subgraph.
    Cached per (effect, sorted-fired-causes) so repeat clicks are free.
    """
    result = await generate_actions(
        clicked=req.clicked,
        edges_with_instances=req.edges_with_instances,
        candidates_without_instances=req.candidates_without_instances,
        lookback_seconds=req.lookback_seconds,
    )
    if "error" in result:
        return JSONResponse(result, status_code=502)
    return JSONResponse(result)
