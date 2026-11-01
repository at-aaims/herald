"""
src/syslog/ingest.py — replay adapters for log sources.

"""
from __future__ import annotations

import asyncio
import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator, Iterable

from src.syslog.timeutil import parse_timestamp as _parse_ts


@dataclass
class RawLog:
    ts: datetime
    node: str
    log_message: str
    pid: int | None = None
    identifier: str | None = None


def as_scalar(value: object) -> object:
    """Guards against a field unexpectedly resolving to a dict/list (e.g. an
    ingestion connector's field-map pointing at a nested object instead of a
    leaf value) — without this, str(value) would silently write a Python
    dict/list repr into a column meant to hold a plain string. Shared by
    ingest_kafka.py and ingest_elasticsearch.py."""
    return None if isinstance(value, (dict, list)) else value


def as_int(value: object) -> int | None:
    """Best-effort int coercion for fields like `pid` arriving from external
    JSON, where a producer may have stringified a numeric value. Returns
    None (not a raised exception) for anything uncoercible, matching
    replay_parquet's existing pid-parsing pattern below."""
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _iter_csv_messages(path: Path) -> Iterable[str]:
    """Yield the log_message column from a CSV. Tolerates BOM and unnamed index col."""
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return
        # The sample CSV uses an empty first header; resolve column robustly.
        msg_col = "log_message"
        if msg_col not in reader.fieldnames:
            # Fall back to the last column if the schema is odd.
            msg_col = reader.fieldnames[-1]
        for row in reader:
            msg = row.get(msg_col)
            if msg:
                yield msg


async def replay_csv(
    path: str | Path,
    *,
    speed_eps: float = 50.0,
    node: str = "node-0",
    start_ts: datetime | None = None,
    loop: bool = False,
) -> AsyncIterator[RawLog]:
    """
    Async generator that yields RawLog records from a CSV at ~speed_eps lines/sec.

    Parameters
    ----------
    path :  file
    speed_eps : events per second
    node : synthetic node id 
    start_ts : first synthesized timestamp; defaults to "now" UTC
    loop : if True, restart at EOF (useful for indefinite demo)
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Log source not found: {p}")

    delay = 1.0 / max(speed_eps, 0.001)
    ts = start_ts or datetime.now(timezone.utc)

    while True:
        for msg in _iter_csv_messages(p):
            yield RawLog(ts=ts, node=node, log_message=msg)
            ts = ts + timedelta(seconds=delay)
            # Real-time pacing — yields control to the event loop.
            if delay > 0:
                await asyncio.sleep(delay)
        if not loop:
            return


async def replay_jsonl(
    path: str | Path,
    *,
    speed_eps: float = 50.0,
    default_node: str = "node-0",
    loop: bool = False,
) -> AsyncIterator[RawLog]:
    """
    Replay a JSONL file at speed_eps records/sec.

    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Log source not found: {p}")

    delay = 1.0 / max(speed_eps, 0.001)

    while True:
        synth_ts = datetime.now(timezone.utc)
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = rec.get("log_message")
                if not msg:
                    continue
                ts = _parse_ts(rec.get("ts")) or synth_ts
                yield RawLog(
                    ts=ts,
                    node=rec.get("node") or default_node,
                    log_message=msg,
                    pid=rec.get("pid"),
                    identifier=rec.get("identifier"),
                )
                synth_ts = synth_ts + timedelta(seconds=delay)
                if delay > 0:
                    await asyncio.sleep(delay)
        if not loop:
            return


async def replay_parquet(
    path: str | Path,
    *,
    speed_eps: float = 50.0,
    default_node: str = "node-0",
    loop: bool = False,
) -> AsyncIterator[RawLog]:
    """
    """
    import pyarrow.parquet as pq  # local import — pyarrow only loaded on demand

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Log source not found: {p}")

    delay = 1.0 / max(speed_eps, 0.001)
    cols_we_want = ["timestamp", "log_message", "name", "pid", "identifier"]

    while True:
        synth_ts = datetime.now(timezone.utc)
        pf = pq.ParquetFile(str(p))
        present = [c for c in cols_we_want if c in pf.schema_arrow.names]
        for batch in pf.iter_batches(columns=present):
            df = batch.to_pandas()
            for col in cols_we_want:
                if col not in df.columns:
                    df[col] = None
            for _, row in df.iterrows():
                msg = row.get("log_message")
                if not msg:
                    continue
                ts = _parse_ts(row.get("timestamp")) or synth_ts
                pid = as_int(row.get("pid"))
                yield RawLog(
                    ts=ts,
                    node=str(row.get("name") or default_node),
                    log_message=str(msg),
                    pid=pid,
                    identifier=row.get("identifier"),
                )
                synth_ts = synth_ts + timedelta(seconds=delay)
                if delay > 0:
                    await asyncio.sleep(delay)
        if not loop:
            return


async def replay_source(
    path: str | Path,
    *,
    speed_eps: float = 50.0,
    default_node: str = "node-0",
    loop: bool = False,
) -> AsyncIterator[RawLog]:
    """Dispatch to the right adapter by file extension."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        gen = replay_jsonl(p, speed_eps=speed_eps, default_node=default_node, loop=loop)
    elif suffix in (".parquet", ".pq"):
        gen = replay_parquet(p, speed_eps=speed_eps, default_node=default_node, loop=loop)
    else:
        gen = replay_csv(p, speed_eps=speed_eps, node=default_node, loop=loop)
    async for raw in gen:
        yield raw
