"""
Base classes for RAG pipeline components.

This module defines the base classes for the retriever, reranker, and generator components of the RAG pipeline.
"""
from typing import List
import numpy as np


class BaseRetriever:
    def embed(self, query:List[str], **kwargs) -> np.ndarray:
        raise NotImplementedError('Please implement this method.')
    def retrieve(self, query:List[str], **kwargs) -> List[str]:
        raise NotImplementedError('Please implement this method.')


class BaseReranker:
    def rank(self, query:str, contexts:List[str], topk:int) -> List[str]:
        raise NotImplementedError('Please implement this method.')


class BaseGenerator:

    def build_prompt(self, query:str, contexts:List[str]) -> str:
        raise NotImplementedError('Please implement this method')
    
    def parse_response(self, model_output:str) -> str:
        raise NotImplementedError('Please implement this method.')

    def generate(self, query:str, contexts:List[str], **pipeline_kwargs) -> str:
        raise NotImplementedError('Please implement this method.')