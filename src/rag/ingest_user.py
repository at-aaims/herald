"""
src/rag/ingest_user.py — ingest user-provided documents/images into the RAG store.

Complements the RST-only batch ingest in db.create_database(). Accepts the
formats operators actually upload — text/markdown/HTML, PDF, DOCX, and standalone
images — parses each into text chunks / tables / images, and embeds them into the
shared ChromaDB collections (text_v1, tables_v1, images_v1) so they're immediately
searchable by the `rag` tool.

Every entry is tagged with metadata `source = <doc_id>` (a per-document UUID), and
each document's original file + any extracted media live under
`{rag_upload_dir}/{doc_id}/`. A manifest.json in the upload dir records what's been
ingested, so documents can be listed and deleted cleanly (drop the doc's rows from
every collection by `source`, then remove its folder).

Two entry points, sharing all logic:
  - ingest_file()  / ingest_folder()  — used by the CLI (`python -m src.rag.ingest_user`)
  - the same functions are called by POST /api/rag/ingest in the HTTP API.
"""
from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from loguru import logger

from src.config import get_settings

# Extension groups. rst/html/pdf/docx are handled by dedicated parsers below.
_TEXT_EXT = {".txt", ".md", ".markdown"}
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

_COLLECTIONS = ("text_v1", "images_v1", "tables_v1")

_manifest_lock = Lock()


# ── Paths & manifest ────────────────────────────────────────────────────────

