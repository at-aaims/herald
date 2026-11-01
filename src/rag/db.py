"""
RAG (Retrieval Augmented Generation) implementation using ChromaDB for text,
image, and table databases. LangChain-free — uses an AsyncOpenAI client for
chat completions and a small char-based splitter for ingestion chunking.
"""
import os
import uuid
import torch
import pandas as pd
from typing import Any, List
from loguru import logger
from openai import OpenAI, AsyncOpenAI
from chromadb import PersistentClient
from docutils.core import publish_doctree
from PIL import Image
from sentence_transformers import SentenceTransformer
from tqdm.autonotebook import tqdm

from .model_cache import get_embedding_function
from .model_cache import get_sentence_transformer
from .model_cache import get_clip_model, get_clip_processor
from .mxbai import MxbaiRetriever
from .mxbai import MxbaiReranker


def _split_markdown(text: str, chunk_size: int = 300, chunk_overlap: int = 50) -> list[str]:
    """Char-based splitter that prefers heading and paragraph boundaries.

    Replaces langchain.text_splitter.MarkdownTextSplitter. Good enough for the
    ingest pipeline — chunks are kept under chunk_size and overlap by chunk_overlap.
    """
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # Prefer to break at a newline boundary
        if end < len(text):
            split = text.rfind("\n", start, end)
            if split > start + chunk_size // 2:
                end = split
        chunks.append(text[start:end].strip())
        start = max(end - chunk_overlap, start + 1)
    return [c for c in chunks if c]


class TextDatabase:
    """Text retrieval over a ChromaDB collection (index + retrieve; no LLM)."""

    def __init__(self, collection):
        self.collection = collection
        logger.info("Initializing text database")
        self.text_model = get_sentence_transformer("mixedbread-ai/mxbai-embed-large-v1")
        self.retriever = MxbaiRetriever('mixedbread-ai/mxbai-embed-large-v1', collection)
        self.ranker = MxbaiReranker('mixedbread-ai/mxbai-rerank-large-v1')

    def index(self, text, source: str = "builtin", title: str = "") -> int:
        """Chunk + embed text into the collection. `source` tags every chunk
        (for list/delete by document) and `title` is a human label carried into
        retrieval for citations. Returns the number of chunks added."""
        chunks = _split_markdown(text, chunk_size=300, chunk_overlap=50)
        if not chunks:
            return 0
        # Batched, not one .encode() call per chunk: SentenceTransformer batches
        # internally (default batch_size=32), which is dramatically faster on
        # CPU than one chunk at a time -- the dominant cost in first-boot RAG
        # ingestion (one doc alone can be 7000+ chunks). Same embeddings, same
        # order, just computed together instead of one Python call each.
        vectors = self.text_model.encode(chunks).tolist()
        metadata = [{"chunk": chunk, "source": source, "title": title} for chunk in chunks]
        ids = [uuid.uuid4().hex for _ in chunks]
        self.collection.add(embeddings=vectors, metadatas=metadata, ids=ids)
        return len(chunks)

    def retrieve(self, query: str, top_k: int = 4) -> list[dict]:
        """Retrieval-only: return the top_k reranked chunks as
        [{"chunk", "title", "source"}], without any LLM call. The orchestrator
        synthesizes the final answer from these (one generation instead of two)."""
        query_vector = self.text_model.encode(query).tolist()
        result = self.collection.query(
            query_embeddings=[query_vector], n_results=9, include=["metadatas"],
        )
        metas = (result.get("metadatas") or [[]])[0]
        by_chunk: dict[str, dict] = {}
        for m in metas:
            c = m.get("chunk")
            if c and c not in by_chunk:
                by_chunk[c] = m
        ranked = self.ranker.rank(query, list(by_chunk.keys()), topk=top_k)
        return [
            {"chunk": c, "title": by_chunk[c].get("title", ""), "source": by_chunk[c].get("source", "")}
            for c in ranked
        ]

class ImageDatabase:
    """
    A class to handle image data storage and retrieval using ChromaDB.
    """
    def __init__(self, collection):
        self.collection = collection
        logger.info("Initializing image database")
        # Cached: first call loads from disk, later calls reuse the instance.
        self.clip_model = get_clip_model("openai/clip-vit-base-patch32")
        self.clip_processor = get_clip_processor("openai/clip-vit-base-patch32")

    def add_data(self, images, source: str = "builtin") -> int:
        """Embed each image with CLIP and store its path + source tag.
        Returns the number of images added (skips ones that fail to open)."""
        metadata_list = []
        vector_list = []
        ids = []
        for image_path in images:
            try:
                image = Image.open(image_path)
            except Exception:
                logger.warning(f"Skipping unreadable image: {image_path}")
                continue
            inputs = self.clip_processor(images=[image], return_tensors="pt")
            with torch.no_grad():
                vector_list.append(self.clip_model.get_image_features(**inputs).squeeze().tolist())
                metadata_list.append({"path": str(image_path), "source": source})
                ids.append(uuid.uuid4().hex)

        if not ids:
            return 0
        self.collection.add(embeddings=vector_list, metadatas=metadata_list, ids=ids)
        return len(ids)

    def encode_clip_text(self,text):
        inputs = self.clip_processor(text=[text], return_tensors="pt")
        with torch.no_grad():
            vector = self.clip_model.get_text_features(**inputs).squeeze().tolist()
            return vector

    def answer_query(self, text_query, top_k: int = 3):
        """Return up to top_k nearest images, closest first, as a list of
        {"path", "distance", "source"} dicts. Empty list when the image
        collection has no match (or is empty)."""
        try:
            query_vector = self.encode_clip_text(text_query)
            res = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                include=["metadatas", "distances"],
            )
        except Exception:
            return []
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        out = []
        for m, d in zip(metas, dists):
            path = m.get("path")
            if not path:
                continue
            out.append({"path": path, "distance": float(d), "source": m.get("source", "")})
        return out


class TableDatabase:
    """Table retrieval over a ChromaDB collection (index + retrieve; no LLM)."""

    def __init__(self, collection):
        self.collection = collection
        logger.info("Initializing table database")
        self.text_model = get_sentence_transformer("mixedbread-ai/mxbai-embed-large-v1")
        self.retriever = MxbaiRetriever('mixedbread-ai/mxbai-embed-large-v1', collection)
        self.ranker = MxbaiReranker('mixedbread-ai/mxbai-rerank-large-v1')

    def encode_table_as_text(self, table):
        return "\n".join((" | ".join(map(str, row))).replace("\n", "") for row in table)

    def index(self, table, table_desc, source: str = "builtin", title: str = "") -> int:
        table_str = self.encode_table_as_text(table)
        vector = self.text_model.encode(table_desc).tolist()
        metadata = {"table": table_str, "source": source, "title": title}
        self.collection.add(embeddings=[vector], metadatas=[metadata], ids=[uuid.uuid4().hex])
        return 1

    def retrieve(self, query: str) -> dict | None:
        """Retrieval-only: return the nearest table as {"table","title","source"}
        (raw markdown), or None. No LLM call."""
        query_vector = self.text_model.encode(query).tolist()
        result = self.collection.query(
            query_embeddings=[query_vector], n_results=1, include=["metadatas"],
        )
        metas = (result.get("metadatas") or [[]])[0]
        if not metas:
            return None
        m = metas[0]
        return {"table": m.get("table", ""), "title": m.get("title", ""), "source": m.get("source", "")}


def initialize_dbs(chroma_client: PersistentClient):
    """Initialize the text / image / table ChromaDB collections for retrieval and
    ingest. No LLM client is needed here — answer synthesis happens in the
    orchestrator, and table-description generation builds its own client.

    Args:
        chroma_client: chromadb.PersistentClient instance
    """
    text_ef = get_embedding_function(model_name="mixedbread-ai/mxbai-embed-large-v1")
    collections = {
        "text": chroma_client.get_or_create_collection("text_v1", embedding_function=text_ef),
        "images": chroma_client.get_or_create_collection("images_v1"),
        "tables": chroma_client.get_or_create_collection("tables_v1"),
    }
    text_db = TextDatabase(collections["text"])
    image_db = ImageDatabase(collections["images"])
    table_db = TableDatabase(collections["tables"])
    return text_db, image_db, table_db

#
# Ingest pipeline code
#

async def generate_table_description(table, openai_client: AsyncOpenAI, model_name: str,
                                     gen_kwargs: dict | None = None) -> str:
    """Summarize an extracted table using the configured chat model.

    `gen_kwargs` carries per-model sampling params (e.g. {'temperature': 0.6});
    omit them for models like gpt-5.x that only accept defaults.
    """
    table_df = pd.DataFrame(table[1:], columns=table[0])
    markdown_table = table_df.to_markdown(index=False)
    prompt = (
        "The following is a table extracted from a document:\n\n"
        f"{markdown_table}\n\n"
        "Generate a 50 word summary about what the contents of this table are, "
        "as if writing a header to describe the table. Only output the description, no extra text."
    )
    response = await openai_client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        **(gen_kwargs or {}),
    )
    return response.choices[0].message.content or ""



def create_database(
    text_db: TextDatabase,
    image_db: ImageDatabase,
    table_db: TableDatabase,
    *,
    openai_client: AsyncOpenAI,
    model_name: str,
    document_folder: str = '/content/documents',
):
    """Ingest RST files from a folder into the text / image / table collections."""
    import asyncio
    count = 1
    for file_name in os.listdir(document_folder):
        if not file_name.endswith(".rst"):
            continue
        logger.info(f"- Ingesting file {count}: {file_name}")
        file_path = os.path.join(document_folder, file_name)
        with open(file_path, 'r', encoding='utf-8') as file:
            rst_content = file.read()

        doctree = publish_doctree(rst_content)
        text_content: list[str] = []
        tables: list = []
        images: list[str] = []

        def is_inside_table(node):
            cur = node
            while cur.parent is not None:
                if hasattr(cur.parent, 'tagname') and cur.parent.tagname == 'table':
                    return True
                cur = cur.parent
                return False

        for node in doctree.traverse():
            if node.tagname == 'paragraph':
                if not is_inside_table(node):
                    text_content.append(node.astext())
                elif node.tagname == 'table':
                    rows = []
                    for row in node.traverse(condition=lambda x: x.tagname == 'row'):
                        cells = [cell.astext() for cell in row.traverse(condition=lambda x: x.tagname == 'entry')]
                        rows.append(cells)
                        tables.append(rows)
                elif node.tagname == 'image':
                    if 'uri' in node.attributes:
                        images.append(node.attributes['uri'][1:])

        for text in tqdm(text_content):
            text_db.index(text)
        if images:
            image_db.add_data(images)
        for table in tqdm(tables):
            table_description = asyncio.run(
                generate_table_description(table, openai_client, model_name)
            )
            table_db.index(table, table_description)
        count += 1

    return text_db, image_db, table_db

