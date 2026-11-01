"""
src/syslog/classifier.py — streaming classifier with noise sampling.

The classifier is stateful only in the sense that it keeps event counters
and a bounded residual queue; the hot path is per-line and side-effect free.

Per the SC paper's hot/cold split:
  - Regex classification on the hot path (this module)
  - Residuals are buffered and handed to the offline LLM (control plane,
    not implemented in P0/P1; see src/syslog/residuals.py — TODO P6)
"""
from __future__ import annotations

import random
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from src.syslog.patterns import (
    CRITICAL_EVENT_TYPES,
    NOISE_EVENT_TYPES,
    classify_log_line,
    severity_for,
    subsystem_for,
)


@dataclass(slots=True)
class ParsedEvent:
    """
    Canonical event record emitted by the classifier.

    `event_type` is None for residuals (unmatched lines). The UI may still
    display residuals; the offline LLM proposer consumes them to grow the
    regex DB.
    """
    ts: datetime
    node: str
    event_type: str | None
    raw: str
    severity: str
    subsystem: str
    pid: int | None = None
    identifier: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


@dataclass
class ClassifierStats:
    total_seen: int = 0
    total_emitted: int = 0
    counts_by_type: Counter[str] = field(default_factory=Counter)
    dropped_by_sampling: Counter[str] = field(default_factory=Counter)
    residual_count: int = 0


# Default sampling rates for noisy classes. 1.0 keeps everything; 0.0 drops all.
# In production at 1B/day these would be aggressive (0.01); for the prototype
# we keep more so the UI has something to show.
DEFAULT_NOISE_SAMPLE_RATE: dict[str, float] = {
    "NET_CXI_RAW_DATA": 0.10,
    "FS_DISK_FULL": 0.20,
    "INFO_NOISE": 0.05,
    "SYS_X11_NOISE": 0.05,
}


class StreamingClassifier:
    """
    Classifies one log record at a time. Sampling is rate-based per noise
    class; critical events always pass through.

    Usage:
        clf = StreamingClassifier()
        ev = clf.classify(raw_message, node="frontier-0042")
        if ev is not None:
            ringbuffer.add(ev)
    """

    def __init__(
        self,
        sample_rates: dict[str, float] | None = None,
        emit_residuals: bool = True,
        residual_queue_max: int = 10_000,
        rng_seed: int | None = None,
        sampling_enabled: bool = False,
    ):
        self.sample_rates = {**DEFAULT_NOISE_SAMPLE_RATE, **(sample_rates or {})}
        self.emit_residuals = emit_residuals
        self.residuals: deque[str] = deque(maxlen=residual_queue_max)
        self.stats = ClassifierStats()
        self._rng = random.Random(rng_seed)
        # Default False: keep every raw message, matching the SC26 paper's
        # frequency-balancing approach (it never discards raw data — see
        # config.py's syslog_noise_sampling_enabled). The true per-type
        # count is tracked via event_true_counts regardless of this flag;
        # this only gates whether raw noise-type message bodies also
        # survive into the store.
        self.sampling_enabled = sampling_enabled

    def classify(
        self,
        log_message: str,
        node: str = "node-0",
        ts: datetime | None = None,
        pid: int | None = None,
        identifier: str | None = None,
    ) -> ParsedEvent | None:
        """
        Returns a ParsedEvent if the line should be surfaced, else None.

        Returns None for:
          - empty lines
          - residuals when emit_residuals=False
          - noise lines lost to sampling
        """
        self.stats.total_seen += 1
        if not log_message:
            return None

        event_type = classify_log_line(log_message)

        if event_type is None:
            self.residuals.append(log_message)
            self.stats.residual_count += 1
            if not self.emit_residuals:
                return None
        else:
            self.stats.counts_by_type[event_type] += 1
            # Noise sampling — opt-in (see __init__), critical types never
            # sampled out even when enabled.
            if self.sampling_enabled and event_type in NOISE_EVENT_TYPES and event_type not in CRITICAL_EVENT_TYPES:
                rate = self.sample_rates.get(event_type, 1.0)
                if rate < 1.0 and self._rng.random() >= rate:
                    self.stats.dropped_by_sampling[event_type] += 1
                    return None

        ev = ParsedEvent(
            ts=ts or datetime.now(timezone.utc),
            node=node,
            event_type=event_type,
            raw=log_message,
            severity=severity_for(event_type),
            subsystem=subsystem_for(event_type),
            pid=pid,
            identifier=identifier,
        )
        self.stats.total_emitted += 1
        return ev

    def stats_snapshot(self) -> dict[str, Any]:
        return {
            "total_seen": self.stats.total_seen,
            "total_emitted": self.stats.total_emitted,
            "residual_count": self.stats.residual_count,
            "residual_queue_len": len(self.residuals),
            "counts_by_type": dict(self.stats.counts_by_type.most_common(30)),
            "dropped_by_sampling": dict(self.stats.dropped_by_sampling),
            "ts": time.time(),
        }
