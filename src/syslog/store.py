"""
src/syslog/store.py — persistent store for classified syslog events.

Two-layer design so we can swap backends without touching the text-to-SQL
chain or the agent tool:

  SyslogStore (Protocol)        — interface
  DuckDBSyslogStore             — dev / small-deployment backend (fine to ~10B rows)
  ClickHouseSyslogStore         — production-scale backend (500B+ rows)

The SQL chain consumes the same Protocol regardless of backend. The
LLM-facing schema_for_prompt() returns dialect-appropriate SQL so the
text-to-SQL model picks the right functions.

Schema shape (identical column names across backends; per-backend types):

  events(ts, node, event_type, severity, subsystem, raw, pid, identifier)
  causal_edges(cause, effect, tier, num_methods, detected_by_*)

The `causal_edges` table is loaded once from the tier1+tier2 CSV at init
so SQL queries can JOIN events against causes without leaving the DB.
"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import text as sql_text

from src.syslog.causal import DEFAULT_CAUSAL_CSV
from src.syslog.classifier import ParsedEvent
from src.tools.sql import JSONSQLDatabase


# ── Interface ─────────────────────────────────────────────────────────────


class SyslogStore(Protocol):
    """Backend-agnostic interface for the persistent syslog events store."""

    dialect: str

    def write_events(self, events: Iterable[ParsedEvent]) -> int: ...
    def run_sql(self, sql: str) -> str: ...
    def schema_for_prompt(self) -> str: ...
    def event_count(self) -> int: ...
    def record_true_counts(self, bucket_ts: datetime, counts: dict[str, int]) -> None: ...
    def counts_since(self, cutoff: datetime) -> dict[str, int]: ...
    def bucketed_counts(
        self, cutoff: datetime, bucket_seconds: int, event_types: list[str],
    ) -> dict[str, list[int]]: ...
    def close(self) -> None: ...


# ── DuckDB implementation ─────────────────────────────────────────────────


_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    ts          TIMESTAMP    NOT NULL,
    node        VARCHAR      NOT NULL,
    event_type  VARCHAR,
    severity    VARCHAR,
    subsystem   VARCHAR,
    raw         VARCHAR,
    pid         INTEGER,
    identifier  VARCHAR
)
"""

_EVENTS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_events_ts        ON events(ts)",
    "CREATE INDEX IF NOT EXISTS idx_events_node_ts   ON events(node, ts)",
    "CREATE INDEX IF NOT EXISTS idx_events_type      ON events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_events_severity  ON events(severity)",
]

# True per-type occurrence counts, independent of classifier.py's noise
# sampling — a type sampled at 10% still gets its full count recorded
# here, just not 90% of its raw rows in `events`. Without this table,
# counts_since()/bucketed_counts() querying `events` directly would
# silently under-report volume for any sampled noise type (see
# ClassifierStats.counts_by_type, which already tracks the true count
# in-memory, but only for the current process's lifetime — this table is
# that same signal, made durable and queryable across restarts).
# bucket_ts is truncated to the minute: fine enough for the 5s-poll UI,
# coarse enough to keep this table small at high event rates.
_TRUE_COUNTS_DDL = """
CREATE TABLE IF NOT EXISTS event_true_counts (
    bucket_ts   TIMESTAMP    NOT NULL,
    event_type  VARCHAR      NOT NULL,
    n           BIGINT       NOT NULL,
    PRIMARY KEY (bucket_ts, event_type)
)
"""

_CAUSAL_DDL = """
CREATE TABLE IF NOT EXISTS causal_edges (
    cause                       VARCHAR NOT NULL,
    effect                      VARCHAR NOT NULL,
    tier                        VARCHAR,
    num_methods                 INTEGER,
    detected_by_transformer     BOOLEAN,
    detected_by_pcmci_plus      BOOLEAN,
    detected_by_transfer_entropy BOOLEAN
)
"""


