"""
src/syslog/state.py — process-wide singletons shared by service.py (the SSE
monitor) and qa.py (the chat sub-agent tools).

Keeping them here avoids a circular import between service and qa, and gives
us a single place to swap the in-memory implementations for a backed-store
(DuckDB / ClickHouse) when P5 lands.

In a multi-process deployment these would become per-tenant registries
backed by Redis or similar; the API surface stays the same.
"""
from __future__ import annotations

from src.config import get_settings
from src.syslog.causal import CausalGraph, load_causal_graph
from src.syslog.classifier import StreamingClassifier
from src.syslog.ringbuffer import PerNodeRingBuffer
from src.syslog.store import DuckDBSyslogStore, SyslogStore

# Eagerly construct the streaming pieces — they're cheap and idempotent.
classifier: StreamingClassifier = StreamingClassifier(
    sampling_enabled=get_settings().syslog_noise_sampling_enabled,
)
ringbuffer: PerNodeRingBuffer = PerNodeRingBuffer(retention_seconds=3600)

# Heavier singletons load lazily so import succeeds even if CSV / DB
# files are missing (e.g. during tests or before make init).
_causal_graph: CausalGraph | None = None
_syslog_store: SyslogStore | None = None


def causal_graph() -> CausalGraph:
    """Lazy-load and cache the tier1+tier2 causal graph."""
    global _causal_graph
    if _causal_graph is None:
        _causal_graph = load_causal_graph()
    return _causal_graph


def syslog_store() -> SyslogStore:
    """Lazy-init the persistent events store (P5a/P5b).

    Dispatches on settings.syslog_store_backend so the rest of HERALD never
    sees the choice — the SyslogStore Protocol is the only contract.
    """
    global _syslog_store
    if _syslog_store is None:
        settings = get_settings()
        if settings.syslog_store_backend == "clickhouse":
            from src.syslog.store import ClickHouseSyslogStore  # local import: optional dep
            _syslog_store = ClickHouseSyslogStore(
                host=settings.clickhouse_host,
                port=settings.clickhouse_port,
                database=settings.clickhouse_database,
                user=settings.clickhouse_user,
                password=settings.clickhouse_password,
                secure=settings.clickhouse_secure,
                async_insert=settings.clickhouse_async_insert,
                event_ttl_days=settings.clickhouse_event_ttl_days,
                rollup_intervals=settings.clickhouse_rollup_intervals,
                rollup_drop=settings.clickhouse_rollup_drop,
            )
        else:
            _syslog_store = DuckDBSyslogStore(settings.syslog_db_path)
    return _syslog_store
