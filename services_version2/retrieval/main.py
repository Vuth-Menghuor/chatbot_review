"""
Entry point for the Retrieval Service (v2).

This service is responsible for HS code classification against the
``gdce_hs_code`` Qdrant collection. It exposes two primary endpoints:

    - ``POST /hs-code-candidates`` — semantic + structured retrieval with
      optional Gemini-powered ranked answer generation.
    - ``POST /hs-code-ranked``   — simplified ranked HS code list.

Port: 8003

Usage
-----
    python -m services_version2.retrieval.main

Or directly via Uvicorn::

    uvicorn services_version2.retrieval.app.app:app --reload --host 127.0.0.1 --port 8003

Architecture Context
--------------------
The upstream Orchestrator (port 8001) routes ``HS_CODE_LOOKUP`` intents to
this service. General / FAQ / definition / policy queries are handled by a
separate general-retrieval service (port 8005) against a different Qdrant
collection (``gdce_docs``) — this service never touches that collection.
"""

import logging
import uvicorn

# Application instance — imported here so ``uvicorn`` can reference the
# module path ``services_version2.retrieval.app.app:app``.
from services_version2.retrieval.app.app import app
from services_version2.retrieval.config import get_config

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
    Bootstrap and run the retrieval service via Uvicorn.

    Reads configuration from the environment / ``.env`` file, then starts
    the ASGI server. When ``reload`` is enabled, ``workers`` is forced to 1
    because Uvicorn's hot-reload is incompatible with multi-worker mode.
    """
    config = get_config()
    host = config.host
    port = config.port
    reload = config.reload
    workers = config.workers

    logger.info("Starting Retrieval Service (v2) on %s:%s", host, port)
    logger.info("Port: 8003  |  Intent: HS_CODE_LOOKUP")
    logger.info("API Documentation: http://%s:%s/docs", host, port)

    uvicorn.run(
        "services_version2.retrieval.app.app:app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers,  # reload + workers > 1 is unsupported
        log_level="info",
    )


if __name__ == "__main__":
    main()