def _upload_dir() -> Path:
    d = Path(get_settings().rag_upload_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manifest_path() -> Path:
    return _upload_dir() / "manifest.json"


def _read_manifest() -> dict[str, Any]:
    p = _manifest_path()
    if not p.exists():
        return {"documents": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        data.setdefault("documents", {})
        return data
    except Exception:
        logger.warning("RAG manifest unreadable; starting fresh")
        return {"documents": {}}


def _write_manifest(m: dict[str, Any]) -> None:
    _manifest_path().write_text(json.dumps(m, indent=2), encoding="utf-8")


def _copy_into(src: Path, media_dir: Path) -> str:
    """Copy an image referenced by a doc into the doc's media dir; return abspath."""
    media_dir.mkdir(parents=True, exist_ok=True)
    dst = media_dir / f"{uuid.uuid4().hex}{src.suffix.lower()}"
    shutil.copyfile(src, dst)
    return str(dst)


# ── Per-format parsers: each returns (text_blocks, tables, image_paths) ───────

def _parse_text(path: Path, media_dir: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    # Markdown image refs ![alt](path) — include local images that exist.
    images: list[str] = []
    if path.suffix.lower() in {".md", ".markdown"}:
        import re
        for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", text):
            ref = m.group(1).split()[0].strip()
            if ref.startswith(("http://", "https://", "data:")):
                continue
            img = (path.parent / ref).resolve()
            if img.exists() and img.suffix.lower() in _IMAGE_EXT:
                images.append(_copy_into(img, media_dir))
    return [text], [], images


def _parse_rst(path: Path, media_dir: Path):
    from docutils.core import publish_doctree
    doctree = publish_doctree(path.read_text(encoding="utf-8", errors="ignore"))
    text_blocks: list[str] = []
    tables: list = []
    images: list[str] = []
    for node in doctree.traverse():
        tag = getattr(node, "tagname", "")
        if tag == "paragraph":
            text_blocks.append(node.astext())
        elif tag == "table":
            rows = []
            for row in node.traverse(condition=lambda x: x.tagname == "row"):
                cells = [c.astext() for c in row.traverse(condition=lambda x: x.tagname == "entry")]
                rows.append(cells)
            if rows:
                tables.append(rows)
        elif tag == "image" and "uri" in node.attributes:
            ref = str(node.attributes["uri"]).lstrip("/")
            img = (path.parent / ref).resolve()
            if img.exists() and img.suffix.lower() in _IMAGE_EXT:
                images.append(_copy_into(img, media_dir))
    return text_blocks, tables, images


def _parse_html(path: Path, media_dir: Path):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    images: list[str] = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src or src.startswith(("http://", "https://", "data:")):
            continue
        p = (path.parent / src).resolve()
        if p.exists() and p.suffix.lower() in _IMAGE_EXT:
            images.append(_copy_into(p, media_dir))
    return [text], [], images


def _parse_pdf(path: Path, media_dir: Path):
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    blocks = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        if t.strip():
            blocks.append(t)
    return blocks, [], []


def _parse_docx(path: Path, media_dir: Path):
    import docx
    d = docx.Document(str(path))
    blocks = [p.text for p in d.paragraphs if p.text.strip()]
    tables = []
    for t in d.tables:
        rows = [[c.text for c in row.cells] for row in t.rows]
        if rows:
            tables.append(rows)
    images: list[str] = []
    for rel in d.part.rels.values():
        if "image" in rel.reltype:
            try:
                blob = rel.target_part.blob
                ext = os.path.splitext(rel.target_ref)[1].lower() or ".png"
                media_dir.mkdir(parents=True, exist_ok=True)
                out = media_dir / f"{uuid.uuid4().hex}{ext}"
                out.write_bytes(blob)
                images.append(str(out))
            except Exception:
                logger.warning("Failed to extract an embedded image from docx")
    return blocks, tables, images


def _parse_image(path: Path, media_dir: Path):
    return [], [], [str(path)]


def _dispatch(path: Path, media_dir: Path):
    ext = path.suffix.lower()
    if ext in _TEXT_EXT:
        return _parse_text(path, media_dir)
    if ext == ".rst":
        return _parse_rst(path, media_dir)
    if ext in {".html", ".htm"}:
        return _parse_html(path, media_dir)
    if ext == ".pdf":
        return _parse_pdf(path, media_dir)
    if ext == ".docx":
        return _parse_docx(path, media_dir)
    if ext in _IMAGE_EXT:
        return _parse_image(path, media_dir)
    raise ValueError(f"Unsupported file type: {ext}")


# ── DB wiring ─────────────────────────────────────────────────────────────────

def _get_dbs():
    """Build the three RAG DBs + the (optional) LLM client used for table
    descriptions. Returns (text_db, image_db, table_db, client, model_name, gen_kwargs).
    client/model may be None if no small model is configured — text/image
    ingestion still works; only table summarization is skipped."""
    import chromadb
    from src.rag import RAG_DB_PATH
    from src.rag.db import initialize_dbs
    from src.models.configured import (
        get_small_model_client_opt, get_small_model_name, get_small_model_extra_args,
    )

    client = get_small_model_client_opt()
    model = get_small_model_name()
    gen_kwargs = get_small_model_extra_args()
    chroma = chromadb.PersistentClient(path=str(RAG_DB_PATH))
    text_db, image_db, table_db = initialize_dbs(chroma)
    return text_db, image_db, table_db, client, model, gen_kwargs


# ── Public API ─────────────────────────────────────────────────────────────────

async def ingest_file(
    file_path: str | Path,
    *,
    original_name: str | None = None,
    doc_id: str | None = None,
    extra: dict[str, Any] | None = None,
    copy_source: bool = True,
) -> dict[str, Any]:
    """Ingest one file into the RAG store and record it in the manifest.

    By default the source file is copied into `{upload_dir}/{doc_id}/` so it (and
    any extracted media) persist. `copy_source=False` parses the file *in place*
    instead — used when the file lives in a corpus whose relative asset refs
    (e.g. RST `.. image:: /images/foo.jpg`) must resolve against its real
    location; extracted media are still copied into the doc dir. `extra` is
    merged into the manifest entry. Returns the manifest entry, or
    {"error": ...} on an unsupported/oversized file.
    """
    settings = get_settings()
    src = Path(file_path)
    if not src.is_file():
        return {"error": f"Not a file: {src}"}
    original_name = original_name or src.name
    ext = src.suffix.lower()
    if ext not in settings.rag_upload_allowed_extensions:
        return {"error": f"Unsupported file type: {ext}"}
    if src.stat().st_size > settings.rag_upload_max_bytes:
        return {"error": f"File exceeds max size ({settings.rag_upload_max_bytes} bytes)"}

    doc_id = doc_id or uuid.uuid4().hex
    doc_dir = _upload_dir() / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    if copy_source:
        stored = doc_dir / f"source{ext}"
        if src.resolve() != stored.resolve():
            shutil.copyfile(src, stored)
    else:
        # Parse the original in place so relative asset refs resolve.
        stored = src

    text_db, image_db, table_db, client, model, gen_kwargs = _get_dbs()
    text_blocks, tables, image_paths = _dispatch(stored, doc_dir)

    chunks = 0
    for block in text_blocks:
        chunks += text_db.index(block, source=doc_id, title=original_name)

    n_tables = 0
    if tables:
        if client is not None and model:
            from src.rag.db import generate_table_description
            for table in tables:
                try:
                    desc = await generate_table_description(table, client, model, gen_kwargs)
                except Exception:
                    desc = "Table extracted from an uploaded document."
                n_tables += table_db.index(table, desc, source=doc_id, title=original_name)
        else:
            logger.warning("No small model configured; skipping %d table(s) in %s",
                           len(tables), original_name)

    n_images = image_db.add_data(image_paths, source=doc_id) if image_paths else 0

    entry = {
        "doc_id": doc_id,
        "filename": original_name,
        "ext": ext,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "chunks": chunks,
        "tables": n_tables,
        "images": n_images,
    }
    if extra:
        entry.update(extra)
    with _manifest_lock:
        m = _read_manifest()
        m["documents"][doc_id] = entry
        _write_manifest(m)
    logger.info(f"Ingested {original_name}: {chunks} chunks, {n_tables} tables, {n_images} images")
    return entry


async def ingest_folder(folder: str | Path) -> list[dict[str, Any]]:
    """Ingest every supported file in a folder (non-recursive)."""
    allowed = set(get_settings().rag_upload_allowed_extensions)
    folder = Path(folder)
    results: list[dict[str, Any]] = []
    for name in sorted(os.listdir(folder)):
        p = folder / name
        if p.is_file() and p.suffix.lower() in allowed:
            results.append(await ingest_file(p, original_name=name))
    return results


def list_documents() -> list[dict[str, Any]]:
    """All ingested user documents, newest first."""
    docs = list(_read_manifest()["documents"].values())
    docs.sort(key=lambda d: d.get("ingested_at", ""), reverse=True)
    return docs


def delete_document(doc_id: str) -> bool:
    """Remove a document's rows from every collection (by source tag), delete
    its stored files, and drop it from the manifest. Returns False if unknown."""
    import chromadb
    from src.rag import RAG_DB_PATH

    chroma = chromadb.PersistentClient(path=str(RAG_DB_PATH))
    for cname in _COLLECTIONS:
        try:
            col = chroma.get_or_create_collection(cname)
            col.delete(where={"source": doc_id})
        except Exception as exc:
            logger.warning(f"delete from {cname} failed: {exc}")

    doc_dir = _upload_dir() / doc_id
    if doc_dir.exists():
        shutil.rmtree(doc_dir, ignore_errors=True)

    with _manifest_lock:
        m = _read_manifest()
        existed = m["documents"].pop(doc_id, None) is not None
        _write_manifest(m)
    return existed


# ── Folder watcher: auto-ingest files dropped into a directory ────────────────
#
# A dependency-free polling watcher. On each pass it scans the watch dir for
# supported files and, for any file not yet ingested (or whose mtime changed
# since last ingest), ingests it — replacing the prior version on change.
# It runs in a daemon thread (NOT the event loop) and uses asyncio.run per
# file, so the embedding work never blocks the API's event loop.

def scan_watch_dir_once(watch_dir: str | Path) -> list[dict[str, Any]]:
    """One pass over the watch dir. Ingests new/changed files; returns summaries
    for whatever was (re-)ingested this pass (empty list if nothing changed)."""
    import asyncio

    watch_dir = Path(watch_dir)
    if not watch_dir.is_dir():
        return []
    allowed = set(get_settings().rag_upload_allowed_extensions)

    # Map already-watched files → (doc_id, recorded mtime) from the manifest.
    watched: dict[str, tuple[str, float]] = {}
    for d in _read_manifest()["documents"].values():
        wp = d.get("watch_path")
        if wp:
            watched[wp] = (d["doc_id"], float(d.get("watch_mtime", 0)))

    results: list[dict[str, Any]] = []
    for name in sorted(os.listdir(watch_dir)):
        p = watch_dir / name
        if not p.is_file() or p.suffix.lower() not in allowed:
            continue
        wp = str(p.resolve())
        mtime = p.stat().st_mtime
        prior = watched.get(wp)
        if prior and mtime <= prior[1]:
            continue  # unchanged since last ingest
        try:
            summary = asyncio.run(ingest_file(
                p, original_name=name,
                extra={"watch_path": wp, "watch_mtime": mtime},
            ))
        except Exception as exc:
            logger.warning(f"watch ingest failed for {name}: {exc}")
            continue
        if not summary.get("error") and prior:
            delete_document(prior[0])  # drop the superseded version
        results.append(summary)
    return results


def start_watcher() -> "threading.Thread | None":
    """Start the folder-watch daemon thread if rag_watch_dir is configured.
    Returns the thread, or None when watching is disabled."""
    import threading
    import time

    settings = get_settings()
    watch_dir = (settings.rag_watch_dir or "").strip()
    if not watch_dir:
        return None
    interval = max(5, int(settings.rag_watch_interval_seconds))
    Path(watch_dir).mkdir(parents=True, exist_ok=True)

    def _loop():
        logger.info(f"RAG folder watcher active on {watch_dir} (every {interval}s)")
        while True:
            try:
                done = scan_watch_dir_once(watch_dir)
                if done:
                    logger.info(f"watcher ingested {len(done)} file(s)")
            except Exception as exc:
                logger.warning(f"watcher pass error: {exc}")
            time.sleep(interval)

    t = threading.Thread(target=_loop, name="rag-folder-watcher", daemon=True)
    t.start()
    return t


# ── In-chat image display: resolve stored image paths → serveable refs ────────

def resolve_image_path(stored_path: str) -> Path | None:
    """Resolve an image path stored in the Chroma metadata to an existing file.

    User-uploaded images store absolute paths (used directly). Pre-existing
    'images/foo.jpg'-style relative paths are resolved against rag_image_base_dir
    when configured. Returns None if no readable file can be found."""
    if not stored_path:
        return None
    p = Path(stored_path)
    if p.is_absolute() and p.is_file():
        return p
    base = (get_settings().rag_image_base_dir or "").strip()
    if base:
        base_path = Path(base)
        if not base_path.is_absolute():
            # Resolve a repo-relative base (e.g. "src/rag/rag_assets") against
            # the project root so it works regardless of the server's CWD.
            from src.config import PROJECT_ROOT
            base_path = PROJECT_ROOT / base_path
        cand = (base_path / stored_path).resolve()
        if cand.is_file():
            return cand
    if p.is_file():
        return p.resolve()
    return None


def _caption_for(path: Path) -> str:
    """Human caption for an image. For uploaded images (stored as
    {upload_dir}/{doc_id}/source.ext) use the original filename from the
    manifest; otherwise prettify the file stem."""
    try:
        upload_root = Path(get_settings().rag_upload_dir).resolve()
        rp = path.resolve()
        if upload_root in rp.parents:
            doc = _read_manifest()["documents"].get(rp.parent.name)
            if doc and doc.get("filename"):
                return str(doc["filename"])
    except Exception:
        pass
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def build_image_refs(
    image_results: list[dict[str, Any]],
    *,
    max_results: int | None = None,
    max_distance: float | None = None,
) -> list[dict[str, Any]]:
    """Turn raw ImageDatabase.answer_query() results into serveable refs:
    [{"url": "/api/rag-image/<token>", "caption": str, "distance": float}].
    Filters by distance cutoff (if >0), caps to max_results, and skips images
    whose files can't be resolved."""
    from src.rag.image_cache import store as cache_store

    settings = get_settings()
    if max_results is None:
        max_results = settings.rag_image_max_results
    if max_distance is None:
        max_distance = settings.rag_image_max_distance
    if max_results <= 0:
        return []

    refs: list[dict[str, Any]] = []
    for item in image_results:
        if len(refs) >= max_results:
            break
        dist = item.get("distance")
        if max_distance and max_distance > 0 and dist is not None and dist > max_distance:
            continue
        resolved = resolve_image_path(item.get("path", ""))
        if resolved is None:
            continue
        token = uuid.uuid4().hex
        cache_store(token, str(resolved))
        refs.append({
            "url": f"/api/rag-image/{token}",
            "caption": _caption_for(resolved),
            "distance": dist,
        })
    return refs


# ── CLI: python -m src.rag.ingest_user <file-or-folder> [more ...] ─────────────

def _main(argv: list[str]) -> int:
    import asyncio

    if not argv:
        print("Usage: python -m src.rag.ingest_user <file-or-folder> [more ...]")
        print("       python -m src.rag.ingest_user --list")
        print("       python -m src.rag.ingest_user --delete <doc_id>")
        return 2

    if argv[0] == "--list":
        for d in list_documents():
            print(f"{d['doc_id']}  {d['filename']:<40} "
                  f"chunks={d['chunks']} tables={d['tables']} images={d['images']}")
        return 0

    if argv[0] == "--delete":
        if len(argv) < 2:
            print("--delete requires a doc_id")
            return 2
        ok = delete_document(argv[1])
        print("deleted" if ok else "not found")
        return 0 if ok else 1

    async def run():
        summaries: list[dict[str, Any]] = []
        for target in argv:
            p = Path(target)
            if p.is_dir():
                summaries.extend(await ingest_folder(p))
            elif p.is_file():
                summaries.append(await ingest_file(p))
            else:
                print(f"skip (not found): {target}")
        for s in summaries:
            if s.get("error"):
                print(f"ERROR {s['error']}")
            else:
                print(f"OK {s['filename']}: chunks={s['chunks']} "
                      f"tables={s['tables']} images={s['images']} (doc_id={s['doc_id']})")
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
