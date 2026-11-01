#!/usr/bin/env python3
"""
scripts/ingest_rag_corpus.py — build src/rag/chroma_db from a curated subset
of the corpus bundled in src/rag/rag_assets/ (committed to git as plain text
.rst/.pdf files). chroma_db itself is a regenerable build artifact, not
committed — run this once after cloning to get working documentation search.

    .venv/bin/python scripts/ingest_rag_corpus.py

Only DEFAULT_CORPUS auto-ingests on first boot, not every file in
rag_assets/ -- enough to answer demo questions about Frontier itself
without the first-boot embedding cost of the full set (one file alone,
frontier_user_guide.rst, is 7000+ chunks; see src/rag/db.py's batched
encode()). The rest of rag_assets/ is still right there in the checkout
(the backend bind-mounts the whole repo) -- add any of them later via the
Knowledge Base upload panel in /setup without restarting anything.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.ingest_user import ingest_file, list_documents  # noqa: E402

ASSETS = Path(__file__).resolve().parent.parent / "src" / "rag" / "rag_assets"
CORPUS_EXT = {".rst", ".pdf"}

# Demo-ready starter set — enough to answer real questions about Frontier
# (the system HERALD is built for) without waiting on the full 12-file
# corpus's embedding cost on first boot. Everything else in rag_assets/
# stays in the repo, just not auto-ingested; add it later via the Knowledge
# Base upload panel (/setup) whenever you want broader coverage.
DEFAULT_CORPUS = {
    "frontier_user_guide.rst",
    "home_user_guide.rst",
    "Frontier (supercomputer) - Wikipedia.pdf",
    "dtn_user_guide.rst",
    "odo_user_guide.rst",
}


def _looks_like_connectivity_error(exc: Exception) -> bool:
    """True for the class of failure that's the SAME for every document —
    can't reach/verify the embedding model host (TLS-inspecting corporate
    proxy, offline, DNS, etc.) — as opposed to a per-document parsing issue.
    Checked by name, not import, since the actual exception type is deep in
    requests/httpx/huggingface_hub and not worth a hard dependency here."""
    chain = []
    cur: BaseException | None = exc
    while cur is not None:
        chain.append(type(cur).__name__)
        cur = cur.__cause__ or cur.__context__
    text = " ".join(chain) + " " + str(exc)
    return any(s in text for s in (
        "SSLError", "SSLCertVerificationError", "ConnectionError",
        "MaxRetryError", "ConnectTimeout", "NewConnectionError",
    ))


async def main() -> int:
    docs = sorted(
        f for f in ASSETS.iterdir()
        if f.suffix.lower() in CORPUS_EXT and f.name in DEFAULT_CORPUS
    )
    # Skip filenames already in the manifest — makes re-running this script
    # safe after a partial failure (e.g. a mid-corpus network error) instead
    # of either duplicating the completed docs or, worse, being skipped
    # entirely by a caller that only checks "is chroma_db non-empty" (which
    # a partially-ingested corpus already satisfies, masking the gap).
    already = {d["filename"] for d in list_documents()}
    docs = [d for d in docs if d.name not in already]
    total_in_folder = sum(1 for f in ASSETS.iterdir() if f.suffix.lower() in CORPUS_EXT)
    print(f"found {len(docs)} of {len(DEFAULT_CORPUS)} default corpus files in {ASSETS} "
          f"not yet ingested ({len(already)} already in the manifest). "
          f"{total_in_folder - len(DEFAULT_CORPUS)} more files are in that folder but not "
          f"auto-ingested -- add them via the Knowledge Base upload panel.")
    for d in docs:
        try:
            s = await ingest_file(d, original_name=d.name, copy_source=False)
        except Exception as exc:
            if _looks_like_connectivity_error(exc):
                # Every remaining file would fail the identical way (same
                # embedding-model host) — one clear message beats N copies
                # of the same raw traceback, and there's no point retrying.
                print(f"  ERROR {d.name}: {type(exc).__name__}: {exc}")
                print("")
                print("RAG indexing stopped: can't reach the embedding model host.")
                print("This is almost always a network/TLS issue — e.g. a corporate")
                print("proxy that intercepts HTTPS. See deploy/README.md for the fix")
                print("(exporting your proxy's CA cert for the Docker build).")
                remaining = len(docs) - docs.index(d) - 1
                print(f"Stopped after {d.name}; {remaining} file(s) not yet attempted — "
                      "re-run this script once connectivity works.")
                return 1
            print(f"  ERROR {d.name}: {type(exc).__name__}: {exc}")
            continue
        if s.get("error"):
            print(f"  ERROR {d.name}: {s['error']}")
        else:
            print(f"  OK {d.name}: chunks={s.get('chunks')} tables={s.get('tables')} images={s.get('images')}")
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
