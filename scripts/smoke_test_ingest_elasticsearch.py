#!/usr/bin/env python3
"""
scripts/smoke_test_ingest_elasticsearch.py — exercise
ElasticsearchBackfillSource against a real ES index.

Skips gracefully (exit 0) if elasticsearch_hosts/elasticsearch_index aren't
configured, or if the cluster is unreachable — so this can live in CI
without forcing a live ES dependency for every contributor.

    .venv/bin/python scripts/smoke_test_ingest_elasticsearch.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import get_settings  # noqa: E402


async def main() -> int:
    settings = get_settings()
    if not settings.elasticsearch_hosts or not settings.elasticsearch_index:
        print("[SKIP] elasticsearch_hosts/elasticsearch_index not configured")
        return 0

    try:
        from src.syslog.ingest_elasticsearch import ElasticsearchBackfillSource
    except ImportError as exc:
        print(f"[SKIP] elasticsearch client not installed: {exc}")
        return 0

    source = ElasticsearchBackfillSource(
        hosts=settings.elasticsearch_hosts,
        index=settings.elasticsearch_index,
        field_map=settings.elasticsearch_field_map,
        checkpoint_path=settings.elasticsearch_backfill_checkpoint_path,
    )
    try:
        await source.start()
    except Exception as exc:
        print(f"[SKIP] Elasticsearch unreachable: {exc}")
        return 0

    try:
        batch = await source.fetch_batch(size=10)
        print(f"fetched {len(batch)} document(s)")
        for raw in batch[:3]:
            print(f"  node={raw.node!r} ts={raw.ts} message={raw.log_message[:80]!r}")
        return 0
    finally:
        await source.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
