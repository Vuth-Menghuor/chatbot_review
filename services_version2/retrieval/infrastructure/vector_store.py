"""
Vector Store Client - Infrastructure layer
Wraps Qdrant vector database for semantic search
"""

import logging
from typing import Optional, Dict, Any, List
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

logger = logging.getLogger(__name__)


class VectorStoreClient:
    """
    Client for Qdrant vector database.
    
    Responsibilities:
    - Semantic search via vector similarity
    - Collection management
    - Health checks
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        collection_name: str,
        timeout: float = 30.0,
        api_key: str = "",
        default_score_threshold: Optional[float] = None,
    ):
        """
        Initialize vector store client.
        
        Args:
            host: Qdrant host
            port: Qdrant port
            collection_name: Collection to search
            timeout: Request timeout
        """
        self.host = host
        self.port = port
        self.collection_name = collection_name
        self.timeout = timeout
        self.default_score_threshold = default_score_threshold
        
        try:
            self.client = QdrantClient(
                host=host,
                port=port,
                api_key=api_key or None,
                timeout=timeout
            )
            logger.info(f"Connected to Qdrant at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}")
            self.client = None
    
    async def search(
        self,
        embedding: List[float],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search vector store by embedding.
        
        Args:
            embedding: Query embedding vector
            top_k: Number of results
            score_threshold: Minimum similarity score
            
        Returns:
            List of search results with scores
        """
        try:
            if not self.client:
                logger.error("Vector store client not initialized")
                return []

            target_collection = collection_name or self.collection_name
            actual_threshold = (score_threshold if score_threshold is not None else self.default_score_threshold)

            # Try the newer API first (qdrant-client >= 1.7.0)
            points = None
            try:
                search_result = self.client.query_points(
                    collection_name=target_collection,
                    query=embedding,
                    limit=top_k,
                    score_threshold=(
                        score_threshold
                        if score_threshold is not None
                        else self.default_score_threshold
                    ),
                    with_payload=True,
                    with_vectors=False
                )
                points = search_result.points
            except (AttributeError, TypeError) as e:
                # Fall back to older API (qdrant-client < 1.7.0)
                logger.debug(f"query_points unavailable ({type(e).__name__}), fallback to search API")
                try:
                    search_result = self.client.search(
                        collection_name=target_collection,
                        query_vector=embedding,
                        limit=top_k,
                        query_filter=None,
                        score_threshold=(
                            score_threshold
                            if score_threshold is not None
                            else self.default_score_threshold
                        ),
                        with_payload=True,
                        with_vectors=False
                    )
                    points = search_result
                except Exception as search_error:
                    logger.error(f"Both query_points and search failed: {search_error}", exc_info=True)
                    return []
            
            if points is None:
                logger.debug("No points returned from search")
                return []

            
            results = []
            for point in points:
                result = {
                    "id": point.id,
                    "score": point.score,
                    **point.payload
                }
                results.append(result)
            
            logger.info(f"Vector search found {len(results)} results from collection {target_collection}")
            return results
            
        except Exception as e:
            logger.error(f"Vector search error: {e}", exc_info=True)
            return []
    
    async def health(self) -> Dict[str, Any]:
        """
        Check health of vector store.
        
        Returns:
            Health status
        """
        try:
            if not self.client:
                return {
                    "status": "unhealthy",
                    "reason": "Client not initialized"
                }
            
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections or []]
            
            has_target = self.collection_name in collection_names
            
            return {
                "status": "healthy" if has_target else "degraded",
                "host": self.host,
                "port": self.port,
                "collection": self.collection_name,
                "collection_exists": has_target,
                "available_collections": collection_names
            }
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
