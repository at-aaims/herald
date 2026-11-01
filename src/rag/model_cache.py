"""
model_cache.py — Cached factories for RAG embedding/reranking models.

The in-process Llama generator was removed (drop in-process HuggingFace policy).
If you need an LLM for RAG, use the AsyncOpenAI client from src.models.configured.
"""
import functools
from sentence_transformers import SentenceTransformer
from sentence_transformers import CrossEncoder
from chromadb.utils.embedding_functions import HuggingFaceEmbeddingFunction


def _cache_with_failure(fn):
    """Like functools.cache, but also memoizes a raised exception.

    functools.cache only memoizes successful returns — a model that fails to
    load (e.g. a network/TLS error fetching weights from huggingface.co) would
    otherwise re-attempt the same slow, failing download on every single RAG
    call for the life of the process, instead of failing fast. The load can
    only succeed again after whatever's actually broken (connectivity, proxy
    cert trust) is fixed and the process restarts, so there's no point retrying
    the exact same call in the meantime.
    """
    cached = functools.cache(fn)
    failures: dict[tuple, Exception] = {}

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        if key in failures:
            raise failures[key]
        try:
            return cached(*args, **kwargs)
        except Exception as exc:
            failures[key] = exc
            raise
    return wrapper


@_cache_with_failure
def get_sentence_transformer(model_name) -> SentenceTransformer:
    return SentenceTransformer(model_name, trust_remote_code=True)


@_cache_with_failure
def get_cross_encoder(model_name) -> CrossEncoder:
    return CrossEncoder(model_name)


@_cache_with_failure
def get_embedding_function(model_name) -> HuggingFaceEmbeddingFunction:
    return HuggingFaceEmbeddingFunction(api_key="", model_name=model_name)


@_cache_with_failure
def get_clip_model(model_name):
    """Cached CLIP model. Loading the weights (~600MB) from disk is a dominant
    per-query cost when uncached — every RAG call constructs an ImageDatabase,
    so the model must be shared across calls."""
    from transformers import CLIPModel
    return CLIPModel.from_pretrained(model_name)


@_cache_with_failure
def get_clip_processor(model_name):
    """Cached CLIP processor — paired with get_clip_model()."""
    from transformers import CLIPProcessor
    return CLIPProcessor.from_pretrained(model_name)
