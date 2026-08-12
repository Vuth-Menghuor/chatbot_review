"""
Vector Store Client — Infrastructure Layer.

Wraps the Qdrant vector database for semantic (dense-vector) search
against HS code collections. Supports both the modern ``query_points``
API and the legacy ``search`` API for backward compatibility with
different ``qdrant-client`` versions.

Design Notes
------------
- The underlying ``QdrantClient`` is synchronous; search calls are
  expected to be wrapped in ``asyncio.to_thread`` by callers.
- Both ``query_points`` (Qdrant ≥1.7) and ``search`` (legacy) APIs are
  tried, with automatic fallback — useful during SDK migrations.
"""

import logging
from typing import Optional, Dict, Any, List
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)


class VectorStoreClient:
    """
    Client for the Qdrant vector database.

    Responsibilities
    ----------------
    - Semantic (dense-vector) search with optional score thresholding.
    - Collection-aware search (override the default collection per request).
    - Health checks that report collection existence and availability.

    Parameters
    ----------
    host : str
        Qdrant server hostname.
    port : int
        Qdrant server gRPC / REST port (typically 6333).
    collection_name : str
        Default collection to query.
    timeout : float
        Connection / request timeout in seconds.
    api_key : str
        Optional Qdrant API key for authenticated instances.
    default_score_threshold : Optional[float]
        Default minimum relevance score; results below this are dropped.
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
                timeout=timeout,
            )
            logger.info("Connected to Qdrant at %s:%s", host, port)
        except Exception as e:
            logger.error("Failed to connect to Qdrant: %s", e)
            self.client = None

    async def search(
        self,
        embedding: List[float],
        top_k: int = 10,
        score_threshold: Optional[float] = None,
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search the vector store by dense embedding.

        Parameters
        ----------
        embedding : List[float]
            Query embedding vector.
        top_k : int
            Maximum number of results.
        score_threshold : Optional[float]
            Per-request score floor; overrides ``default_score_threshold``.
        collection_name : Optional[str]
            Override the default collection for this query.

        Returns
        -------
        List[Dict[str, Any]]
            Each dict has at minimum ``id``, ``score``, and all payload
            fields. Empty list on any failure.
        """
        try:
            if not self.client:
                logger.error("Vector store client not initialized")
                return []

            target_collection = collection_name or self.collection_name
            effective_threshold = (
                score_threshold
                if score_threshold is not None
                else self.default_score_threshold
            )

            points = None
            # --- Try modern query_points API (Qdrant ≥ 1.7) ---------------
            try:
                search_result = self.client.query_points(
                    collection_name=target_collection,
                    query=embedding,
                    limit=top_k,
                    score_threshold=effective_threshold,
                    with_payload=True,
                    with_vectors=False,
                )
                points = search_result.points
            except (AttributeError, TypeError) as e:
                # Fall back to legacy ``search`` API.
                logger.debug(
                    "query_points unavailable (%s), fallback to search API",
                    type(e).__name__,
                )
                try:
                    search_result = self.client.search(
                        collection_name=target_collection,
                        query_vector=embedding,
                        limit=top_k,
                        query_filter=None,
                        score_threshold=effective_threshold,
                        with_payload=True,
                        with_vectors=False,
                    )
                    points = search_result
                except Exception as search_error:
                    logger.error(
                        "Both query_points and search failed: %s",
                        search_error,
                        exc_info=True,
                    )
                    return []

            if points is None:
                logger.debug("No points returned from search")
                return []

            # Normalise into a consistent result shape.
            results = []
            for point in points:
                result = {
                    "id": point.id,
                    "score": point.score,
                    **point.payload,
                }
                results.append(result)

            logger.info(
                "Vector search found %d results from collection %s",
                len(results),
                target_collection,
            )
            return results

        except Exception as e:
            logger.error("Vector search error: %s", e, exc_info=True)
            return []

    async def health(self) -> Dict[str, Any]:
        """
        Check vector store health.

        Reports whether the client is connected, whether the configured
        collection exists, and lists all available collections for
        operator visibility.
        """
        try:
            if not self.client:
                return {"status": "unhealthy", "reason": "Client not initialized"}

            collections = self.client.get_collections()
            collection_names = [
                c.name for c in (collections.collections or [])
            ]

            has_target = self.collection_name in collection_names

            return {
                "status": "healthy" if has_target else "degraded",
                "host": self.host,
                "port": self.port,
                "collection": self.collection_name,
                "collection_exists": has_target,
                "available_collections": collection_names,
            }

        except Exception as e:
            logger.error("Health check error: %s", e)
            return {"status": "unhealthy", "error": str(e)}