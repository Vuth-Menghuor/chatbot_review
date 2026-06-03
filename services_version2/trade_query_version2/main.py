"""
GDCE Trade Query Service - Uvicorn Entrypoint
=============================================
Run this file with:

    python -m services_version2.trade_query_version2.main

Or use uvicorn directly:

    uvicorn services_version2.trade_query_version2.main:app --host 127.0.0.1 --port 8004 --reload
"""

import logging
import uvicorn
from .app import app  # Export app for uvicorn module loading
from .config import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    """Run the trade query service."""
    settings = get_settings()
    host = settings.host
    port = settings.port
    
    logger.info(f"Starting Trade Query Service on {host}:{port}")
    logger.info(f"API Documentation: http://{host}:{port}/docs")
    
    # Run uvicorn
    # Note: when reload=True, uvicorn must be passed the import string rather than the app object.
    uvicorn.run(
        "services_version2.trade_query_version2.app:app",
        host=host,
        port=port,
        reload=False,  # Can set reload to True in dev environments
        log_level="info",
    )


if __name__ == "__main__":
    main()
