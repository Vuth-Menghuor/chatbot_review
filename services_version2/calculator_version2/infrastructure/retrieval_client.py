"""
GDCE Calculator Service - Retrieval Service Client
===================================================
HTTP adapter for the Retrieval microservice (HS code auto-lookup).
"""

from __future__ import annotations

import logging
import httpx
from typing import Optional, Dict, Any
from ..config import get_settings

logger = logging.getLogger(__name__)


class RetrievalClient:
    """
    HTTP client for the GDCE Retrieval microservice.
    Used to lookup HS codes from product descriptions.
    """

    def __init__(self, base_url: Optional[str] = None):
        settings = get_settings()
        self.base_url = base_url or settings.retrieval_service_url or "http://127.0.0.1:8003"
        # Strip trailing slash if present
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]
        logger.info(f"RetrievalClient initialized with base URL: {self.base_url}")

    async def lookup_hs_code(self, query: str, top_k: int = 5) -> Optional[str]:
        """
        Lookup HS code from product description using retrieval service.
        Returns the primary HS code string if found, otherwise None.
        """
        if not self.base_url:
            logger.warning("Retrieval service URL is not configured. Skipping lookup.")
            return None

        url = f"{self.base_url}/v1/hs-code-candidates"
        payload = {
            "query": query,
            "top_k": top_k,
            "generate_answer": False,
            "collection": "gdce_hs_code",
            "hs_mode": "best",
            "intent": "hs_code_lookup"
        }

        try:
            logger.info(f"Looking up HS code for query: '{query}' via retrieval service url: {url}")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                # Check for primary code in hs_validation
                hs_validation = data.get("hs_validation") or {}
                primary_code = hs_validation.get("primary_code")

                if primary_code:
                    logger.info(f"Found primary HS code in hs_validation: {primary_code}")
                    return str(primary_code)

                # Fallback: check documents
                documents = data.get("documents") or []
                if documents:
                    first_doc = documents[0] or {}
                    metadata = first_doc.get("metadata") or {}
                    code = metadata.get("hs_code") or first_doc.get("id")
                    if code:
                        logger.info(f"Found HS code in document metadata/ID: {code}")
                        return str(code)

                logger.warning(f"No HS code found in retrieval response for query: '{query}'")
                return None

        except Exception as e:
            logger.error(f"Failed to lookup HS code from retrieval service: {e}")
            return None
