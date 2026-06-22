"""
Configuration Management for General Retrieval Service
Provides centralized, environment-independent configuration.

This service is intentionally separate from the HS-code-focused retrieval
service (port 8003). It runs against its own Qdrant instance so that
general/FAQ/definition/policy document growth never competes with or
pollutes HS code vector search.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)


class GeneralConfig:
    """
    Centralized configuration for the general retrieval service.
    Loads from environment variables with sensible defaults.
    """

    def __init__(self, env_file: Optional[Path] = None):
        # Load environment variables (prefer explicit file, then service-local .env, then default search)
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
        """Set up repository and service paths."""
        self.service_root = Path(__file__).resolve().parent
        self.repo_root = self.service_root.parent.parent.parent
        self.configs_dir = self.repo_root / "configs"
        self.data_dir = self.repo_root / "data"
        self.model_dir = self.repo_root / "model"

    def _load_service_config(self):
        """Load service-specific configuration."""
        # API Server Configuration
        self.host = os.environ.get("GENERAL_HOST") or "127.0.0.1"
        self.port = int(os.environ.get("GENERAL_PORT") or 8005)
        self.service_host = os.environ.get("GENERAL_SERVICE_HOST") or "127.0.0.1"
        self.service_port = int(os.environ.get("GENERAL_SERVICE_PORT") or 8005)
        self.reload = (os.environ.get("GENERAL_RELOAD") or "false").lower() == "true"
        self.workers = int(os.environ.get("GENERAL_WORKERS") or 4)

        # Vector Store Configuration — dedicated Qdrant instance, separate from
        # the retrieval service (8003) which uses port 6333.
        #   - Docker Compose (internal network): QDRANT_HOST=qdrant-general, QDRANT_PORT=6333
        #   - Local / non-Docker runs:           QDRANT_HOST=localhost,      QDRANT_PORT=6334
        self.qdrant_host = os.environ.get("QDRANT_HOST") or "localhost"
        self.qdrant_port = int(os.environ.get("QDRANT_PORT") or 6334)
        self.qdrant_api_key = os.environ.get("QDRANT_API_KEY") or ""

        # General documents collection (FAQ / definitions / policy / misc docs)
        self.qdrant_collection = os.environ.get("QDRANT_SEARCH_COLLECTION") or "gdce_docs"
        self.qdrant_collection_name = os.environ.get("QDRANT_COLLECTION_NAME") or "gdce_docs"

        # Embedding Configuration
        self.query_embedding_model = os.environ.get("QUERY_EMBEDDING_MODEL") or "BAAI/bge-m3"
        self.embedding_batch_size = int(os.environ.get("EMBEDDING_BATCH_SIZE") or 32)
        self.embedding_cache_enabled = (os.environ.get("EMBEDDING_CACHE_ENABLED") or "true").lower() == "true"

        # Retrieval Configuration
        self.top_k_default = int(os.environ.get("TOP_K_DEFAULT") or 10)
        self.top_k_max = int(os.environ.get("TOP_K_MAX") or 50)
        self.similarity_threshold = float(os.environ.get("SIMILARITY_THRESHOLD") or 0.1)

        # Gemini LLM Configuration (for answer generation)
        self.gemini_api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        self.gemini_model = os.environ.get("GEMINI_MODEL")
        self.gemini_enabled = (os.environ.get("GEMINI_ENABLED") or "true").lower() == "true"

        # Optional vLLM fallback (mirrors retrieval service; safe to leave disabled)
        self.vllm_host = os.environ.get("VLLM_HOST") or "localhost"
        self.vllm_port = int(os.environ.get("VLLM_PORT") or 8000)
        self.vllm_model_name = os.environ.get("VLLM_MODEL_NAME") or "llama3.1:8b"
        self.vllm_enabled = (os.environ.get("VLLM_ENABLED") or "false").lower() == "true"
        self.vllm_timeout = float(os.environ.get("VLLM_TIMEOUT") or 60.0)

        # Security Configuration
        self.rate_limit_requests = int(os.environ.get("RATE_LIMIT_REQUESTS") or 100)
        self.max_payload_size_mb = int(os.environ.get("MAX_PAYLOAD_SIZE_MB") or 10)

        # CORS Configuration
        allowed_origins = os.environ.get("ALLOWED_ORIGINS") or "http://localhost:3000,http://localhost:8001"
        self.allowed_origins = [origin.strip() for origin in allowed_origins.split(",")]

        # Logging Configuration
        self.log_level = os.environ.get("LOG_LEVEL") or "INFO"

        # Timeouts (in seconds)
        self.qdrant_timeout = float(os.environ.get("QDRANT_TIMEOUT") or 30.0)

        # Caching Configuration
        self.cache_enabled = (os.environ.get("CACHE_ENABLED") or "true").lower() == "true"
        self.cache_ttl_seconds = int(os.environ.get("CACHE_TTL_SECONDS") or 3600)

    def get_service_url(self) -> str:
        """Get the general service URL."""
        return f"http://{self.host}:{self.port}"

    def validate(self) -> bool:
        """
        Validate configuration is complete.
        Returns True if valid, raises exception otherwise.
        """
        required_hosts = [
            ("qdrant_host", self.qdrant_host),
        ]

        for name, value in required_hosts:
            if not value:
                logger.warning(f"Config {name} is not set")

        return True

    def to_dict(self) -> dict:
        """Convert configuration to dictionary for logging/debugging."""
        return {
            "host": self.host,
            "port": self.port,
            "qdrant_host": self.qdrant_host,
            "qdrant_port": self.qdrant_port,
            "qdrant_collection": self.qdrant_collection,
            "top_k_default": self.top_k_default,
            "similarity_threshold": self.similarity_threshold,
            "gemini_enabled": self.gemini_enabled,
            "gemini_configured": bool(self.gemini_api_key),
            "rate_limit_requests": self.rate_limit_requests,
            "log_level": self.log_level,
        }


# Global configuration instance
_config: Optional[GeneralConfig] = None


def get_config(env_file: Optional[Path] = None) -> GeneralConfig:
    """
    Get or create the global configuration instance.

    Args:
        env_file: Optional path to .env file

    Returns:
        GeneralConfig instance
    """
    global _config
    if _config is None:
        _config = GeneralConfig(env_file)
        _config.validate()
        logger.info(f"General service configuration loaded: {_config.to_dict()}")
    return _config


def reset_config():
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None
