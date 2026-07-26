"""
Configuration Management for Retrieval Service
Provides centralized, environment-independent configuration.

Only fields actually consumed by the HS-code candidate/ranked endpoints
are kept — OpenSearch, vLLM, Postgres, and rate-limit settings were
removed along with the subsystems that used them.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


class RetrievalConfig:
    """Centralized configuration for retrieval service."""

    def __init__(self, env_file: Optional[Path] = None):
        service_root = Path(__file__).resolve().parent
        default_env = service_root / ".env"

        if env_file and env_file.exists():
            load_dotenv(env_file)
        elif default_env.exists():
            load_dotenv(default_env)
        else:
            load_dotenv()

        self._setup_paths()
        self._load_service_config()

    def _setup_paths(self):
        self.service_root = Path(__file__).resolve().parent
        self.repo_root = self.service_root.parent.parent.parent
        self.configs_dir = self.repo_root / "configs"
        self.data_dir = self.repo_root / "data"
        self.model_dir = self.repo_root / "model"

    def _load_service_config(self):
        # API Server Configuration
        self.host = os.environ.get("RETRIEVAL_HOST") or "127.0.0.1"
        self.port = int(os.environ.get("RETRIEVAL_PORT") or 8003)
        self.service_host = os.environ.get("RETRIEVAL_SERVICE_HOST") or "127.0.0.1"
        self.service_port = int(os.environ.get("RETRIEVAL_SERVICE_PORT") or 8003)
        self.reload = (os.environ.get("RETRIEVAL_RELOAD") or "false").lower() == "true"
        self.workers = int(os.environ.get("RETRIEVAL_WORKERS") or 4)

        # Vector Store Configuration (HS code collection only)
        self.qdrant_host = os.environ.get("QDRANT_HOST") or "localhost"
        self.qdrant_port = int(os.environ.get("QDRANT_PORT") or 6333)
        self.qdrant_api_key = os.environ.get("QDRANT_API_KEY") or ""
        self.qdrant_hs_code_collection = os.environ.get("QDRANT_HS_CODE_COLLECTION") or "gdce_hs_code"
        self.qdrant_timeout = float(os.environ.get("QDRANT_TIMEOUT") or 30.0)

        # Embedding Configuration
        self.query_embedding_model = os.environ.get("QUERY_EMBEDDING_MODEL") or "all-MiniLM-L6-v2"

        # Retrieval Configuration
        self.top_k_default = int(os.environ.get("TOP_K_DEFAULT") or 10)
        self.top_k_max = int(os.environ.get("TOP_K_MAX") or 50)

        # Gemini LLM Configuration (answer generation)
        self.gemini_api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        self.gemini_model = os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash"
        self.gemini_enabled = (os.environ.get("GEMINI_ENABLED") or "true").lower() == "true"

        # CORS Configuration
        allowed_origins = os.environ.get("ALLOWED_ORIGINS") or "http://localhost:3000,http://localhost:8001"
        self.allowed_origins = [origin.strip() for origin in allowed_origins.split(",")]

        # Logging Configuration
        self.log_level = os.environ.get("LOG_LEVEL") or "INFO"

        # Redis cache Configuration (HS corpus caching)
        self.redis_host = os.environ.get("REDIS_HOST") or "localhost"
        self.redis_port = int(os.environ.get("REDIS_PORT") or 6381)
        self.redis_corpus_ttl = int(os.environ.get("REDIS_CORPUS_TTL") or 21600)  # 6h

    def get_retrieval_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def validate(self) -> bool:
        if not self.qdrant_host:
            logger.warning("Config qdrant_host is not set")
        return True

    def to_dict(self) -> dict:
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
        }


_config: Optional[RetrievalConfig] = None


def get_config(env_file: Optional[Path] = None) -> RetrievalConfig:
    """Get or create the global configuration instance."""
    global _config
    if _config is None:
        _config = RetrievalConfig(env_file)
        _config.validate()
        logger.info(f"Retrieval configuration loaded: {_config.to_dict()}")
    return _config


def reset_config():
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None