SCHEMA_PROMPT = """\
-- HERALD syslog events store (DuckDB)
-- One row per classified log message. event_type is one of the 87 taxonomy
-- labels, or NULL for unmatched residuals.

CREATE TABLE events (
    ts          TIMESTAMP   NOT NULL,    -- log timestamp (UTC)
    node        VARCHAR     NOT NULL,    -- compute node id (e.g. 'frontier-0042')
    event_type  VARCHAR,                 -- 87-event taxonomy label, NULL for residual
    severity    VARCHAR,                 -- 'critical' | 'error' | 'warning' | 'info' | 'residual'
    subsystem   VARCHAR,                 -- prefix of event_type (NET/GPU/HW/FS/SYS/SVC/APP/SEC/STO/CTX)
    raw         VARCHAR,                 -- original log message
    pid         INTEGER,
    identifier  VARCHAR
);

-- Causal edges from the SC paper's triangulation, plus operator-curated
-- Manual edges (P6+). The `tier` column takes one of three values:
--   'Tier 1'  : all three statistical methods agreed (strongest evidence)
--   'Tier 2'  : 2 of 3 methods agreed
--   'Manual'  : operator-curated (often LLM-suggested then operator-approved);
--              NOT statistically validated. detected_by_* are all FALSE
--              and num_methods = 0 for Manual edges.
-- To list Manual-tier edges: SELECT ... FROM causal_edges WHERE tier = 'Manual'.
CREATE TABLE causal_edges (
    cause                       VARCHAR NOT NULL,
    effect                      VARCHAR NOT NULL,
    tier                        VARCHAR,   -- 'Tier 1' | 'Tier 2' | 'Manual'
    num_methods                 INTEGER,
    detected_by_transformer     BOOLEAN,
    detected_by_pcmci_plus      BOOLEAN,
    detected_by_transfer_entropy BOOLEAN
);
"""


