"""
Embedding Client - Infrastructure layer
Handles query embeddings using sentence-transformers.
Falls back to keyword-based embeddings if the model can't be loaded.
"""

import logging
import hashlib
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

_embedder = None
_embedder_name = None


def get_embedder(model_name: str):
    """Get or initialize embedder with lazy loading. Falls back to keyword-based if unavailable."""
    global _embedder, _embedder_name

    if _embedder is None or _embedder_name != model_name:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedder: {model_name}")
            _embedder = SentenceTransformer(model_name)
            _embedder_name = model_name
        except Exception as e:
            logger.warning(f"Failed to load SentenceTransformer: {e}. Using keyword-based fallback.")
            _embedder = None

    return _embedder


def create_keyword_embedding(text: str, dimension: int = 384) -> List[float]:
    """Simple keyword-based embedding fallback when SentenceTransformer is unavailable."""
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
    Client for generating query embeddings.

    Responsibilities:
    - Embed queries
    - Health checks
    - Fallback to keyword-based embeddings if the model is unavailable
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.embedder = None
        self.embedding_dimension = 384  # Default for all-MiniLM-L6-v2

    def _load_embedder(self):
        if self.embedder is None:
            self.embedder = get_embedder(self.model_name)
            if self.embedder is None:
                logger.warning("Using keyword-based fallback embeddings")

    async def embed_query(self, query: str) -> List[float]:
        """Embed a query."""
        try:
            self._load_embedder()
            if self.embedder is not None:
                embedding = self.embedder.encode(query)
                return embedding.tolist()
            logger.debug(f"Using fallback embedding for query: {query[:50]}...")
            return create_keyword_embedding(query, self.embedding_dimension)
        except Exception as e:
            logger.warning(f"Query embedding error: {e}, using fallback")
            return create_keyword_embedding(query, self.embedding_dimension)

    async def health(self) -> Dict[str, Any]:
        """Check health of embeddings service."""
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
                return {"status": "unhealthy", "reason": "Test embedding failed"}

            return {
                "status": "healthy",
                "model": self.model_name,
                "dimension": len(test_embedding)
            }

        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {"status": "unhealthy", "reason": str(e)}