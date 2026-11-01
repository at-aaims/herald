"""
src/syslog/ingest_elasticsearch.py.

"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from src.syslog.ingest import RawLog, as_int, as_scalar
from src.syslog.timeutil import parse_timestamp

PIT_KEEP_ALIVE = "2m"


def _get_nested(doc: dict, dotted_field: str) -> Any:
    """ES field names are commonly dotted paths into nested objects
    (e.g. 'host.name'), which is exactly what elasticsearch_field_map's
    ECS-following defaults use."""
    value: Any = doc
    for part in dotted_field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


class ElasticsearchBackfillSource:
    """One backfill run over an index, resumable via a checkpoint file:

        source = ElasticsearchBackfillSource(hosts=..., index=..., field_map=...,
                                              checkpoint_path=...)
        await source.start()
        try:
            while True:
                batch = await source.fetch_batch(size=1000)
                if not batch:
                    break
                # ... classify + store.write_events(batch) ...
                source.save_checkpoint()  # only after a successful write
        finally:
            await source.close()
    """

    def __init__(
        self,
        *,
        hosts: str,
        index: str,
        field_map: dict[str, str],
        checkpoint_path: str,
    ):
        self._hosts = [h.strip() for h in hosts.split(",") if h.strip()]
        self._index = index
        self._field_map = field_map
        self._checkpoint_path = Path(checkpoint_path)
        self._client = None  # type: ignore[var-annotated]
        self._pit_id: str | None = None
        self._search_after: list[Any] | None = self._load_checkpoint()

    def _load_checkpoint(self) -> list[Any] | None:
        if not self._checkpoint_path.exists():
            return None
        try:
            data = json.loads(self._checkpoint_path.read_text())
            return data.get("search_after")
        except (json.JSONDecodeError, OSError) as exc:
            # A corrupt/unreadable checkpoint must not silently restart the
            # backfill from the beginning (that would duplicate everything
            # already written) — surface it loudly so a human decides,
            # matching the "crash loud, never silently reprocess" rule
            # applied to ingest_kafka.py's poison-pill handling.
            logger.error(
                f"Elasticsearch checkpoint at {self._checkpoint_path} is unreadable ({exc}) — "
                "refusing to silently restart the backfill from the beginning. "
                "Fix or remove the checkpoint file manually to proceed."
            )
            raise

    def save_checkpoint(self) -> None:
        """Persist the current search_after position. Call ONLY after a
        successful store.write_events() for the batch that produced it —
        same commit-after-persist invariant as ingest_kafka.py's
        KafkaRawLogSource.commit(), for the same reason: a crash before the
        checkpoint is saved just means the next run re-fetches (and
        re-writes) that one batch, not a silent gap.

        Written atomically (temp file + os.replace) so a crash mid-write
        can never leave a half-written, unreadable checkpoint on disk."""
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._checkpoint_path.with_suffix(self._checkpoint_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps({"search_after": self._search_after}))
        os.replace(tmp_path, self._checkpoint_path)

    async def start(self) -> None:
        # Lazy import: elasticsearch is an optional dependency, only needed
        # when the ES connector is actually configured (matches the
        # clickhouse_connect/aiokafka lazy-import convention).
        from elasticsearch import AsyncElasticsearch

        self._client = AsyncElasticsearch(hosts=self._hosts)
        pit = await self._client.open_point_in_time(index=self._index, keep_alive=PIT_KEEP_ALIVE)
        self._pit_id = pit["id"]

    async def fetch_batch(self, *, size: int = 1000) -> list[RawLog]:
        """Returns up to `size` RawLog objects in timestamp order. Empty
        list means the backfill has reached the end of the index."""
        assert self._client is not None, "call start() first"
        ts_field = self._field_map.get("timestamp", "@timestamp")
        resp = await self._client.search(
            size=size,
            pit={"id": self._pit_id, "keep_alive": PIT_KEEP_ALIVE},
            sort=[{ts_field: "asc"}, {"_shard_doc": "asc"}],
            search_after=self._search_after,
        )
        hits = resp["hits"]["hits"]
        if not hits:
            return []
        self._search_after = hits[-1]["sort"]
        # A newer PIT id may be returned per response; keep using the latest.
        self._pit_id = resp.get("pit_id", self._pit_id)

        batch: list[RawLog] = []
        for hit in hits:
            doc = hit["_source"]
            message = as_scalar(_get_nested(doc, self._field_map.get("message", "message")))
            if not message or not isinstance(message, str):
                continue
            node = as_scalar(_get_nested(doc, self._field_map.get("node", "host.name"))) or "unknown"
            batch.append(RawLog(
                ts=parse_timestamp(_get_nested(doc, ts_field), default=datetime.now(timezone.utc)),
                node=str(node),
                log_message=message,
                pid=as_int(_get_nested(doc, self._field_map.get("pid", "process.pid"))),
                identifier=as_scalar(_get_nested(doc, self._field_map.get("identifier", "process.name"))),
            ))
        return batch

    async def close(self) -> None:
        if self._client is not None:
            if self._pit_id:
                try:
                    await self._client.close_point_in_time(id=self._pit_id)
                except Exception:
                    pass  # PIT expires on its own via keep_alive regardless
            await self._client.close()
