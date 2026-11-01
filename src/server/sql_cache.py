"""
Side-channel cache for full SQL tool results.

The SQL tool returns a slim slice to the LLM (to keep its context bounded),
but the UI needs the full row set to render charts properly. The tool puts
the full rows in this in-process LRU cache keyed by a per-call UUID and
embeds that token in its JSON return. The frontend then fetches the full
rows via GET /api/sql-result/{token}.

Single-process only — fine for our single-uvicorn deployment. If we ever
scale horizontally, swap to Redis with the same interface.
"""
from collections import OrderedDict
from threading import Lock
from typing import Any

_MAX_ENTRIES = 50  # cap so memory doesn't grow unbounded in long sessions
_CACHE: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
_LOCK = Lock()


def store(token: str, rows: list[dict[str, Any]]) -> None:
    """Insert rows under token, evicting the oldest entry if we're over the cap."""
    with _LOCK:
        _CACHE[token] = rows
        _CACHE.move_to_end(token)
        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.popitem(last=False)


def fetch(token: str) -> list[dict[str, Any]] | None:
    with _LOCK:
        return _CACHE.get(token)
