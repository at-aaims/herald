"""
src/syslog/ringbuffer.py — per-node, 5-second-binned in-memory event store.

Matches the PCMCI+ binning granularity from the SC paper (5s bins) so that
later causal-walker queries align with the offline causal graph's lag
semantics.

Memory model:
  buffer[node_id] = deque of Bin, each Bin = (bin_start_ts, Counter[event_type], list[ParsedEvent])

  - Counters are kept for ALL event types (cheap).
  - The raw ParsedEvent list inside a bin keeps only NON-noise events
    (configurable via keep_raw_predicate). This bounds memory at scale.

Eviction: bins older than retention_seconds are dropped on every add.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

from src.syslog.classifier import ParsedEvent
from src.syslog.patterns import NOISE_EVENT_TYPES

BIN_SECONDS = 5


@dataclass
class Bin:
    start: datetime
    counts: Counter[str] = field(default_factory=Counter)
    events: list[ParsedEvent] = field(default_factory=list)


def _bin_start(ts: datetime) -> datetime:
    epoch_s = int(ts.timestamp())
    aligned = epoch_s - (epoch_s % BIN_SECONDS)
    return datetime.fromtimestamp(aligned, tz=timezone.utc)


def _default_keep_raw(ev: ParsedEvent) -> bool:
    """Keep all non-noise events; residuals also kept."""
    return ev.event_type not in NOISE_EVENT_TYPES


class PerNodeRingBuffer:
    """
    In-memory 5s-binned event store, partitioned by node.

    Methods that mutate state are not thread-safe; in HERALD's async FastAPI
    runtime everything runs on one event-loop thread, which is sufficient.
    Switch to a lock or a per-node actor if multiple ingest workers are added.
    """

    def __init__(
        self,
        retention_seconds: int = 3600,
        keep_raw_predicate: Callable[[ParsedEvent], bool] = _default_keep_raw,
    ):
        self.retention_seconds = retention_seconds
        self.keep_raw_predicate = keep_raw_predicate
        self._buffers: dict[str, deque[Bin]] = defaultdict(deque)

    def add(self, ev: ParsedEvent) -> None:
        node_buf = self._buffers[ev.node]
        bin_start = _bin_start(ev.ts)

        if node_buf and bin_start < node_buf[-1].start:
            # Timestamp moved backward relative to this node's last-seen
            # bin. A real production source's timestamps are monotonic by
            # construction (Kafka/ES deliver events in arrival order); the
            # only way this happens is a demo replay looping back to the
            # start of its file, or the underlying file changing under a
            # running stream. Treat it as a fresh recording session for
            # this node: the old bins are a previous lap that's about to
            # be re-observed from the top, and keeping them corrupts two
            # things at once — _evict_old's horizon is computed from the
            # latest event's own timestamp, so a backward jump resets it
            # backward too and nothing ages out (bins accumulate forever
            # across loops instead of staying bounded at retention_seconds
            # worth); and events_for_node's linear scan assumes bins are
            # in non-decreasing start order and `break`s as soon as it
            # sees one past its query window, which fires prematurely
            # against out-of-order bins and can miss real matches sitting
            # later in the deque. Clearing keeps the invariant both of
            # those rely on intact.
            node_buf.clear()

        if node_buf and node_buf[-1].start == bin_start:
            cur = node_buf[-1]
        else:
            cur = Bin(start=bin_start)
            node_buf.append(cur)

        if ev.event_type is not None:
            cur.counts[ev.event_type] += 1
        if self.keep_raw_predicate(ev):
            cur.events.append(ev)

        self._evict_old(node_buf, ev.ts)

    def _evict_old(self, node_buf: deque[Bin], now_ts: datetime) -> None:
        horizon = now_ts - timedelta(seconds=self.retention_seconds)
        while node_buf and node_buf[0].start < horizon:
            node_buf.popleft()

    def events_for_node(
        self,
        node: str,
        since: datetime,
        until: datetime,
        of_types: Iterable[str] | None = None,
    ) -> list[ParsedEvent]:
        """Return ParsedEvents in [since, until] for a node, optionally type-filtered."""
        type_set = set(of_types) if of_types is not None else None
        out: list[ParsedEvent] = []
        for b in self._buffers.get(node, ()):
            if b.start + timedelta(seconds=BIN_SECONDS) < since:
                continue
            if b.start > until:
                break
            for ev in b.events:
                if since <= ev.ts <= until and (type_set is None or ev.event_type in type_set):
                    out.append(ev)
        return out

    def counts_window(
        self,
        node: str,
        since: datetime,
        until: datetime,
    ) -> Counter[str]:
        agg: Counter[str] = Counter()
        for b in self._buffers.get(node, ()):
            if b.start + timedelta(seconds=BIN_SECONDS) < since:
                continue
            if b.start > until:
                break
            agg.update(b.counts)
        return agg

    def nodes(self) -> list[str]:
        return list(self._buffers.keys())

    def total_bins(self) -> int:
        return sum(len(d) for d in self._buffers.values())
