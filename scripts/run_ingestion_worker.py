#!/usr/bin/env python3
"""
scripts/run_ingestion_worker.py — standalone Kafka -> classify -> store
ingestion daemon (P8).

Generalizes scripts/smoke_test_sql_clickhouse.py's pattern (drive a source ->
classify -> store.write_events(), entirely outside the HTTP request path)
into a continuous, long-running loop, independent of FastAPI/uvicorn — the
existing /syslog "Connect" flow ties ingestion to one HTTP SSE connection,
which cannot work for an always-on Kafka feed.

Run under a process supervisor (e.g. supervisor, already in requirements.txt)
so a crash restarts cleanly and resumes from the last committed Kafka offset.

    .venv/bin/python scripts/run_ingestion_worker.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.syslog.classifier import StreamingClassifier  # noqa: E402
from src.syslog.ingest_kafka import KafkaRawLogSource  # noqa: E402
from src.syslog import state  # noqa: E402


async def main() -> int:
    settings = get_settings()

    if not settings.kafka_bootstrap_servers or not settings.kafka_topic:
        logger.error(
            "kafka_bootstrap_servers/kafka_topic are not configured "
            "(KAFKA_BOOTSTRAP_SERVERS / KAFKA_TOPIC in .env) — nothing to consume."
        )
        return 1

    # DuckDBSyslogStore is documented as single-writer (store.py) — running
    # this worker against it alongside anything else that also writes to it
    # (the existing inline _sse_stream writer, or another worker process)
    # will hit lock conflicts. ClickHouse is the only backend here built for
    # more than one concurrent writer.
    if settings.syslog_store_backend != "clickhouse":
        logger.error(
            f"syslog_store_backend={settings.syslog_store_backend!r}, but this worker "
            "requires 'clickhouse' — DuckDB is single-writer and will conflict with "
            "a second process writing to it. Set SYSLOG_STORE_BACKEND=clickhouse."
        )
        return 1

    store = state.syslog_store()
    classifier = StreamingClassifier(sampling_enabled=settings.syslog_noise_sampling_enabled)
    source = KafkaRawLogSource(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        topic=settings.kafka_topic,
        group_id=settings.kafka_consumer_group,
        auto_offset_reset=settings.kafka_consumer_auto_offset_reset,
    )

    logger.info(
        f"Starting ingestion worker: topic={settings.kafka_topic!r} "
        f"group={settings.kafka_consumer_group!r} store=clickhouse"
    )
    await source.start()

    buffer: list = []
    last_flush = time.monotonic()
    total_written = 0
    loop = asyncio.get_running_loop()
    try:
        while True:
            batch = await source.poll_batch(timeout_ms=1000, max_records=settings.kafka_batch_size)
            for raw in batch:
                ev = classifier.classify(
                    raw.log_message, node=raw.node, ts=raw.ts, pid=raw.pid, identifier=raw.identifier,
                )
                if ev is not None:
                    buffer.append(ev)

            should_flush = len(buffer) >= settings.kafka_batch_size or (
                buffer and (time.monotonic() - last_flush) >= settings.kafka_batch_timeout_seconds
            )
            if not should_flush:
                continue

            # Persistent write failure -> crash loudly and let a process
            # supervisor restart us. Offsets only commit below, on success,
            # so a restart resumes from the last good batch instead of
            # silently dropping events (unlike _sse_stream's demo-path
            # `except Exception: pass`, which is fine for a best-effort
            # live stream but wrong here).
            #
            # store.write_events() is a synchronous/blocking ClickHouse
            # call — run it off the event loop so it can't stall
            # aiokafka's internal heartbeat/poll tasks, which would risk a
            # consumer-group rebalance (and duplicate re-delivery) under
            # sustained load.
            n = await loop.run_in_executor(None, store.write_events, buffer)
            total_written += n
            await source.commit()
            logger.info(f"wrote {n} events (total {total_written})")
            buffer.clear()
            last_flush = time.monotonic()
    finally:
        await source.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
