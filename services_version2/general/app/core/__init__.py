"""
Compatibility Exports — General Retrieval Service.

Central re-export point for all major service components. This allows
callers (e.g. the API layer) to import from a single location rather
than from each sub-package individually.
"""

from ..embeddings.embeddings import EmbeddingClient
from ..llm.gemini_client import GeminiClient
from ..repositories.repositories import DocumentRepository
from ..rag.answer_generator import AnswerGenerator
from ..rag.query import QueryProcessor
from ..rag.retrieval import RetrievalOrchestrator
from ..rag.service import GeneralRetrievalService
from ..vectorstore.vector_store import VectorStoreClient

__all__ = [
    "AnswerGenerator",
    "DocumentRepository",
    "EmbeddingClient",
    "GeminiClient",
    "GeneralRetrievalService",
    "QueryProcessor",
    "RetrievalOrchestrator",
    "VectorStoreClient",
]