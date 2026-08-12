"""
Document Repository — Infrastructure Layer.

Optional structured data access layer for keyword-based document search
against external backends (e.g. OpenSearch, Elasticsearch). When no
search client is configured, all methods return empty lists — the service
falls back to pure semantic (vector) search.

This is a stub for future integration; currently unused in the default
deployment.
"""

import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class DocumentRepository:
    """
    Data access layer for documents.

    Responsibilities:
    - Keyword-based document search
    - Optional structured search integration
    - Health checks
    """

    def __init__(self, db_pool=None, search_client=None):
        """
        Initialize document repository.

        Args:
            db_pool: Database connection pool
            search_client: Search engine client (e.g., OpenSearch)
        """
        self.db_pool = db_pool
        self.search_client = search_client
        self._missing_search_client_warned = False

    async def search_by_keywords(
        self,
        keywords: List[str],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search documents by keywords.

        Args:
            keywords: List of search keywords
            limit: Maximum results

        Returns:
            List of documents
        """
        if not keywords:
            return []

        try:
            if not self.search_client:
                if not self._missing_search_client_warned:
                    logger.warning("Search client not configured")
                    self._missing_search_client_warned = True
                return []

            # Build keyword search query
            query = " AND ".join(keywords)

            results = await self._search_documents(query, limit)
            logger.info(f"Found {len(results)} documents for keywords: {keywords}")
            return results

        except Exception as e:
            logger.error(f"Keyword search error: {e}")
            return []

    async def search_by_query(
        self,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search documents by query.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of documents
        """
        try:
            if not self.search_client:
                return []

            results = await self._search_documents(query, limit)
            logger.info(f"Found {len(results)} documents for query: {query}")
            return results

        except Exception as e:
            logger.error(f"Query search error: {e}")
            return []

    async def get_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document or None
        """
        try:
            if not self.search_client:
                return None

            result = await self._get_document(doc_id)
            return result

        except Exception as e:
            logger.error(f"Get document error: {e}")
            return None

    async def _search_documents(
        self,
        query: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Internal method to search documents.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of documents
        """
        # This would be implemented based on the actual search backend
        # (OpenSearch, Elasticsearch, PostgreSQL full-text search, etc.)
        logger.debug(f"Searching documents with query: {query}")
        return []

    async def _get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        Internal method to get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document or None
        """
        logger.debug(f"Getting document: {doc_id}")
        return None

    async def health(self) -> Dict[str, Any]:
        """
        Check health of repository.

        Returns:
            Health status
        """
        try:
            status = {"status": "healthy", "components": {}}

            # Check database pool
            if self.db_pool:
                try:
                    async with self.db_pool.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                    status["components"]["database"] = {"status": "healthy"}
                except Exception as e:
                    status["components"]["database"] = {"status": "unhealthy", "error": str(e)}
                    status["status"] = "degraded"

            # Check search client
            if self.search_client:
                try:
                    health = await self.search_client.health()
                    status["components"]["search"] = health
                except Exception as e:
                    status["components"]["search"] = {"status": "unhealthy", "error": str(e)}
                    status["status"] = "degraded"

            return status

        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
