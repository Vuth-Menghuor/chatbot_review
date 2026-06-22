"""
Infrastructure module - General Retrieval Service
Contains vector/search clients and external service adapters
"""

from .vector_store import VectorStoreClient
from .embeddings import EmbeddingClient
from .repositories import DocumentRepository
from .gemini_client import GeminiClient

__all__ = [
    "VectorStoreClient",
    "EmbeddingClient",
    "DocumentRepository",
    "GeminiClient",
]
