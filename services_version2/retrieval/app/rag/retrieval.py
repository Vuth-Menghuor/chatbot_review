"""
Retrieval Orchestration Module - Retrieval service
Wraps semantic (vector) search against the HS code collection.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetrievalOrchestrator:
    """
    Thin orchestration layer around the vector store + embedding client
    for semantic search against the HS code collection.
    """

    def __init__(self, vector_store_client=None, embedding_client=None):
        """
        Args:
            vector_store_client: Qdrant vector store client
            embedding_client: Embedding service client
        """
        self.vector_store = vector_store_client
        self.embeddings = embedding_client

    async def retrieve_semantic(
        self,
        query: str,
        top_k: int = 10,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve documents via semantic (vector) search."""
        active_collection = collection_name or (self.vector_store.collection_name if self.vector_store else "N/A")
        logger.info(f"Semantic search for: {query[:100]}... (collection: {active_collection})")

        try:
            if not self.embeddings:
                logger.error("Embedding client not configured")
                return []
            if not self.vector_store:
                logger.error("Vector store client not configured")
                return []

            embedding = await self.embeddings.embed_query(query)
            if not embedding or len(embedding) == 0:
                logger.warning(f"Invalid embedding generated for query: {query[:50]}...")
                return []

            results = await self.vector_store.search(
                embedding=embedding,
                top_k=top_k,
                collection_name=collection_name,
            )

            logger.info(f"Found {len(results)} documents from semantic search (collection: {active_collection})")
            return results

        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            return []