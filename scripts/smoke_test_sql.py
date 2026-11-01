"""
scripts/smoke_test_sql.py — verify the syslog persistent store + SQL surface.

Two-phase check:

  Phase A (no LLM): ingest the cascade demo JSONL into the store via the
                    same code path as the SSE stream uses, then run a few
                    canonical SQL queries directly against the store.

  Phase B (LLM, optional): if a sql_model client builds successfully, also
                           run a natural-language question through the
                           text-to-SQL chain and print both the generated
                           SQL and the row count.

Phase A is the gate — Phase B is informational.

Usage:
    .venv/bin/python scripts/smoke_test_sql.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.syslog import state  # noqa: E402
from src.syslog.ingest import replay_source  # noqa: E402
from src.syslog.store import DuckDBSyslogStore  # noqa: E402

DEMO = Path(__file__).resolve().parent.parent / ".data" / "syslog_demo.jsonl"


async def phase_a() -> None:
    if not DEMO.exists():
        print(f"ERROR: demo JSONL not found at {DEMO}; run build_demo_cascades.py first")
        sys.exit(2)

    # Use a temp DB file so we don't pollute the dev DB.
    tmp_db = Path(__file__).resolve().parent.parent / ".data" / "syslog_smoke.duckdb"
    if tmp_db.exists():
        tmp_db.unlink()
    store = DuckDBSyslogStore(tmp_db)

    # Drain the demo into the store via the streaming classifier.
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

    print(f"Ingested {n} classified events into {tmp_db.name}")
    print(f"store.event_count() = {store.event_count()}\n")

    queries = [
        ("Event counts by type (top 5)",
         "SELECT event_type, COUNT(*) AS n FROM events GROUP BY event_type ORDER BY n DESC LIMIT 5"),
        ("Per-node event count",
         "SELECT node, COUNT(*) AS n FROM events GROUP BY node ORDER BY n DESC"),
        ("Critical events with their static-graph causes",
         """SELECT e.node, e.ts, e.event_type, ce.cause, ce.tier
            FROM events e
            JOIN causal_edges ce ON ce.effect = e.event_type
            WHERE e.severity = 'critical'
            ORDER BY e.node, e.ts
            LIMIT 10"""),
        ("Cascade detection: causes that fired within 60s before each APP_INFRA_FAIL",
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
    ]
    for label, sql in queries:
        print(f"=== {label} ===")
        print(sql.strip())
        print(store.run_sql(sql))
        print()

    store.close()


async def phase_b() -> None:
    """Best-effort: run one natural-language question through the SQL chain."""
    try:
        from src.models.configured import get_sql_model_client, get_sql_model_name
        from src.syslog.sql_chain import run_syslog_sql_qna
    except Exception as exc:
        print(f"[Phase B skipped] model imports failed: {exc}")
        return

    try:
        client = get_sql_model_client()
        model_name = get_sql_model_name()
    except Exception as exc:
        print(f"[Phase B skipped] sql_model client unavailable: {exc}")
        return

    # Use the production-default store (the one populated by phase A's
    # replay would be in the temp file, so phase B touches the configured
    # store; in a fresh checkout that means 0 rows but the SQL chain still
    # produces valid SQL we can inspect).
    store = state.syslog_store()
    question = "How many events of each event_type did we see in the last hour, top 5?"
    print(f"=== Phase B: NL question ===\n{question}\n")
    result = await run_syslog_sql_qna(
        client=client, model_name=model_name, store=store, question=question,
    )
    print("Generated SQL:")
    print(result.get("query"))
    if result.get("error"):
        print(f"Execution error: {result['error']}")
    else:
        rows = result.get("query_result") or []
        print(f"Rows: {len(rows)}")
        print(json.dumps(rows[:5], indent=2, default=str))


async def main() -> int:
    await phase_a()
    print("─" * 60)
    await phase_b()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
