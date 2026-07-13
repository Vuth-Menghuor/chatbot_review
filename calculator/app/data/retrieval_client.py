"""
GDCE Calculator Service - Retrieval Service Client
===================================================
HTTP adapter for the Retrieval microservice (HS code auto-lookup).

Phase 2 TODO:
    - Move lookup_hs_code_from_product() from api.py into this file
    - Read RETRIEVAL_SERVICE_URL from core.config.get_settings()
    - Add retry logic with exponential back-off
    - Add circuit-breaker to avoid cascading failures
"""

# Placeholder — retrieval HTTP client will be moved here in Phase 2
# See services/calculator/api.py → async def lookup_hs_code_from_product()
