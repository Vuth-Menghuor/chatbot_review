"""
GDCE Calculator Service - Uvicorn Entrypoint
=============================================
Run this file with:

    python -m calculator.main

Or use uvicorn directly (from repo root with PYTHONPATH set):

    uvicorn calculator.main:app --host 127.0.0.1 --port 8002 --reload

Version: 2.0  (microservice skeleton)
Last Updated: 2026-03-25
"""

from __future__ import annotations

import logging
import os

import uvicorn

# Use relative imports since this will be run as a package module
from .app.main import create_app

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WSGI / ASGI app object
# Exposed at module level so uvicorn can import it:
#   uvicorn calculator.main:app
# ---------------------------------------------------------------------------
app = create_app()


# ---------------------------------------------------------------------------
# Direct-run entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = os.getenv("CALCULATOR_HOST", "127.0.0.1")
    port = int(os.getenv("CALCULATOR_PORT", "8002"))
    reload = os.getenv("CALCULATOR_RELOAD", "false").lower() == "true"

    logger.info("Starting GDCE Calculator Service on %s:%s", host, port)

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )
