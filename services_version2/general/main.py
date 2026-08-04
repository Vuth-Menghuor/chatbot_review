"""
Entry point for General Retrieval Service
Port: 8005

Run with:
  python -m services_version2.general.main

Or:
  uvicorn services_version2.general.app.main:app --reload --host 127.0.0.1 --port 8005

Architecture:
  - Orchestrator (8001) routes general/FAQ/definition/policy queries here
  - This service is independent from the HS-code retrieval service (8003)
    and uses its own dedicated Qdrant instance (default port 6334)
"""

import logging
import uvicorn
from .app.main import app  # Export app for uvicorn module loading
from .app.config.config import get_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run the general retrieval service."""
    config = get_config()
    host = config.host
    port = config.port
    reload = config.reload
    workers = config.workers

    logger.info(f"Starting General Retrieval Service on {host}:{port}")
    logger.info(f"Port: 8005 (Handles: general/FAQ/definition/policy queries)")
    logger.info(f"API Documentation: http://{host}:{port}/docs")

    # Run uvicorn
    uvicorn.run(
      "services_version2.general.app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers,
        log_level="info"
    )


if __name__ == "__main__":
    main()
