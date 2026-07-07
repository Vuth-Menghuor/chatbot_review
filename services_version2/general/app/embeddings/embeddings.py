"""
Embedding Client - Infrastructure layer
Handles query and document embeddings using sentence-transformers.
Falls back to keyword-based embeddings if torch is unavailable.
"""

import logging
import hashlib
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Lazy load embedder to avoid memory overhead on import
_embedder = None
_embedder_name = None
_use_fallback = False


def get_embedder(model_name: str):
    """Get or initialize embedder with lazy loading. Falls back to keyword-based if torch unavailable."""
    global _embedder, _embedder_name, _use_fallback

    if _embedder is None or _embedder_name != model_name:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedder: {model_name}")
            _embedder = SentenceTransformer(model_name)
            _embedder_name = model_name
            _use_fallback = False
        except Exception as e:
            logger.warning(f"Failed to load SentenceTransformer: {e}. Using keyword-based fallback.")
            _embedder = None
            _use_fallback = True

    return _embedder


def create_keyword_embedding(text: str, dimension: int = 1024) -> List[float]:
    """
    Create a simple keyword-based embedding using hash and keyword frequency.
    Used as fallback when SentenceTransformer is unavailable.

    Args:
        text: Text to embed
        dimension: Embedding dimension (default 1024 to match BAAI/bge-m3)

    Returns:
        Simple embedding vector
    """
    text_lower = text.lower()
    words = text_lower.split()

    embedding = [0.0] * dimension

    text_hash = int(hashlib.md5(text_lower.encode()).hexdigest(), 16)

    for i, word in enumerate(words[:min(20, dimension)]):
        word_hash = int(hashlib.md5(word.encode()).hexdigest(), 16)
        value = ((word_hash % 200) - 100) / 100.0
        embedding[i % dimension] += value

    for i in range(dimension):
        text_hash = (text_hash * 1103515245 + 12345) & ((1 << 31) - 1)
        embedding[i] += ((text_hash % 200) - 100) / 1000.0

    magnitude = sum(x**2 for x in embedding) ** 0.5
    if magnitude > 0:
        embedding = [x / magnitude for x in embedding]

    return embedding


class EmbeddingClient:
    """
    Client for generating embeddings.

    Responsibilities:
    - Embed queries
    - Embed documents
    - Model loading
    - Health checks
    - Fallback to keyword-based embeddings if torch unavailable
    """

    def __init__(self, model_name: str = "BAAI/bge-m3"):
        """
        Initialize embedding client.

        Args:
            model_name: Sentence transformer model name
        """
        self.model_name = model_name
        self.embedder = None
        self.use_fallback = False
        self.embedding_dimension = 1024  # Default for BAAI/bge-m3

    def _load_embedder(self):
        """Lazy load embedder on first use. Falls back to keyword-based if needed."""
        if self.embedder is None:
            self.embedder = get_embedder(self.model_name)
            if self.embedder is None:
                self.use_fallback = True
                logger.warning("Using keyword-based fallback embeddings")

    async def embed_query(self, query: str) -> List[float]:
        """
        Embed a query.

        Args:
            query: Query text

        Returns:
            Query embedding vector
        """
        try:
            self._load_embedder()

            if self.embedder is not None:
                embedding = self.embedder.encode(query)
                return embedding.tolist()
            else:
                logger.debug(f"Using fallback embedding for query: {query[:50]}...")
                return create_keyword_embedding(query, self.embedding_dimension)

        except Exception as e:
            logger.warning(f"Query embedding error: {e}, using fallback")
            return create_keyword_embedding(query, self.embedding_dimension)

    async def embed_document(self, text: str) -> List[float]:
        """
        Embed a document.

        Args:
            text: Document text

        Returns:
            Document embedding vector
        """
        try:
            self._load_embedder()

            if self.embedder is not None:
                embedding = self.embedder.encode(text)
                return embedding.tolist()
            else:
                logger.debug(f"Using fallback embedding for document: {text[:50]}...")
                return create_keyword_embedding(text, self.embedding_dimension)

        except Exception as e:
            logger.warning(f"Document embedding error: {e}, using fallback")
            return create_keyword_embedding(text, self.embedding_dimension)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        try:
            self._load_embedder()

            if self.embedder is not None:
                embeddings = self.embedder.encode(texts)
                return embeddings.tolist()
            else:
                return [create_keyword_embedding(text, self.embedding_dimension) for text in texts]

        except Exception as e:
            logger.warning(f"Batch embedding error: {e}, using fallback")
            return [create_keyword_embedding(text, self.embedding_dimension) for text in texts]

    async def health(self) -> Dict[str, Any]:
        """
        Check health of embeddings service.

        Returns:
            Health status
        """
        try:
            self._load_embedder()

            if self.embedder is None:
                return {
                    "status": "degraded",
                    "reason": "Using keyword-based fallback",
                    "mode": "fallback"
                }

            test_embedding = await self.embed_query("test")
            if not test_embedding or len(test_embedding) == 0:
                return {
                    "status": "unhealthy",
                    "reason": "Test embedding failed"
                }

            return {
                "status": "healthy",
                "model": self.model_name,
                "dimension": len(test_embedding)
            }

        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {
                "status": "unhealthy",
                "reason": str(e)
            }
