"""
Entry point for the General Retrieval Service.

This service handles general / FAQ / definition / policy-style queries that
are NOT HS-code classification (that is handled by the retrieval service on
port 8003). It uses its own dedicated Qdrant instance (default port 6334)
against the ``gdce_docs`` collection.

Port: 8005

Usage
-----
    python -m services_version2.general.main

Or directly via Uvicorn::

    uvicorn services_version2.general.app.main:app --reload --host 127.0.0.1 --port 8005

Architecture Context
--------------------
The upstream Orchestrator (port 8001) routes general / FAQ / definition /
policy queries to this service. The HS-code retrieval service (port 8003)
handles ``HS_CODE_LOOKUP`` intents against its own Qdrant instance — this
service never touches the ``gdce_hs_code`` collection.
"""

import logging
import uvicorn

# Application instance — imported here so ``uvicorn`` can reference the
# module path ``services_version2.general.app.main:app``.
from .app.main import app
from .app.config.config import get_config

# ---------------------------------------------------------------------------
# Logging — plain stdlib configuration; Uvicorn will layer its own handlers
# on top when run programmatically.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """
    Bootstrap and run the general retrieval service via Uvicorn.

    Reads configuration from the environment / ``.env`` file, then starts
    the ASGI server. When ``reload`` is enabled, ``workers`` is forced to 1
    because Uvicorn's hot-reload is incompatible with multi-worker mode.
    """
    config = get_config()
    host = config.host
    port = config.port
    reload = config.reload
    workers = config.workers

    logger.info(f"Starting General Retrieval Service on {host}:{port}")
    logger.info(f"Port: 8005 (Handles: general/FAQ/definition/policy queries)")
    logger.info(f"API Documentation: http://{host}:{port}/docs")

    uvicorn.run(
        "services_version2.general.app.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers,  # reload + workers > 1 is unsupported
        log_level="info"
    )


if __name__ == "__main__":
    main()
