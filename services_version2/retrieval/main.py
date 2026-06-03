"""
Entry point for Retrieval service v2
Port: 8003 (as per GDCE services architecture)

Run with: 
  python -m services_version2.retrieval.main
  
Or: 
  uvicorn services_version2.retrieval.app:app --reload --host 127.0.0.1 --port 8003

Architecture:
  - Orchestrator (8001) routes HS_CODE_LOOKUP, DEFINITION, POLICY_INQUIRY, GENERAL intents here
  - See: services_version2/orchestrator/ORCHESTRATOR_V2_ARCHITECTURE.md
"""

import logging
import uvicorn
from .app import app  # Export app for uvicorn module loading
from .config import get_config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run the retrieval service."""
    config = get_config()
    host = config.host
    port = config.port
    reload = config.reload
    workers = config.workers
    
    logger.info(f"Starting Retrieval Service (v2) on {host}:{port}")
    logger.info(f"Port: 8003 (Handles: HS_CODE_LOOKUP, DEFINITION, POLICY_INQUIRY, GENERAL intents)")
    logger.info(f"API Documentation: http://{host}:{port}/docs")
    
    # Run uvicorn
    uvicorn.run(
        "services_version2.retrieval.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers,
        log_level="info"
    )


if __name__ == "__main__":
    main()
