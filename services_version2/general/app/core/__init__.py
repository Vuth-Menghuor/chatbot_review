"""
Compatibility exports for the general retrieval service.
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