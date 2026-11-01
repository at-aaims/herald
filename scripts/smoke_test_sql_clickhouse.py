"""
scripts/smoke_test_sql_clickhouse.py — exercise the ClickHouseSyslogStore.

Mirrors smoke_test_sql.py's Phase A but against a ClickHouse server. Skips
gracefully (exit 0) if ClickHouse is unreachable so this can live in CI
without forcing a CH dependency for every contributor.

Quick local setup (Docker):
    docker run -d --name clickhouse-herald \\
      -p 8123:8123 -p 9000:9000 \\
      --ulimit nofile=262144:262144 \\
      clickhouse/clickhouse-server

Then:
    .venv/bin/python scripts/smoke_test_sql_clickhouse.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog import state  # noqa: E402
from src.syslog.ingest import replay_source  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent / ".data" / "syslog_demo.jsonl"
SMOKE_DB = "herald_syslog_smoke"


def _try_build_store():
    """Return a ClickHouseSyslogStore or None if the server is unreachable."""
    try:
        from src.syslog.store import ClickHouseSyslogStore
    except ImportError as exc:
        print(f"[SKIP] clickhouse-connect not installed: {exc}")
        return None
    try:
        store = ClickHouseSyslogStore(
            host="localhost", port=8123,
            database=SMOKE_DB, user="default", password="",
        )
    except Exception as exc:
        print(f"[SKIP] ClickHouse unreachable at localhost:8123 — {exc}")
        print()
        print("    Start a local CH server with:")
        print("      docker run -d --name clickhouse-herald \\")
        print("        -p 8123:8123 -p 9000:9000 \\")
        print("        --ulimit nofile=262144:262144 \\")
        print("        clickhouse/clickhouse-server")
        return None
    return store


async def main() -> int:
    if not DEMO.exists():
        print(f"ERROR: demo JSONL not found at {DEMO}; run build_demo_cascades.py first")
        return 2

    store = _try_build_store()
    if store is None:
        return 0

    # Wipe the smoke DB before re-ingesting so runs are repeatable.
    store._client.command("TRUNCATE TABLE IF EXISTS events")

    # Drain the cascade demo into the CH store via the streaming classifier.
    batch: list = []
    n = 0
    async for raw in replay_source(DEMO, speed_eps=10_000, default_node="node-0"):
        ev = state.classifier.classify(
            raw.log_message, node=raw.node, ts=raw.ts,
            pid=raw.pid, identifier=raw.identifier,
        )
        if ev is None:
            continue
        batch.append(ev)
        n += 1
        if len(batch) >= 64:
            store.write_events(batch)
            batch.clear()
    if batch:
        store.write_events(batch)

    print(f"Ingested {n} classified events into ClickHouse db `{SMOKE_DB}`")
    print(f"store.event_count() = {store.event_count()}\n")

    queries = [
        ("Event counts by type (top 5)",
         "SELECT event_type, count() AS n FROM events GROUP BY event_type ORDER BY n DESC LIMIT 5"),
        ("Per-node event count",
         "SELECT node, count() AS n FROM events GROUP BY node ORDER BY n DESC"),
        ("Critical events with their static-graph causes",
         """SELECT e.node, e.ts, e.event_type, ce.cause, ce.tier
            FROM events e
            JOIN causal_edges ce ON ce.effect = e.event_type
            WHERE e.severity = 'critical'
            ORDER BY e.node, e.ts
            LIMIT 10"""),
        ("Cascade detection: causes within 60s before each APP_INFRA_FAIL",
         """WITH effects AS (
              SELECT ts, node FROM events WHERE event_type = 'APP_INFRA_FAIL'
            )
            SELECT e.node, e.ts AS effect_ts, c.event_type AS cause, ce.tier
            FROM effects e
            JOIN causal_edges ce ON ce.effect = 'APP_INFRA_FAIL'
            JOIN events c
              ON c.node = e.node
             AND c.event_type = ce.cause
             AND c.ts BETWEEN e.ts - INTERVAL 60 SECOND AND e.ts
            ORDER BY e.node, e.ts"""),
        ("P5c rollup: hourly histogram via events_rollup_1min (skips raw events)",
         """SELECT toStartOfHour(ts_bucket) AS hour,
                   event_type,
                   sum(n) AS events
            FROM events_rollup_1min
            WHERE event_type IN ('NET_CXI_TIMEOUT', 'APP_INFRA_FAIL', 'SYS_OOM_KILL')
            GROUP BY hour, event_type
            ORDER BY hour, event_type"""),
    ]
    for label, sql in queries:
        print(f"=== {label} ===")
        print(sql.strip())
        print(store.run_sql(sql))
        print()

    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
