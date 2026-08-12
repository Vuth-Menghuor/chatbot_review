"""
Configuration Management for the Retrieval Service.

Provides a centralized, environment-independent ``RetrievalConfig`` object
that reads all settings from environment variables (with sensible defaults)
via ``python-dotenv``. Only fields actually consumed by the HS-code
candidate / ranked endpoints are kept — OpenSearch, vLLM, Postgres, and
rate-limit settings were removed along with the subsystems that used them.

Usage
-----
    from app.config import get_config

    config = get_config()
    print(config.qdrant_host)
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


class RetrievalConfig:
    """
    Centralized, read-only configuration for the retrieval service.

    All values are derived from environment variables at construction time.
    The singleton ``get_config()`` helper should be used to obtain the
    shared instance.

    Environment Variables
    ---------------------
    RETRIEVAL_HOST / RETRIEVAL_PORT
        Bind address for the Uvicorn server.
    QDRANT_HOST / QDRANT_PORT / QDRANT_API_KEY
        Connection details for the Qdrant vector database.
    QDRANT_HS_CODE_COLLECTION
        Name of the Qdrant collection holding HS code documents.
    QUERY_EMBEDDING_MODEL
        HuggingFace sentence-transformers model name.
    GEMINI_API_KEY / GEMINI_MODEL / GEMINI_ENABLED
        Google Generative AI (Gemini) settings for answer generation.
    REDIS_HOST / REDIS_PORT / REDIS_CORPUS_TTL
        Redis cache connection and HS-corpus TTL (seconds).
    ALLOWED_ORIGINS
        Comma-separated list of CORS-allowed origins.
    LOG_LEVEL
        Standard Python log level name.
    GDCE_TARIFF_SEARCH_URL
        Public URL for the GDCE tariff lookup page (shown in responses).
    """

    def __init__(self, env_file: Optional[Path] = None):
        # Resolve the .env file relative to this config module's directory.
        service_root = Path(__file__).resolve().parent
        default_env = service_root / ".env"

        if env_file and env_file.exists():
            load_dotenv(env_file)
        elif default_env.exists():
            load_dotenv(default_env)
        else:
            load_dotenv()  # fall back to cwd / project-root search

        self._setup_paths()
        self._load_service_config()

    # ------------------------------------------------------------------
    # Path helpers (reserved for future use — currently informational)
    # ------------------------------------------------------------------

    def _setup_paths(self):
        """Compute canonical filesystem paths relative to this module."""
        self.service_root = Path(__file__).resolve().parent
        self.repo_root = self.service_root.parent.parent.parent
        self.configs_dir = self.repo_root / "configs"
        self.data_dir = self.repo_root / "data"
        self.model_dir = self.repo_root / "model"

    # ------------------------------------------------------------------
    # Environment variable loading
    # ------------------------------------------------------------------

    def _load_service_config(self):
        """Read every configuration value from the environment."""

        # --- API Server -------------------------------------------------
        self.host = os.environ.get("RETRIEVAL_HOST") or "127.0.0.1"
        self.port = int(os.environ.get("RETRIEVAL_PORT") or 8003)
        self.service_host = os.environ.get("RETRIEVAL_SERVICE_HOST") or "127.0.0.1"
        self.service_port = int(os.environ.get("RETRIEVAL_SERVICE_PORT") or 8003)
        self.reload = (
            os.environ.get("RETRIEVAL_RELOAD") or "false"
        ).lower() == "true"
        self.workers = int(os.environ.get("RETRIEVAL_WORKERS") or 4)

        # --- Qdrant Vector Store (HS code collection only) ---------------
        self.qdrant_host = os.environ.get("QDRANT_HOST") or "localhost"
        self.qdrant_port = int(os.environ.get("QDRANT_PORT") or 6333)
        self.qdrant_api_key = os.environ.get("QDRANT_API_KEY") or ""
        self.qdrant_hs_code_collection = (
            os.environ.get("QDRANT_HS_CODE_COLLECTION") or "gdce_hs_code"
        )
        self.qdrant_timeout = float(os.environ.get("QDRANT_TIMEOUT") or 30.0)

        # --- Embeddings --------------------------------------------------
        self.query_embedding_model = (
            os.environ.get("QUERY_EMBEDDING_MODEL") or "all-MiniLM-L6-v2"
        )

        # --- Retrieval ---------------------------------------------------
        self.top_k_default = int(os.environ.get("TOP_K_DEFAULT") or 10)
        self.top_k_max = int(os.environ.get("TOP_K_MAX") or 50)

        # --- Gemini LLM --------------------------------------------------
        self.gemini_api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        self.gemini_model = os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash"
        self.gemini_enabled = (
            os.environ.get("GEMINI_ENABLED") or "true"
        ).lower() == "true"

        # --- CORS --------------------------------------------------------
        allowed_origins = (
            os.environ.get("ALLOWED_ORIGINS")
            or "http://localhost:3000,http://localhost:8001"
        )
        self.allowed_origins = [
            origin.strip() for origin in allowed_origins.split(",")
        ]

        # --- Logging -----------------------------------------------------
        self.log_level = os.environ.get("LOG_LEVEL") or "INFO"

        # --- Reference URLs ----------------------------------------------
        self.gdce_tariff_search_url = (
            os.environ.get("GDCE_TARIFF_SEARCH_URL")
            or "https://customs.gov.kh/en/publications/14037-customs-tariff-of-cambodia-km-2022"
        )

        # --- Redis Cache -------------------------------------------------
        self.redis_host = os.environ.get("REDIS_HOST") or "localhost"
        self.redis_port = int(os.environ.get("REDIS_PORT") or 6381)
        self.redis_corpus_ttl = int(
            os.environ.get("REDIS_CORPUS_TTL") or 21600
        )  # 6 hours

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def get_retrieval_url(self) -> str:
        """Return the full HTTP URL for this service (e.g. for health checks)."""
        return f"http://{self.host}:{self.port}"

    def validate(self) -> bool:
        """
        Perform lightweight configuration validation.

        Logs warnings for missing critical settings but does **not** raise —
        the service is designed to start degraded rather than refuse to start.
        """
        if not self.qdrant_host:
            logger.warning("Config qdrant_host is not set")
        return True

    def to_dict(self) -> dict:
        """
        Return a sanitised dictionary of configuration values suitable for
        logging (secrets are represented as booleans, never exposed).
        """
        return {
            "host": self.host,
            "port": self.port,
            "qdrant_host": self.qdrant_host,
            "qdrant_port": self.qdrant_port,
            "qdrant_hs_code_collection": self.qdrant_hs_code_collection,
            "top_k_default": self.top_k_default,
            "gemini_enabled": self.gemini_enabled,
            "gemini_configured": bool(self.gemini_api_key),
            "log_level": self.log_level,
            "gdce_tariff_search_url": self.gdce_tariff_search_url,
        }


# ---------------------------------------------------------------------------
# Singleton — created once on first access, shared for the process lifetime.
# ---------------------------------------------------------------------------
_config: Optional[RetrievalConfig] = None


def get_config(env_file: Optional[Path] = None) -> RetrievalConfig:
    """
    Return the global ``RetrievalConfig`` singleton, creating it on first call.

    Parameters
    ----------
    env_file : Optional[Path]
        Path to a ``.env`` file. Only honoured on the **first** call;
        subsequent calls return the already-loaded instance.

    Returns
    -------
    RetrievalConfig
    """
    global _config
    if _config is None:
        _config = RetrievalConfig(env_file)
        _config.validate()
        logger.info("Retrieval configuration loaded: %s", _config.to_dict())
    return _config


def reset_config():
    """
    Reset the global config singleton so the next call to ``get_config()``
    re-reads the environment. Primarily useful in test suites.
    """
    global _config
    _config = None