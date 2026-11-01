"""
src/syslog/ingest_kafka.py — live Kafka syslog ingestion connector (P8).

"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger

from src.syslog.ingest import RawLog, as_int, as_scalar
from src.syslog.timeutil import parse_timestamp


@dataclass(slots=True)
class KafkaSourceStats:
    messages_consumed: int = 0
    parse_errors: int = 0


class KafkaRawLogSource:
    """Wraps an aiokafka consumer. The caller drives the loop explicitly:

        source = KafkaRawLogSource(bootstrap_servers=..., topic=..., group_id=...)
        await source.start()
        try:
            while True:
                batch = await source.poll_batch(timeout_ms=1000)
                # ... classify + store.write_events(batch) ...
                await source.commit()  # only after a successful write
        finally:
            await source.close()
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        topic: str,
        group_id: str,
        auto_offset_reset: str = "latest",
    ):
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._group_id = group_id
        self._auto_offset_reset = auto_offset_reset
        self._consumer = None  # type: ignore[var-annotated]
        self.stats = KafkaSourceStats()

    async def start(self) -> None:
        # Lazy import: aiokafka is an optional dependency, only needed when
        # the Kafka connector is actually configured (matches the
        # clickhouse_connect lazy-import convention in store.py/state.py).
        from aiokafka import AIOKafkaConsumer

        self._consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset=self._auto_offset_reset,
            enable_auto_commit=False,  # hard requirement — see module docstring
        )
        await self._consumer.start()

    async def poll_batch(self, *, timeout_ms: int = 1000, max_records: int = 500) -> list[RawLog]:
        """Returns up to max_records RawLog objects, waiting up to timeout_ms
        for at least one. Empty list on timeout (not an error — the caller's
        loop should just try again; this is what gives bursty Kafka traffic
        a natural pause instead of busy-looping)."""
        assert self._consumer is not None, "call start() first"
        result = await self._consumer.getmany(timeout_ms=timeout_ms, max_records=max_records)
        batch: list[RawLog] = []
        for _tp, messages in result.items():
            for msg in messages:
                self.stats.messages_consumed += 1
                raw = self._parse_message(msg.value)
                if raw is not None:
                    batch.append(raw)
        return batch

    def _parse_message(self, value: bytes) -> RawLog | None:
        """Never raises — a malformed message is counted and skipped, not
        allowed to crash the caller's loop. See module docstring."""
        try:
            data = json.loads(value)
            if not isinstance(data, dict):
                self.stats.parse_errors += 1
                return None

            message = data.get("message")
            if message is None:
                message = data.get("log_message")
            if not message or not isinstance(message, str):
                self.stats.parse_errors += 1
                return None

            ts_raw = data.get("ts")
            if ts_raw is None:
                ts_raw = data.get("timestamp")
            # "now" is the least-wrong fallback for a genuinely missing or
            # unparseable timestamp (not the same as an explicit epoch-0,
            # which parse_timestamp handles as real input) — this way the
            # message still gets ingested rather than dropped.
            ts = parse_timestamp(ts_raw, default=datetime.now(timezone.utc))

            node = as_scalar(data.get("node")) or as_scalar(data.get("host")) or "unknown"

            return RawLog(
                ts=ts,
                node=str(node),
                log_message=message,
                pid=as_int(data.get("pid")),
                identifier=as_scalar(data.get("identifier")),
            )
        except Exception as exc:
            # Defense in depth: no matter what goes wrong parsing one
            # message, the worker loop must survive it. See module
            # docstring — this is what prevents an unbounded crash-restart
            # loop on a poison-pill message.
            logger.warning(f"Kafka message parse failed, skipping: {exc}")
            self.stats.parse_errors += 1
            return None

    async def commit(self) -> None:
        """ """
        assert self._consumer is not None, "call start() first"
        await self._consumer.commit()

    async def close(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
