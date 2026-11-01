"""
src/rag/chain.py — RAG chain.

The mxbai-backed chain searches text, table, and image collections in ChromaDB
and returns the retrieved context; the orchestrator synthesizes the answer.
"""
from __future__ import annotations
import asyncio
from typing import Any


async def run_rag_retrieval(query: str, *, top_k_text: int = 4) -> dict[str, Any]:
    """Retrieval-only RAG: return the relevant context WITHOUT generating an
    answer (no LLM call). The orchestrator synthesizes from this, so each docs
    lookup is one fast retrieval instead of two sub-LLM generations.

    Returns:
        {
            "chunks": list[{chunk, title, source}],   # top reranked text passages
            "table":  {table, title, source} | None,  # nearest table (raw markdown)
            "images": list[{path, distance, source}], # nearest images
        }
    """
    import chromadb
    from . import RAG_DB_PATH
    from .db import initialize_dbs

    chroma = chromadb.PersistentClient(path=str(RAG_DB_PATH))
    text_db, image_db, table_db = initialize_dbs(chroma)

    chunks, images, table = await asyncio.gather(
        asyncio.to_thread(text_db.retrieve, query, top_k_text),
        asyncio.to_thread(image_db.answer_query, query),
        asyncio.to_thread(table_db.retrieve, query),
    )
    return {"chunks": chunks, "table": table, "images": images}
