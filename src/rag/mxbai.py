"""
mxbai RAG pipeline components.
"""
from typing import List
import numpy as np

from .base import BaseRetriever
from .base import BaseReranker
from .model_cache import get_sentence_transformer
from .model_cache import get_cross_encoder


class MxbaiRetriever(BaseRetriever):
    """
    Retriever using SentenceTransformer from sentence_transformers.
    """
    def __init__(self, model_name, collection):
        self.model = get_sentence_transformer(model_name)
        self.collection = collection

    def embed(self, query:List[str], **kwargs) -> np.ndarray:
        emb = self.model.encode( query, show_progress_bar=False, convert_to_numpy=True, **kwargs)
        return emb

    def retrieve(self, collection_name, query: List[str], topk=5) -> List[str]:
        contexts = self.collection.query(query_texts=query, n_results=topk)
        return contexts


class MxbaiReranker(BaseReranker):
    """
    Reranker using CrossEncoder from sentence_transformers.
    """

    def __init__(self, model_name):
        self.model = get_cross_encoder(model_name)
    
    def rank(self, query: str, contexts: List[str], topk:int) -> List[str]:
        topk = min(topk, len(contexts))
        pairs = [(query, context) for context in contexts]
        scores = self.model.predict(pairs)
        indices = np.argsort(scores)[::-1]
        return [contexts[i] for i in indices][:topk]