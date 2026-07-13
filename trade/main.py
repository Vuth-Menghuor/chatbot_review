"""
GDCE Trade Query Service - Uvicorn Entrypoint
=============================================
Run this file with:

    python main.py

Or use uvicorn directly:

    uvicorn app.main:app --host 127.0.0.1 --port 8004 --reload
"""

import logging
import uvicorn
from app.main import app  # Export app for uvicorn module loading
from app.core.config import get_settings

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
        "app.main:app",
        host=host,
        port=port,
        reload=False,  # Can set reload to True in dev environments
        log_level="info",
    )


if __name__ == "__main__":
    main()
