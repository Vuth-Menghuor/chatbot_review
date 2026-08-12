"""
GDCE Calculator Service - Qdrant Client Adapter
================================================
Infrastructure adapter: connects to Qdrant for semantic HS code search.
Duty rates and formulas are served from the calculator's own PostgreSQL (gdce_calculator).
Default host is 'qdrant' (Docker service name) or 'localhost' for local dev.

Qdrant Payload Structure:
{
  "id": "0101.21.00",
  "payload": {
    "hs_code": "0101.21.00",
    "description": "Live horses, asses, mules...",
    "unit": "u",
    "cd_rate": 0,        # Integer 0-100 (NOT decimal)
    "st_rate": 0,
    "vat_rate": 10,
    "et_rate": 0
  }
}

Note: All rates are stored as INTEGERS (0-100), must be divided by 100 for calculations.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class QdrantClientAdapter:
    """Adapter for querying remote Qdrant database for HS codes and duty rates."""

    def __init__(self, host: str = None, port: int = None, collection_name: str = "gdce_hs_code", embedding_model: str = None):
        """
        Initialize Qdrant client.

        Args:
            host: Qdrant server host (default: env QDRANT_HOST or 'qdrant')
            port: Qdrant server port (default: env QDRANT_PORT or 6333)
            collection_name: Qdrant collection name (default: gdce_hs_code)
            embedding_model: Sentence-transformers model for semantic search (default: all-MiniLM-L6-v2)
        """
        self.host = host or os.getenv("QDRANT_HOST", "qdrant")
        self.port = port or int(os.getenv("QDRANT_PORT", 6333))
        self.collection_name = collection_name or os.getenv("QDRANT_DUTY_COLLECTION", "gdce_hs_code")
        self.embedding_model = embedding_model or os.getenv("QDRANT_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self._embedder = None
        self.client = None
        self._connect()

    def _connect(self) -> None:
        """Establish connection to Qdrant."""
        try:
            from qdrant_client import QdrantClient
            self.client = QdrantClient(host=self.host, port=self.port, timeout=5)
            logger.info(f" Connected to Qdrant at {self.host}:{self.port}")
        except ImportError:
            logger.error(" qdrant-client not installed. Run: pip install qdrant-client")
            raise
        except Exception as e:
            logger.error(f" Failed to connect to Qdrant: {e}")
            raise

    def get_duty_rates(self, hs_code: str) -> Optional[Dict[str, Any]]:
        """
        Query Qdrant for duty rates by HS code.
        
        Returns dict with:
            {
                "hs_code": "0102.29.11",
                "description": "Live horses, asses, mules...",
                "unit": "u",
                "cd_rate": 0,        # ALREADY CONVERTED TO DECIMAL
                "st_rate": 0,
                "vat_rate": 0.10,
                "et_rate": 0,
                "source": "qdrant"
            }
        """
        if not self.client:
            logger.warning("Qdrant client not connected")
            return None

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # Query Qdrant by payload filter (hs_code field), not point ID
            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="hs_code",
                            match=MatchValue(value=hs_code),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
            )

            if not results:
                logger.debug(f"HS code {hs_code} not found in Qdrant")
                return None

            point = results[0]
            payload = point.payload

            # Convert rates from integers (0-100) to decimals (0-1.0)
            cd_rate_int = payload.get("cd_rate", 0)
            st_rate_int = payload.get("st_rate", 0)
            vat_rate_int = payload.get("vat_rate", 10)
            et_rate_int = payload.get("et_rate", 0)

            # Convert to decimal
            cd_rate = Decimal(cd_rate_int) / Decimal(100)
            st_rate = Decimal(st_rate_int) / Decimal(100)
            vat_rate = Decimal(vat_rate_int) / Decimal(100)
            et_rate = Decimal(et_rate_int) / Decimal(100)

            return {
                "hs_code": payload.get("hs_code", hs_code),
                "description": payload.get("description", ""),
                "unit": payload.get("unit", "u"),
                "cd_rate": float(cd_rate),
                "st_rate": float(st_rate),
                "vat_rate": float(vat_rate),
                "et_rate": float(et_rate),
                "source": "qdrant"
            }

        except Exception as e:
            logger.error(f"Error querying Qdrant for HS {hs_code}: {e}")
            return None

    def get_hs_code_info(self, hs_code: str) -> Optional[Dict[str, Any]]:
        """
        Get HS code description and unit from Qdrant.
        
        Returns dict with:
            {
                "hs_code": "0102.29.11",
                "description": "Live horses...",
                "unit": "u"
            }
        """
        if not self.client:
            return None

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="hs_code",
                            match=MatchValue(value=hs_code),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
            )

            if not results:
                return None

            payload = results[0].payload
            return {
                "hs_code": payload.get("hs_code", hs_code),
                "description": payload.get("description", ""),
                "unit": payload.get("unit", "u")
            }

        except Exception as e:
            logger.error(f"Error getting HS info from Qdrant: {e}")
            return None

    def _get_embedder(self):
        """Lazy-load sentence-transformers embedder."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer(self.embedding_model)
                logger.info(f"Loaded embedding model: {self.embedding_model}")
            except Exception as e:
                logger.warning(f"Failed to load embedding model '{self.embedding_model}': {e}")
                raise
        return self._embedder

    def _do_search(self, vector: list, limit: int):
        """Version-agnostic vector search (query_points for v1.10+, search for v1.7)."""
        if hasattr(self.client, "query_points"):
            resp = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=limit,
                with_payload=True,
            )
            return resp.points if resp else []
        return self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )

    def search_by_description(self, query: str, top_k: int = None):
        """
        Semantic search by description using Qdrant vector search.

        Args:
            query: Product description (e.g., "car", "petroleum")
            top_k: Number of candidates to return. If None, returns a single
                   (hs_code, score) tuple for legacy compatibility.

        Returns:
            - (hs_code, score) tuple when top_k is None
            - List[dict] when top_k is provided, each dict has:
                {"hs_code": str, "description": str, "score": float, "source": "qdrant"}
            - None or [] on failure
        """
        if not self.client:
            logger.warning("Qdrant client not connected")
            return None

        try:
            embedder = self._get_embedder()
            vector = embedder.encode(query, convert_to_tensor=False).tolist()

            limit = top_k or 1
            results = self._do_search(vector, limit)

            if not results:
                logger.debug(f"No Qdrant semantic matches for '{query}'")
                return None

            if top_k is None:
                payload = results[0].payload
                return (payload.get("hs_code"), float(results[0].score))
            else:
                return [
                    {
                        "hs_code": r.payload.get("hs_code") if r.payload else None,
                        "description": r.payload.get("description") if r.payload else None,
                        "score": float(r.score),
                        "source": "qdrant",
                    }
                    for r in results
                ]
        except Exception as e:
            logger.warning(f"Qdrant semantic search failed for '{query}': {e}")
            return None

    def get_candidates(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Get HS code candidates via semantic search.

        Returns a list of candidate dicts (empty list on failure).
        """
        return self.search_by_description(query, top_k=limit) or []

    def search_by_prefix_and_description(
        self,
        prefix: str,
        description: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Semantic search filtered by HS code prefix.

        Performs a vector search by description, then client-side filters
        results to only those whose hs_code starts with the given prefix.

        Args:
            prefix: HS prefix (e.g. "7204")
            description: Product description for semantic ranking
            top_k: Number of candidates before filtering

        Returns:
            List of matching candidates, ranked by semantic score.
        """
        if not self.client:
            logger.warning("Qdrant client not connected")
            return []

        try:
            embedder = self._get_embedder()
            vector = embedder.encode(description, convert_to_tensor=False).tolist()

            # Search with a larger top_k because filtering will reduce results
            search_limit = max(top_k * 5, 50)
            results = self._do_search(vector, search_limit)

            if not results:
                logger.debug(f"No Qdrant matches for '{description}'")
                return []

            clean_prefix = prefix.replace(".", "")
            filtered = []
            for r in results:
                hs = r.payload.get("hs_code") if r.payload else None
                if hs and hs.replace(".", "").startswith(clean_prefix):
                    filtered.append({
                        "hs_code": hs,
                        "description": r.payload.get("description", ""),
                        "score": float(r.score),
                        "source": "qdrant",
                    })

            # Return top_k after filtering
            filtered.sort(key=lambda x: x["score"], reverse=True)
            return filtered[:top_k]

        except Exception as e:
            logger.warning(f"Qdrant prefix+description search failed: {e}")
            return []

    def get_prefix_candidates(
        self,
        prefix: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Get all HS codes starting with a given prefix via payload scroll.

        Args:
            prefix: HS prefix (e.g. "7204")
            limit: Maximum number of results

        Returns:
            List of candidate dicts with hs_code and description.
        """
        if not self.client:
            return []

        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # Qdrant does not support prefix payload filters natively.
            # We scroll all points and filter client-side.
            results, _ = self.client.scroll(
                collection_name=self.collection_name,
                limit=limit * 10,  # Over-fetch for client-side filtering
                with_payload=True,
            )

            clean_prefix = prefix.replace(".", "")
            candidates = []
            for point in results:
                hs = point.payload.get("hs_code", "") if point.payload else ""
                if hs.replace(".", "").startswith(clean_prefix):
                    candidates.append({
                        "hs_code": hs,
                        "description": point.payload.get("description", ""),
                        "source": "qdrant",
                    })

            return candidates[:limit]
        except Exception as e:
            logger.warning(f"Qdrant prefix candidate search failed: {e}")
            return []

    def check_health(self) -> Dict[str, Any]:
        """Check Qdrant connection health."""
        try:
            if self.client:
                collections = self.client.get_collections()
                collection_names = [c.name for c in collections.collections]
                connected = self.collection_name in collection_names
                return {
                    "ok": connected,
                    "server": f"{self.host}:{self.port}",
                    "collection_exists": connected,
                    "collection_name": self.collection_name,
                    "message": "Connected" if connected else f"Collection {self.collection_name} not found"
                }
            return {"ok": False, "message": "Client not initialized"}
        except Exception as e:
            return {"ok": False, "message": str(e)}
