"""
src/syslog/timeutil.py — single shared timestamp parser for syslog ingestion.

Previously duplicated (with subtly different failure contracts) across
ingest.py, ingest_kafka.py, and ingest_elasticsearch.py; consolidated here
so a format fix or bug only needs applying once.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_timestamp(value: Any, *, default: datetime | None = None) -> datetime | None:
    """Parse an epoch (int/float, seconds or millis) or ISO8601 (str,
    optionally trailing 'Z') timestamp. Returns `default` for None, empty,
    or unparseable input — never raises.

    `value is None` and `value == 0` are handled distinctly: an explicit
    epoch-0 timestamp is real input and gets parsed normally, not silently
    replaced with `default` (callers should check `is not None` before
    falling back to an alternate field, not use bare `or`, which would
    incorrectly discard a legitimate epoch-0 value).
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e12 else value, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return default
    if isinstance(value, str):
        if not value:
            return default
        try:
            s = value[:-1] + "+00:00" if value.endswith("Z") else value
            return datetime.fromisoformat(s)
        except ValueError:
            return default
    return default
