"""
Embedding Client — Infrastructure Layer.

Generates dense vector embeddings for user queries using the
``sentence-transformers`` library. If the model cannot be loaded (e.g.
missing dependency, network issue), the client falls back to a lightweight
keyword-based deterministic embedding so the service remains operational.

Architecture Note
-----------------
The underlying ``SentenceTransformer`` instance is cached in a module-level
global (``_embedder``). This is safe because the service only ever uses a
single embedding model per process. If multi-model support is needed in the
future, move the cache into the ``EmbeddingClient`` instance.
"""

import logging
import hashlib
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level embedder cache — only one model is used process-wide.
# ---------------------------------------------------------------------------
_embedder = None
_embedder_name = None


def get_embedder(model_name: str):
    """
    Lazily load the ``SentenceTransformer`` model, or return the cached
    instance if already loaded.

    Falls back to keyword-based embeddings if ``SentenceTransformer`` is
    not installed or the model download fails.
    """
    global _embedder, _embedder_name

    if _embedder is None or _embedder_name != model_name:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedder: %s", model_name)
            _embedder = SentenceTransformer(model_name)
            _embedder_name = model_name
        except Exception as e:
            logger.warning(
                "Failed to load SentenceTransformer: %s. "
                "Using keyword-based fallback.", e
            )
            _embedder = None

    return _embedder


def create_keyword_embedding(text: str, dimension: int = 384) -> List[float]:
    """
    Produce a deterministic embedding from text alone using keyword hashing.

    This is a **degraded-mode fallback** — it does not capture semantic
    similarity and should only be used when the sentence-transformer model
    is unavailable. The output is a unit-normalised vector of the requested
    dimension.

    Algorithm
    ---------
    1. Hash each word (up to 20) via MD5 and map to [-1.0, 1.0].
    2. Spread a pseudo-random sequence across the remaining dimensions.
    3. L2-normalise the result.
    """
    text_lower = text.lower()
    words = text_lower.split()

    embedding = [0.0] * dimension
    text_hash = int(hashlib.md5(text_lower.encode()).hexdigest(), 16)

    # Word-level contributions.
    for i, word in enumerate(words[: min(20, dimension)]):
        word_hash = int(hashlib.md5(word.encode()).hexdigest(), 16)
        value = ((word_hash % 200) - 100) / 100.0
        embedding[i % dimension] += value

    # Pseudo-random fill for remaining dimensions.
    for i in range(dimension):
        text_hash = (text_hash * 1103515245 + 12345) & ((1 << 31) - 1)
        embedding[i] += ((text_hash % 200) - 100) / 1000.0

    # L2-normalise.
    magnitude = sum(x**2 for x in embedding) ** 0.5
    if magnitude > 0:
        embedding = [x / magnitude for x in embedding]

    return embedding


class EmbeddingClient:
    """
    Client for generating query embeddings.

    Responsibilities
    ----------------
    - Embed free-text queries into dense vectors.
    - Report embedding model health.
    - Fall back to keyword-based embeddings when the model is unavailable
      (controlled by ``create_keyword_embedding``).
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.embedder = None
        # Default dimension for ``all-MiniLM-L6-v2``.
        self.embedding_dimension = 384

    def _load_embedder(self):
        """Lazily initialise the underlying model on first use."""
        if self.embedder is None:
            self.embedder = get_embedder(self.model_name)
            if self.embedder is None:
                logger.warning("Using keyword-based fallback embeddings")

    async def embed_query(self, query: str) -> List[float]:
        """
        Embed a free-text query into a dense vector.

        Returns a ``List[float]`` of length ``self.embedding_dimension``.
        Falls back to keyword-based embedding if the model call fails.
        """
        try:
            self._load_embedder()
            if self.embedder is not None:
                embedding = self.embedder.encode(query)
                return embedding.tolist()
            logger.debug("Using fallback embedding for query: %s...", query[:50])
            return create_keyword_embedding(query, self.embedding_dimension)
        except Exception as e:
            logger.warning("Query embedding error: %s, using fallback", e)
            return create_keyword_embedding(query, self.embedding_dimension)

    async def health(self) -> Dict[str, Any]:
        """
        Check embedding service health.

        Returns a dict with ``status`` ('healthy', 'degraded', 'unhealthy'),
        the model name, and the embedding dimension.
        """
        try:
            self._load_embedder()

            if self.embedder is None:
                return {
                    "status": "degraded",
                    "reason": "Using keyword-based fallback",
                    "mode": "fallback",
                }

            test_embedding = await self.embed_query("test")
            if not test_embedding or len(test_embedding) == 0:
                return {"status": "unhealthy", "reason": "Test embedding failed"}

            return {
                "status": "healthy",
                "model": self.model_name,
                "dimension": len(test_embedding),
            }

        except Exception as e:
            logger.error("Health check error: %s", e)
            return {"status": "unhealthy", "reason": str(e)}