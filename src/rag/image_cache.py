"""
Side-channel cache for RAG image references.

The docs tool can't put image bytes into the LLM context, so it stashes each
relevant image's resolved absolute path under a per-image UUID token and embeds
`/api/rag-image/{token}` URLs in its JSON output. The frontend renders those
URLs; GET /api/rag-image/{token} resolves the token back to the file and streams
it. Because only paths we vetted ever enter the cache, the serve endpoint can't
be used for path traversal.

Single-process in-memory LRU — mirrors src/server/sql_cache.py.
"""
from collections import OrderedDict
from threading import Lock

_MAX_ENTRIES = 500  # images are small refs; keep more around than SQL results
_CACHE: "OrderedDict[str, str]" = OrderedDict()
_LOCK = Lock()


def store(token: str, abspath: str) -> None:
    with _LOCK:
        _CACHE[token] = abspath
        _CACHE.move_to_end(token)
        while len(_CACHE) > _MAX_ENTRIES:
            _CACHE.popitem(last=False)


def fetch(token: str) -> str | None:
    with _LOCK:
        return _CACHE.get(token)