class DuckDBSyslogStore:
    """File-backed DuckDB store. Single-writer process model; multiple
    concurrent readers are fine via DuckDB's per-statement locking.
    """

    dialect: str = "duckdb"

    def __init__(
        self,
        db_path: str | Path,
        *,
        causal_csv: str | Path | None = None,
        max_result_length: int = 1000,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine: Engine = create_engine(f"duckdb:///{self.db_path}")
        self._json_db = JSONSQLDatabase(
            self._engine, max_result_length=max_result_length, max_string_length=400,
        )
        self._init_schema()
        self._load_causal_edges(Path(
            causal_csv or os.environ.get("HERALD_CAUSAL_CSV", DEFAULT_CAUSAL_CSV)
        ))

    # ── Lifecycle ─────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(sql_text(_EVENTS_DDL))
            for ddl in _EVENTS_INDEXES:
                conn.execute(sql_text(ddl))
            conn.execute(sql_text(_TRUE_COUNTS_DDL))
            conn.execute(sql_text(_CAUSAL_DDL))

    def _load_causal_edges(self, csv_path: Path) -> None:
        """Populate causal_edges from the tier1+tier2 CSV if empty, then
        refresh tier='Manual' edges from EXTENSION_CAUSAL_EDGES on every
        init (so JSONL changes propagate at the next API restart).
        """
        with self._engine.begin() as conn:
            existing = conn.execute(sql_text("SELECT COUNT(*) FROM causal_edges")).scalar()
            csv_loaded = bool(existing and existing > 0)
            if not csv_loaded and csv_path.exists():
                with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                    reader = csv.DictReader(f)
                    rows = []
                    for r in reader:
                        rows.append({
                            "cause": r["cause_event"].strip(),
                            "effect": r["effect_event"].strip(),
                            "tier": (r.get("tier") or "").strip() or "Tier 2",
                            "num_methods": int(r.get("num_methods") or 0),
                            "detected_by_transformer":      _as_bool(r.get("detected_by_transformer")),
                            "detected_by_pcmci_plus":       _as_bool(r.get("detected_by_pcmci_plus")),
                            "detected_by_transfer_entropy": _as_bool(r.get("detected_by_transfer_entropy")),
                        })
                if rows:
                    conn.execute(
                        sql_text(
                            "INSERT INTO causal_edges (cause, effect, tier, num_methods, "
                            "detected_by_transformer, detected_by_pcmci_plus, "
                            "detected_by_transfer_entropy) "
                            "VALUES (:cause, :effect, :tier, :num_methods, "
                            ":detected_by_transformer, :detected_by_pcmci_plus, "
                            ":detected_by_transfer_entropy)"
                        ),
                        rows,
                    )

            # P6+ manual edges: ALWAYS refresh from the extension JSONL so
            # changes are picked up by an API restart. Tier="Manual" rows
            # are the source-of-truth; statistical Tier-1/Tier-2 stays put.
            self._refresh_manual_edges(conn)

    def _refresh_manual_edges(self, conn) -> None:
        try:
            from src.syslog.patterns_extension import EXTENSION_CAUSAL_EDGES
        except ImportError:
            return
        conn.execute(sql_text("DELETE FROM causal_edges WHERE tier = 'Manual'"))
        if not EXTENSION_CAUSAL_EDGES:
            return
        # Use a transient set to dedupe against whatever's already loaded +
        # within the manual batch itself, mirroring the in-memory walker's
        # rule (causal.py:256, which dedupes against the full loaded edge
        # set regardless of tier value). `tier != 'Manual'`, not a
        # hardcoded ('Tier 1', 'Tier 2') allowlist: that version silently
        # matches nothing whenever the loaded tier values are anything
        # else (e.g. currently 'Placeholder'), defeating this
        # dedup/cycle-guard without erroring.
        existing = {
            (row[0], row[1])
            for row in conn.execute(sql_text(
                "SELECT cause, effect FROM causal_edges WHERE tier != 'Manual'"
            )).fetchall()
        }
        seen: set[tuple[str, str]] = set()
        rows: list[dict] = []
        for me in EXTENSION_CAUSAL_EDGES:
            pair = (me["cause"], me["effect"])
            if pair in existing or pair in seen:
                continue
            if (me["effect"], me["cause"]) in existing:
                continue   # cycle with a statistical edge — skip
            rows.append({
                "cause": me["cause"], "effect": me["effect"],
                "tier": "Manual", "num_methods": 0,
                "detected_by_transformer": False,
                "detected_by_pcmci_plus": False,
                "detected_by_transfer_entropy": False,
            })
            seen.add(pair)
        if rows:
            conn.execute(
                sql_text(
                    "INSERT INTO causal_edges (cause, effect, tier, num_methods, "
                    "detected_by_transformer, detected_by_pcmci_plus, "
                    "detected_by_transfer_entropy) "
                    "VALUES (:cause, :effect, :tier, :num_methods, "
                    ":detected_by_transformer, :detected_by_pcmci_plus, "
                    ":detected_by_transfer_entropy)"
                ),
                rows,
            )

    def close(self) -> None:
        self._engine.dispose()

    # ── Writes ────────────────────────────────────────────────────────

    def write_events(self, events: Iterable[ParsedEvent]) -> int:
        payload = [
            {
                "ts": ev.ts,
                "node": ev.node,
                "event_type": ev.event_type,
                "severity": ev.severity,
                "subsystem": ev.subsystem,
                "raw": ev.raw,
                "pid": ev.pid,
                "identifier": ev.identifier,
            }
            for ev in events
        ]
        if not payload:
            return 0
        with self._engine.begin() as conn:
            conn.execute(
                sql_text(
                    "INSERT INTO events (ts, node, event_type, severity, subsystem, "
                    "raw, pid, identifier) "
                    "VALUES (:ts, :node, :event_type, :severity, :subsystem, "
                    ":raw, :pid, :identifier)"
                ),
                payload,
            )
        return len(payload)

    # ── Reads ─────────────────────────────────────────────────────────

    def run_sql(self, sql: str) -> str:
        """Run a SQL query and return JSON rows or an error string."""
        return self._json_db.run(sql)

    def event_count(self) -> int:
        with self._engine.connect() as conn:
            return int(conn.execute(sql_text("SELECT COUNT(*) FROM events")).scalar() or 0)

    def record_true_counts(self, bucket_ts: datetime, counts: dict[str, int]) -> None:
        """Accumulate true per-type occurrence counts for one bucket —
        called with every type classify() saw, INCLUDING ones sampled out
        of `events` by classifier.py's noise dropping. Upserts (adds to
        any existing count for this bucket+type) rather than overwriting,
        since callers flush partial deltas repeatedly rather than one
        final total per bucket."""
        if not counts:
            return
        with self._engine.begin() as conn:
            conn.execute(
                sql_text(
                    "INSERT INTO event_true_counts (bucket_ts, event_type, n) "
                    "VALUES (:bucket_ts, :event_type, :n) "
                    "ON CONFLICT (bucket_ts, event_type) DO UPDATE SET n = event_true_counts.n + excluded.n"
                ),
                [{"bucket_ts": bucket_ts, "event_type": et, "n": n} for et, n in counts.items()],
            )

    def counts_since(self, cutoff: datetime) -> dict[str, int]:
        """Per-event_type TRUE counts at or after `cutoff`, from
        event_true_counts — not `events`, which only holds whatever
        survived classifier.py's noise sampling. Using `events` here would
        silently under-report volume for sampled types (e.g. NET_CXI_RAW_DATA
        kept at 10%) by up to 10-20x. Relies on the table's PK (bucket_ts,
        event_type); cheap even at large volumes."""
        with self._engine.connect() as conn:
            rows = conn.execute(
                sql_text(
                    "SELECT event_type, SUM(n) AS n FROM event_true_counts "
                    "WHERE bucket_ts >= :cutoff GROUP BY event_type ORDER BY n DESC"
                ),
                {"cutoff": cutoff},
            ).fetchall()
        return {(r[0] or "(residual)"): int(r[1]) for r in rows}

    def bucketed_counts(
        self, cutoff: datetime, bucket_seconds: int, event_types: list[str],
    ) -> dict[str, list[int]]:
        """Per-type TRUE counts (see counts_since) in fixed-width time
        buckets from `cutoff` to now — powers the stats-strip sparklines.
        Restricted to the caller's already-chosen `event_types` (e.g. the
        current top-N from counts_since) rather than the whole taxonomy,
        so this stays a small query regardless of how many distinct types
        exist. Sums event_true_counts' own minute-granularity rows into
        the caller's wider bucket_seconds width (SUM(n), not COUNT(*) —
        each row already IS a count, not one row per event)."""
        out: dict[str, list[int]] = {et: [] for et in event_types}
        if not event_types:
            return out
        now = datetime.now(timezone.utc)
        n_buckets = max(1, int((now - cutoff).total_seconds() // bucket_seconds) + 1)
        for et in event_types:
            out[et] = [0] * n_buckets
        placeholders = ", ".join(f":t{i}" for i in range(len(event_types)))
        params: dict[str, Any] = {"cutoff": cutoff, "bucket_seconds": bucket_seconds}
        params.update({f"t{i}": et for i, et in enumerate(event_types)})
        with self._engine.connect() as conn:
            rows = conn.execute(
                sql_text(
                    # Difference computed entirely inside DuckDB, between
                    # bucket_ts and the bound :cutoff param — NOT
                    # EXTRACT(EPOCH FROM bucket_ts) minus a Python-computed
                    # cutoff.timestamp(). A tz-aware Python datetime bound
                    # against a naive TIMESTAMP column gets silently
                    # converted to the session's LOCAL time on insert/bind
                    # (confirmed directly: stored value was 4h off real UTC
                    # on this machine's EDT offset). EXTRACT(EPOCH FROM ...)
                    # then treats that local-shifted value as UTC, so mixing
                    # it with a real Python UTC epoch produced a constant
                    # offset large enough to push every bucket index out of
                    # range — bucketed_counts returned all-zero rows despite
                    # counts_since (a plain >= comparison, unaffected by this)
                    # correctly showing thousands of events. Subtracting two
                    # values that both went through the same conversion
                    # cancels the offset regardless of what it is.
                    "SELECT event_type, "
                    "CAST(EXTRACT(EPOCH FROM (bucket_ts - CAST(:cutoff AS TIMESTAMP))) / :bucket_seconds AS INTEGER) AS bucket, "
                    "SUM(n) AS n FROM event_true_counts "
                    f"WHERE bucket_ts >= :cutoff AND event_type IN ({placeholders}) "
                    "GROUP BY event_type, bucket"
                ),
                params,
            ).fetchall()
        for et, bucket, n in rows:
            if et in out and 0 <= bucket < n_buckets:
                out[et][bucket] = int(n)
        return out

    def schema_for_prompt(self) -> str:
        return SCHEMA_PROMPT


def _as_bool(s: str | None) -> bool:
    return s is not None and str(s).strip().lower() in ("true", "1", "t", "yes")


# ── ClickHouse implementation ─────────────────────────────────────────────
#
# Production-scale backend for the SC paper-scale corpus (18.4 B events
# today, headroom to 500 B+). Designed against clickhouse-connect's HTTP
# client so it works against single-node, replicated, or cloud clusters
# without code changes.
#
# Schema choices (per-column rationale):
#   - PARTITION BY toDate(ts)              one part per day → cheap retention drops
#   - ORDER BY (node, event_type, ts)      node-scoped & type-scoped scans skip
#                                          most parts; ts comes last so range
#                                          queries on a single (node,type) are O(log)
#   - LowCardinality(String) on labels     dictionary-encoded; saves ~10x on
#                                          repeating subsystem / severity strings
#   - CODEC(Delta, ZSTD) on ts             monotonic timestamps compress ~20x
#   - CODEC(ZSTD) on raw                   text logs compress 5-10x
#
# Production knobs we intentionally do NOT enable here (leave to P5c):
#   - TTL ts + INTERVAL N DAY DELETE        retention policy
#   - Buffer table engine in front          for sub-millisecond INSERT latency
#   - MATERIALIZED VIEW for 5s rollups      keeps OLAP queries fast at 500B
#   - Async_insert + Replicated engines     HA / write throughput

_CH_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    ts          DateTime              CODEC(Delta, ZSTD),
    node        LowCardinality(String),
    event_type  LowCardinality(String),
    severity    LowCardinality(String),
    subsystem   LowCardinality(String),
    raw         String                CODEC(ZSTD),
    pid         Nullable(Int32),
    identifier  LowCardinality(Nullable(String))
)
ENGINE = MergeTree
PARTITION BY toDate(ts)
ORDER BY (node, event_type, ts)
SETTINGS index_granularity = 8192
"""

_CH_TRUE_COUNTS_DDL = """
CREATE TABLE IF NOT EXISTS event_true_counts (
    bucket_ts   DateTime              CODEC(Delta, ZSTD),
    event_type  LowCardinality(String),
    n           UInt64
)
ENGINE = SummingMergeTree(n)
ORDER BY (event_type, bucket_ts)
"""

_CH_CAUSAL_DDL = """
CREATE TABLE IF NOT EXISTS causal_edges (
    cause                        LowCardinality(String),
    effect                       LowCardinality(String),
    tier                         LowCardinality(String),
    num_methods                  UInt8,
    detected_by_transformer      UInt8,
    detected_by_pcmci_plus       UInt8,
    detected_by_transfer_entropy UInt8
)
ENGINE = MergeTree
ORDER BY (effect, cause)
"""


# Materialized rollups (P5c). SummingMergeTree pre-aggregates count() by
# (node, event_type, ts_bucket); aggregate queries skip raw `events`
# entirely. Each MV is fed automatically by INSERTs to `events` — no
# code change to the writer.
#
# Default windows (5s/1min/10min) mirror the SC paper's transfer-entropy
# analyses. Override via settings.clickhouse_rollup_intervals.

_UNIT_SUFFIX = {"SECOND": "s", "MINUTE": "min", "HOUR": "hour", "DAY": "day"}
_INTERVAL_RE = re.compile(r"^\s*(\d+)\s+(SECOND|MINUTE|HOUR|DAY)S?\s*$", re.IGNORECASE)


def _parse_interval(spec: str) -> tuple[int, str, str]:
    """Parse '5 SECOND' -> (5, 'SECOND', 'events_rollup_5s').

    Returns (n, ClickHouse unit name, table name suffix).
    Raises ValueError on malformed input.
    """
    m = _INTERVAL_RE.match(spec)
    if not m:
        raise ValueError(
            f"Invalid CH rollup interval {spec!r}. "
            f"Expected '<n> SECOND|MINUTE|HOUR|DAY' (e.g. '5 SECOND', '1 MINUTE')."
        )
    n = int(m.group(1))
    unit = m.group(2).upper()
    suffix = _UNIT_SUFFIX[unit]
    return n, unit, f"events_rollup_{n}{suffix}"


def _rollup_table_ddl(table: str) -> str:
    return f"""
    CREATE TABLE IF NOT EXISTS {table} (
        ts_bucket   DateTime,
        node        LowCardinality(String),
        event_type  LowCardinality(String),
        n           UInt64
    )
    ENGINE = SummingMergeTree
    PARTITION BY toDate(ts_bucket)
    ORDER BY (node, event_type, ts_bucket)
    """


def _rollup_mv_ddl(table: str, n: int, unit: str) -> str:
    return f"""
    CREATE MATERIALIZED VIEW IF NOT EXISTS {table}_mv TO {table} AS
    SELECT
        toStartOfInterval(ts, INTERVAL {n} {unit}) AS ts_bucket,
        node,
        event_type,
        count() AS n
    FROM events
    GROUP BY ts_bucket, node, event_type
    """


CH_SCHEMA_PROMPT_BASE = """\
-- HERALD syslog events store (ClickHouse)
-- One row per classified log message. event_type is one of the 87 taxonomy
-- labels, or empty string for unmatched residuals (LowCardinality(String)
-- cannot be NULL on a sort-key column).

CREATE TABLE events (
    ts          DateTime,
    node        LowCardinality(String),
    event_type  LowCardinality(String),
    severity    LowCardinality(String),      -- 'critical' | 'error' | 'warning' | 'info' | 'residual'
    subsystem   LowCardinality(String),      -- NET / GPU / HW / FS / SYS / SVC / APP / SEC / STO / CTX
    raw         String,
    pid         Nullable(Int32),
    identifier  LowCardinality(Nullable(String))
) ENGINE = MergeTree
  PARTITION BY toDate(ts)
  ORDER BY (node, event_type, ts);

-- Causal edges from the SC paper's triangulation, plus operator-curated
-- Manual edges (P6+). The `tier` column takes one of three values:
--   'Tier 1'  : all three statistical methods agreed (strongest evidence)
--   'Tier 2'  : 2 of 3 methods agreed
--   'Manual'  : operator-curated (often LLM-suggested then operator-approved);
--              NOT statistically validated. detected_by_* are all 0 and
--              num_methods = 0 for Manual edges.
-- To list Manual-tier edges: SELECT ... FROM causal_edges WHERE tier = 'Manual'.
CREATE TABLE causal_edges (
    cause                        LowCardinality(String),
    effect                       LowCardinality(String),
    tier                         LowCardinality(String),    -- 'Tier 1' | 'Tier 2' | 'Manual'
    num_methods                  UInt8,
    detected_by_transformer      UInt8,    -- 1 = true, 0 = false
    detected_by_pcmci_plus       UInt8,
    detected_by_transfer_entropy UInt8
) ENGINE = MergeTree
  ORDER BY (effect, cause);
"""

CH_SCHEMA_PROMPT_ROLLUP_USAGE = """\

-- Pre-aggregated rollups, auto-populated from `events` via materialized
-- views. Use these instead of raw `events` for COUNT / aggregate questions
-- over time — they're orders of magnitude smaller. Always SELECT sum(n),
-- never bare n — SummingMergeTree may not have merged identical keys yet.
-- Use raw `events` when you need: raw text, pid, identifier, severity,
-- sub-second timestamps, or to JOIN causes within a time window
-- (cascade detection).
--
-- All rollups share the schema:
--   CREATE TABLE events_rollup_<suffix> (
--       ts_bucket DateTime, node LowCardinality(String),
--       event_type LowCardinality(String), n UInt64
--   ) ENGINE = SummingMergeTree
--     ORDER BY (node, event_type, ts_bucket);
"""

CH_SCHEMA_PROMPT_TAIL = """\

-- ClickHouse query tips:
--   - Time: now(), today(), now() - INTERVAL 1 HOUR, toStartOfHour(ts),
--     toStartOfInterval(ts, INTERVAL 5 SECOND), toStartOfDay(ts)
--   - Cardinality-aware aggregations: uniq(node), uniqExact(event_type)
--   - For nearest-time correlations consider ASOF JOIN

-- Example rollup query (hourly histogram of NET_CXI_TIMEOUT, last 24h):
--   SELECT toStartOfHour(ts_bucket) AS hour, sum(n) AS events
--   FROM <rollup_table>
--   WHERE event_type = 'NET_CXI_TIMEOUT'
--     AND ts_bucket >= now() - INTERVAL 24 HOUR
--   GROUP BY hour
--   ORDER BY hour;
"""


# Back-compat alias for the old constant name (still used in tests).
CH_SCHEMA_PROMPT = CH_SCHEMA_PROMPT_BASE + CH_SCHEMA_PROMPT_ROLLUP_USAGE + CH_SCHEMA_PROMPT_TAIL


class ClickHouseSyslogStore:
    """ClickHouse-backed implementation of SyslogStore.

    Uses clickhouse-connect's HTTP client (port 8123 by default). The same
    code works against ClickHouse single-node, replicated clusters, and
    ClickHouse Cloud — only the connection params change.
    """

    dialect: str = "clickhouse"

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 8123,
        database: str = "herald_syslog",
        user: str = "default",
        password: str = "",
        secure: bool = False,
        async_insert: bool = True,
        event_ttl_days: int = 0,
        rollup_intervals: list[str] | None = None,
        rollup_drop: list[str] | None = None,
        causal_csv: str | Path | None = None,
        max_result_length: int = 1000,
    ):
        # Validate interval strings up front so a malformed entry fails at
        # init time, not at first INSERT.
        self._rollup_intervals = list(
            rollup_intervals if rollup_intervals is not None
            else ["5 SECOND", "1 MINUTE", "10 MINUTE"]
        )
        self._rollup_drop = list(rollup_drop or [])
        for spec in self._rollup_intervals + self._rollup_drop:
            _parse_interval(spec)  # raises ValueError if malformed

        # Local import so DuckDB-only deployments don't pay for the dep.
        try:
            import clickhouse_connect
        except ImportError as exc:
            raise ImportError(
                "ClickHouseSyslogStore requires 'clickhouse-connect'. "
                "Install with `pip install clickhouse-connect`."
            ) from exc

        # Connect to default DB first to issue CREATE DATABASE, then reopen.
        bootstrap = clickhouse_connect.get_client(
            host=host, port=port, username=user, password=password, secure=secure,
        )
        bootstrap.command(f"CREATE DATABASE IF NOT EXISTS {database}")
        bootstrap.close()

        self._client = clickhouse_connect.get_client(
            host=host, port=port, username=user, password=password,
            database=database, secure=secure,
        )
        self._database = database
        self.max_result_length = max_result_length
        self.max_string_length = 400
        # P5c: server-side INSERT batching. Fire-and-forget at our event
        # rates is fine — the live stream and chat tools don't require
        # read-after-write consistency on the persistent store.
        self._insert_settings: dict[str, Any] = (
            {"async_insert": 1, "wait_for_async_insert": 0} if async_insert else {}
        )

        self._init_schema()
        if event_ttl_days > 0:
            # Idempotent: re-applying the same TTL is a no-op in CH.
            self._client.command(
                f"ALTER TABLE events MODIFY TTL ts + INTERVAL {int(event_ttl_days)} DAY DELETE"
            )
        self._load_causal_edges(Path(
            causal_csv or os.environ.get("HERALD_CAUSAL_CSV", DEFAULT_CAUSAL_CSV)
        ))

    # ── Lifecycle ─────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        self._client.command(_CH_EVENTS_DDL)
        self._client.command(_CH_TRUE_COUNTS_DDL)
        self._client.command(_CH_CAUSAL_DDL)

        # P5c: drop requested rollups first (destructive). DROP IF EXISTS
        # is a no-op when the table is already gone, so leaving stale
        # entries in clickhouse_rollup_drop is safe.
        for spec in self._rollup_drop:
            _, _, table = _parse_interval(spec)
            self._client.command(f"DROP TABLE IF EXISTS {table}_mv")
            self._client.command(f"DROP TABLE IF EXISTS {table}")

        # Create configured rollups (additive, idempotent via IF NOT EXISTS).
        for spec in self._rollup_intervals:
            n, unit, table = _parse_interval(spec)
            self._client.command(_rollup_table_ddl(table))
            self._client.command(_rollup_mv_ddl(table, n, unit))

    def _rollup_summary_for_prompt(self) -> str:
        """Render a one-line summary per configured rollup for the SQL prompt."""
        if not self._rollup_intervals:
            return "-- (No rollup tables configured. Aggregate over raw `events`.)\n"
        lines = ["-- Configured rollup tables (auto-populated from `events`):"]
        for spec in self._rollup_intervals:
            n, unit, table = _parse_interval(spec)
            lines.append(f"--   {table:<26}  bucket = {n} {unit}")
        return "\n".join(lines) + "\n"

    def _load_causal_edges(self, csv_path: Path) -> None:
        existing = self._client.command("SELECT count() FROM causal_edges")
        csv_loaded = bool(existing and int(existing) > 0)
        if not csv_loaded and csv_path.exists():
            with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                rows: list[list[Any]] = []
                for r in reader:
                    rows.append([
                        r["cause_event"].strip(),
                        r["effect_event"].strip(),
                        (r.get("tier") or "").strip() or "Tier 2",
                        int(r.get("num_methods") or 0),
                        1 if _as_bool(r.get("detected_by_transformer")) else 0,
                        1 if _as_bool(r.get("detected_by_pcmci_plus")) else 0,
                        1 if _as_bool(r.get("detected_by_transfer_entropy")) else 0,
                    ])
            if rows:
                self._client.insert(
                    "causal_edges",
                    rows,
                    column_names=[
                        "cause", "effect", "tier", "num_methods",
                        "detected_by_transformer", "detected_by_pcmci_plus",
                        "detected_by_transfer_entropy",
                    ],
                )

        # P6+ manual edges: ALWAYS refresh on every init.
        self._refresh_manual_edges()

    def _refresh_manual_edges(self) -> None:
        try:
            from src.syslog.patterns_extension import EXTENSION_CAUSAL_EDGES
        except ImportError:
            return
        self._client.command("ALTER TABLE causal_edges DELETE WHERE tier = 'Manual'")
        if not EXTENSION_CAUSAL_EDGES:
            return
        # tier != 'Manual', not a hardcoded ('Tier 1', 'Tier 2') allowlist
        # — see the DuckDB version's comment. Also matters here because
        # ClickHouse's ALTER TABLE ... DELETE above is an async mutation;
        # explicitly excluding 'Manual' (rather than assuming the delete
        # already landed) is correct regardless of mutation timing.
        result = self._client.query(
            "SELECT cause, effect FROM causal_edges WHERE tier != 'Manual'"
        )
        existing = {(r[0], r[1]) for r in result.result_rows}
        seen: set[tuple[str, str]] = set()
        rows: list[list[Any]] = []
        for me in EXTENSION_CAUSAL_EDGES:
            pair = (me["cause"], me["effect"])
            if pair in existing or pair in seen:
                continue
            if (me["effect"], me["cause"]) in existing:
                continue
            rows.append([me["cause"], me["effect"], "Manual", 0, 0, 0, 0])
            seen.add(pair)
        if rows:
            self._client.insert(
                "causal_edges", rows,
                column_names=[
                    "cause", "effect", "tier", "num_methods",
                    "detected_by_transformer", "detected_by_pcmci_plus",
                    "detected_by_transfer_entropy",
                ],
            )

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    # ── Writes ────────────────────────────────────────────────────────

    def write_events(self, events: Iterable[ParsedEvent]) -> int:
        rows: list[list[Any]] = []
        for ev in events:
            rows.append([
                ev.ts,
                ev.node,
                ev.event_type or "",
                ev.severity or "",
                ev.subsystem or "",
                ev.raw or "",
                ev.pid,
                ev.identifier,
            ])
        if not rows:
            return 0
        self._client.insert(
            "events", rows,
            column_names=[
                "ts", "node", "event_type", "severity", "subsystem",
                "raw", "pid", "identifier",
            ],
            settings=self._insert_settings,
        )
        return len(rows)

    # ── Reads ─────────────────────────────────────────────────────────

    def run_sql(self, sql: str) -> str:
        """Run a SQL query and return JSON-encoded rows (or an error string)."""
        try:
            result = self._client.query(sql)
        except Exception as e:
            return f"Error: {e}"
        cols = list(result.column_names)
        out: list[dict[str, Any]] = []
        for row in result.result_rows[: self.max_result_length]:
            d: dict[str, Any] = {}
            for col, val in zip(cols, row):
                if isinstance(val, datetime):
                    d[col] = val.isoformat()
                elif isinstance(val, str) and len(val) > self.max_string_length:
                    d[col] = val[: self.max_string_length] + "..."
                else:
                    d[col] = val
            out.append(d)
        return "[\n" + ",\n".join(f"    {json.dumps(o, default=str)}" for o in out) + "\n]"

    def event_count(self) -> int:
        result = self._client.command("SELECT count() FROM events")
        return int(result or 0)

    def record_true_counts(self, bucket_ts: datetime, counts: dict[str, int]) -> None:
        """See DuckDBSyslogStore.record_true_counts — same contract.
        SummingMergeTree sums rows sharing (event_type, bucket_ts) in the
        background; a plain sum() at query time is correct regardless of
        whether that merge has run yet, so this can just INSERT a delta
        row per call rather than needing an explicit upsert."""
        if not counts:
            return
        rows = [[bucket_ts, et, n] for et, n in counts.items()]
        self._client.insert("event_true_counts", rows, column_names=["bucket_ts", "event_type", "n"])

    def counts_since(self, cutoff: datetime) -> dict[str, int]:
        """Per-event_type TRUE counts at or after `cutoff`, from
        event_true_counts. See DuckDBSyslogStore.counts_since for why this
        isn't `events` (which only holds whatever survived classifier.py's
        noise sampling)."""
        result = self._client.query(
            "SELECT event_type, sum(n) AS n FROM event_true_counts "
            "WHERE bucket_ts >= {cutoff:DateTime} GROUP BY event_type ORDER BY n DESC",
            parameters={"cutoff": cutoff},
        )
        return {(row[0] or "(residual)"): int(row[1]) for row in result.result_rows}

    def bucketed_counts(
        self, cutoff: datetime, bucket_seconds: int, event_types: list[str],
    ) -> dict[str, list[int]]:
        """See DuckDBSyslogStore.bucketed_counts — same contract, reading
        event_true_counts (SUM, since each row is already a count) rather
        than `events` (COUNT)."""
        if not event_types:
            return {}
        now = datetime.now(timezone.utc)
        n_buckets = max(1, int((now - cutoff).total_seconds() // bucket_seconds) + 1)
        out: dict[str, list[int]] = {et: [0] * n_buckets for et in event_types}
        result = self._client.query(
            "SELECT event_type, "
            "intDiv(toUInt32(bucket_ts) - toUInt32({cutoff:DateTime}), {bucket_seconds:UInt32}) AS bucket, "
            "sum(n) AS n FROM event_true_counts "
            "WHERE bucket_ts >= {cutoff:DateTime} AND event_type IN {types:Array(String)} "
            "GROUP BY event_type, bucket",
            parameters={"cutoff": cutoff, "bucket_seconds": bucket_seconds, "types": event_types},
        )
        for et, bucket, n in result.result_rows:
            if et in out and 0 <= bucket < n_buckets:
                out[et][bucket] = int(n)
        return out

    def schema_for_prompt(self) -> str:
        # Rebuild on every call: cheap, and lets a config change at runtime
        # (e.g. adding a rollup interval) flow into the LLM prompt without
        # restarting the process.
        return (
            CH_SCHEMA_PROMPT_BASE
            + CH_SCHEMA_PROMPT_ROLLUP_USAGE
            + self._rollup_summary_for_prompt()
            + CH_SCHEMA_PROMPT_TAIL
        )
