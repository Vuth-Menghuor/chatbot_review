"""
Main entry point for orchestrator service v2
"""

import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Use relative imports since this will be run as a package module with: python -m services_version2.orchestrator.main
from .config import get_config
from .app import app  # Export app for uvicorn module loading

logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    import uvicorn
    
    config = get_config()
    
    logger.info("=" * 60)
    logger.info("GDCE Orchestrator Service v2")
    logger.info("=" * 60)
    logger.info(f"Starting service on {config.host}:{config.port}")
    logger.info(f"Log Level: {config.log_level}")
    logger.info(f"Reload: {config.reload}")
    logger.info(f"Workers: {config.workers}")
    logger.info("=" * 60)
    
    uvicorn.run(
        "services_version2.orchestrator.app:app",
        host=config.host,
        port=config.port,
        reload=config.reload,
        workers=1 if config.reload else config.workers,
        log_level=config.log_level.lower(),
        access_log=True,
    )


if __name__ == "__main__":
    main()
