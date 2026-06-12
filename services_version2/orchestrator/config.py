"""
Configuration Management for Orchestrator Service v2
Provides centralized, environment-independent configuration
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import yaml
import json
import logging

logger = logging.getLogger(__name__)


class OrchestratorConfig:
    """
    Centralized configuration for orchestrator service.
    Loads from environment variables with sensible defaults,
    making the service independent from local config files.
    """
    
    def __init__(self, env_file: Optional[Path] = None):
        """
        Initialize configuration.
        
        Args:
            env_file: Optional path to .env file. If None, uses default search.
        """
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
        # Look for configs in orchestrator/configs first, then fall back to repo-level configs
        self.orchestrator_configs_dir = self.service_root / "configs"
        if not self.orchestrator_configs_dir.exists():
            self.orchestrator_configs_dir = self.configs_dir / "orchestrator"
        self.data_dir = self.repo_root / "data"
        self.model_dir = self.repo_root / "model"
        
        logger.debug(f"Config paths: service_root={self.service_root}, orchestrator_configs_dir={self.orchestrator_configs_dir}")
        
        # Load JSON configurations from configs/orchestrator/
        self._load_json_configs()
    
    def _load_json_configs(self):
        """Load JSON configuration files from configs/orchestrator/."""
        # Initialize configuration dictionaries
        self.intent_detection_rules: Dict[str, Any] = {}
        self.service_routing: Dict[str, Any] = {}
        self.validation_rules: Dict[str, Any] = {}
        self.response_formatting: Dict[str, Any] = {}
        
        try:
            # Load intent detection rules
            intent_file = self.orchestrator_configs_dir / "intent_detection_rules.json"
            if intent_file.exists():
                with open(intent_file, 'r') as f:
                    self.intent_detection_rules = json.load(f)
                logger.info(f"✓ Loaded intent_detection_rules.json from {intent_file}")
            else:
                logger.debug(f"intent_detection_rules.json not found at {intent_file} - using defaults")
            
            # Load service routing
            routing_file = self.orchestrator_configs_dir / "service_routing.json"
            if routing_file.exists():
                with open(routing_file, 'r') as f:
                    self.service_routing = json.load(f)
                logger.info(f"✓ Loaded service_routing.json from {routing_file}")
            else:
                logger.debug(f"service_routing.json not found at {routing_file} - using defaults")
            
            # Load validation rules
            validation_file = self.orchestrator_configs_dir / "validation_rules.json"
            if validation_file.exists():
                with open(validation_file, 'r') as f:
                    self.validation_rules = json.load(f)
                logger.info(f"✓ Loaded validation_rules.json from {validation_file}")
            else:
                logger.debug(f"validation_rules.json not found at {validation_file} - using defaults")
            
            # Load response formatting
            format_file = self.orchestrator_configs_dir / "response_formatting.json"
            if format_file.exists():
                with open(format_file, 'r') as f:
                    self.response_formatting = json.load(f)
                logger.info(f"✓ Loaded response_formatting.json from {format_file}")
            else:
                logger.debug(f"response_formatting.json not found at {format_file} - using defaults")
                
        except Exception as e:
            logger.error(f"Error loading JSON configurations: {e}")
    
    def _load_service_config(self):
        """Load service-specific configuration."""
        # API Server Configuration
        self.host = os.getenv("ORCHESTRATOR_HOST", "127.0.0.1")
        self.port = int(os.getenv("ORCHESTRATOR_PORT", "8001"))
        self.reload = os.getenv("ORCHESTRATOR_RELOAD", "false").lower() == "true"
        self.workers = int(os.getenv("ORCHESTRATOR_WORKERS", "4"))
        
        # Service URLs
        self.retrieval_service_url = os.getenv(
            "RETRIEVAL_SERVICE_URL",
            "http://127.0.0.1:8003"
        )
        self.calculator_service_url = os.getenv(
            "CALCULATOR_SERVICE_URL",
            "http://127.0.0.1:8002"
        )
        self.trade_data_service_url = os.getenv(
            "TRADE_DATA_SERVICE_URL",
            "http://127.0.0.1:8004"
        )
        
        # Service Configuration
        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
        
        # Search collections
        self.qdrant_search_collection = os.getenv(
            "QDRANT_SEARCH_COLLECTION",
            "gdce_docs"
        )
        self.qdrant_hs_code_collection = os.getenv(
            "QDRANT_HS_CODE_COLLECTION",
            "gdce_hs_code"
        )
        
        self.opensearch_host = os.getenv("OPENSEARCH_HOST", "localhost")
        self.opensearch_port = int(os.getenv("OPENSEARCH_PORT", "9200"))
        
        self.vllm_host = os.getenv("VLLM_HOST", "localhost")
        self.vllm_port = int(os.getenv("VLLM_PORT", "8000"))
        
        # Gemini LLM Configuration
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.gemini_timeout = int(os.getenv("GEMINI_TIMEOUT", "30"))
        self.gemini_enabled = os.getenv("GEMINI_ENABLED", "true").lower() == "true"
        
        # LLM Intent Detection (using Gemini)
        self.llm_intent_detection_enabled = os.getenv(
            "LLM_INTENT_DETECTION",
            "true"
        ).lower() == "true"
        self.llm_intent_detection_timeout = int(os.getenv("LLM_INTENT_DETECTION_TIMEOUT", "60"))
        
        # Query Embedding
        self.query_embedding_model = os.getenv(
            "QUERY_EMBEDDING_MODEL",
            "all-MiniLM-L6-v2"
        )
        
        # Security Configuration
        self.rate_limit_requests = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
        self.max_payload_size_mb = int(os.getenv("MAX_PAYLOAD_SIZE_MB", "10"))
        
        # CORS Configuration
        allowed_origins = os.getenv(
            "ALLOWED_ORIGINS",
            "http://localhost:3000,http://localhost:8000"
        )
        self.allowed_origins = [origin.strip() for origin in allowed_origins.split(",")]
        
        # Logging Configuration
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        
        # Feature Flags
        self.enable_trade_query = os.getenv("ENABLE_TRADE_QUERY", "true").lower() == "true"
        self.enable_calculator = os.getenv("ENABLE_CALCULATOR", "true").lower() == "true"
        self.enable_policy_engine = os.getenv("ENABLE_POLICY_ENGINE", "true").lower() == "true"
    
    def get_orchestrator_url(self) -> str:
        """Get the orchestrator service URL."""
        return f"http://{self.host}:{self.port}"
    
    def get_calculator_url(self) -> str:
        """Get the calculator service URL."""
        return self.calculator_service_url
    
    def get_retrieval_url(self) -> str:
        """Get the retrieval service URL."""
        return self.retrieval_service_url
    
    def get_trade_data_url(self) -> str:
        """Get the trade data service URL."""
        return self.trade_data_service_url
    
    def validate(self) -> bool:
        """
        Validate configuration is complete.
        Returns True if valid, raises exception otherwise.
        """
        required_urls = [
            ("retrieval_service_url", self.retrieval_service_url),
            ("calculator_service_url", self.calculator_service_url),
        ]
        
        missing = []
        for name, value in required_urls:
            if not value or value.startswith("http://localhost") and "localhost" in value:
                logger.warning(f"Config {name}: {value} (uses localhost)")
        
        return True
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary for logging/debugging."""
        return {
            "host": self.host,
            "port": self.port,
            "retrieval_service_url": self.retrieval_service_url,
            "calculator_service_url": self.calculator_service_url,
            "trade_data_service_url": self.trade_data_service_url,
            "qdrant_host": self.qdrant_host,
            "qdrant_port": self.qdrant_port,
            "vllm_host": self.vllm_host,
            "vllm_port": self.vllm_port,
            "rate_limit_requests": self.rate_limit_requests,
            "max_payload_size_mb": self.max_payload_size_mb,
            "allowed_origins": self.allowed_origins,
            "log_level": self.log_level,
        }


# Global configuration instance
_config: Optional[OrchestratorConfig] = None


def get_config(env_file: Optional[Path] = None) -> OrchestratorConfig:
    """
    Get or create the global configuration instance.
    
    Args:
        env_file: Optional path to .env file
        
    Returns:
        OrchestratorConfig instance
    """
    global _config
    if _config is None:
        _config = OrchestratorConfig(env_file)
        _config.validate()
        logger.info(f"Orchestrator configuration loaded: {_config.to_dict()}")
    return _config


def reset_config():
    """Reset the global configuration (useful for testing)."""
    global _config
    _config = None
