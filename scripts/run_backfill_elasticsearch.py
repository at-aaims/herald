#!/usr/bin/env python3
"""
scripts/run_backfill_elasticsearch.py — standalone Elasticsearch -> classify
-> store backfill runner (P8).

Mirrors scripts/run_ingestion_worker.py's structure, but for a bounded batch
job rather than a continuous stream: ElasticsearchBackfillSource.fetch_batch()
returns an empty list once the index is exhausted, at which point this script
exits 0 (there is nothing to "keep polling" the way Kafka's tail is unbounded)
rather than looping forever.

Safe to re-run: progress resumes from the on-disk checkpoint
(elasticsearch_backfill_checkpoint_path), which is only advanced after a
successful store.write_events() for the batch that produced it — same
commit-after-persist invariant as the Kafka worker, for the same reason.

    .venv/bin/python scripts/run_backfill_elasticsearch.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.syslog.classifier import StreamingClassifier  # noqa: E402
from src.syslog.ingest_elasticsearch import ElasticsearchBackfillSource  # noqa: E402
from src.syslog import state  # noqa: E402


async def main() -> int:
    settings = get_settings()

    if not settings.elasticsearch_hosts or not settings.elasticsearch_index:
        logger.error(
            "elasticsearch_hosts/elasticsearch_index are not configured "
            "(ELASTICSEARCH_HOSTS / ELASTICSEARCH_INDEX in .env) — nothing to backfill."
        )
        return 1

    # Same rationale as run_ingestion_worker.py: DuckDBSyslogStore is
    # single-writer, so backfilling into it alongside any other live writer
    # (a Kafka worker, the demo SSE stream) risks lock conflicts.
    if settings.syslog_store_backend != "clickhouse":
        logger.error(
            f"syslog_store_backend={settings.syslog_store_backend!r}, but this backfill "
            "requires 'clickhouse' — DuckDB is single-writer and will conflict with "
            "a second process writing to it. Set SYSLOG_STORE_BACKEND=clickhouse."
        )
        return 1

    store = state.syslog_store()
    classifier = StreamingClassifier(sampling_enabled=settings.syslog_noise_sampling_enabled)
    source = ElasticsearchBackfillSource(
        hosts=settings.elasticsearch_hosts,
        index=settings.elasticsearch_index,
        field_map=settings.elasticsearch_field_map,
        checkpoint_path=settings.elasticsearch_backfill_checkpoint_path,
    )

    logger.info(f"Starting ES backfill: index={settings.elasticsearch_index!r} store=clickhouse")
    await source.start()

    total_written = 0
    loop = asyncio.get_running_loop()
    try:
        while True:
            batch = await source.fetch_batch(size=settings.elasticsearch_backfill_batch_size)
            if not batch:
                logger.info(f"Backfill complete (total {total_written} written) — index exhausted.")
                return 0

            events = [
                ev
                for raw in batch
                if (ev := classifier.classify(
                    raw.log_message, node=raw.node, ts=raw.ts, pid=raw.pid, identifier=raw.identifier,
                )) is not None
            ]
            if events:
                # Blocking ClickHouse call — off the event loop, same
                # reasoning as run_ingestion_worker.py.
                n = await loop.run_in_executor(None, store.write_events, events)
                total_written += n

            # Only after a successful write — a crash before this point
            # just means the next run re-fetches (and re-writes) this one
            # batch, not a silent gap.
            source.save_checkpoint()
            logger.info(f"wrote {len(events)} events (total {total_written})")
    finally:
        await source.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
