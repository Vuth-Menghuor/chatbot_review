"""
Retrieval Orchestration Module — Retrieval Service.

Provides a thin orchestration layer that wraps the vector store and
embedding client for semantic (dense-vector) search against the HS code
Qdrant collection. This module is intentionally minimal — all heavier
logic (corpus loading, prefix scanning, candidate scoring) lives in
``service.py``.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetrievalOrchestrator:
    """
    Thin wrapper around the vector store + embedding client.

    Responsibilities
    ----------------
    - Accept a free-text query, embed it, and run semantic search.
    - Log result counts and collection names for observability.
    - Return raw document dicts — scoring and transformation are handled
      upstream by ``RetrievalService`` and the API layer.

    Parameters
    ----------
    vector_store_client : VectorStoreClient
        Configured Qdrant client.
    embedding_client : EmbeddingClient
        Configured embedding model client.
    """

    def __init__(self, vector_store_client=None, embedding_client=None):
        self.vector_store = vector_store_client
        self.embeddings = embedding_client

    async def retrieve_semantic(
        self,
        query: str,
        top_k: int = 10,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run a semantic (dense-vector) search against the Qdrant collection.

        Parameters
        ----------
        query : str
            Free-text search query.
        top_k : int
            Maximum number of results to return.
        collection_name : Optional[str]
            Override the default collection. If None, uses the client's
            configured collection.

        Returns
        -------
        List[Dict[str, Any]]
            Raw document dicts with at least ``id``, ``score``, and
            ``payload`` fields. Empty list on any failure.
        """
        active_collection = (
            collection_name
            or (self.vector_store.collection_name if self.vector_store else "N/A")
        )
        logger.info(
            "Semantic search for: %s... (collection: %s)",
            query[:100],
            active_collection,
        )

        try:
            if not self.embeddings:
                logger.error("Embedding client not configured")
                return []
            if not self.vector_store:
                logger.error("Vector store client not configured")
                return []

            embedding = await self.embeddings.embed_query(query)
            if not embedding or len(embedding) == 0:
                logger.warning(
                    "Invalid embedding generated for query: %s...", query[:50]
                )
                return []

            results = await self.vector_store.search(
                embedding=embedding,
                top_k=top_k,
                collection_name=collection_name,
            )

            logger.info(
                "Found %d documents from semantic search (collection: %s)",
                len(results),
                active_collection,
            )
            return results

        except Exception as e:
            logger.error("Semantic search error: %s", e)
            return []