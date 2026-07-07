"""
Configuration Management for Orchestrator Service v2
Provides centralized, environment-independent configuration
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
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
        # Load environment variables from the service root .env (services_version2/orchestrator/.env)
        self.service_root = Path(__file__).resolve().parents[2]
        default_env = self.service_root / ".env"

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
        self.repo_root = self.service_root.parent.parent
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
        self.general_service_url = os.getenv(
            "GENERAL_SERVICE_URL",
            "http://127.0.0.1:8005"
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

        # Postgres Configuration
        self.pg_host = os.getenv("POSTGRES_HOST") or os.getenv("PG_HOST")
        self.pg_port = int(os.getenv("POSTGRES_PORT") or os.getenv("PG_PORT"))
        self.pg_database = os.getenv("POSTGRES_DB") or os.getenv("PG_DATABASE")
        self.pg_user = os.getenv("POSTGRES_USER") or os.getenv("PG_USER")
        self.pg_password = os.getenv("POSTGRES_PASSWORD") or os.getenv("PG_PASSWORD")

        # Session Transcript Flusher Configuration
        self.transcript_flush_interval = int(os.getenv("TRANSCRIPT_FLUSH_INTERVAL", "300"))
        self.redis_retention_turns = int(os.getenv("REDIS_RETENTION_TURNS", "20"))
        self.postgres_retention_days = int(os.getenv("POSTGRES_RETENTION_DAYS", "90"))
        
        # LLM Service Configuration
        self.llm = LLMServiceConfig()
        
        # First Layer Configuration
        self.first_layer = LLMFirstLayerConfig()
        
        # Formatter Configuration
        self.formatter = FormatterServiceConfig()
    
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

    def get_general_url(self) -> str:
        """Get the general service URL."""
        return self.general_service_url
    
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
            "general_service_url": self.general_service_url,
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
            "pg_host": self.pg_host,
            "pg_port": self.pg_port,
            "pg_database": self.pg_database,
            "pg_user": self.pg_user,
            "transcript_flush_interval": self.transcript_flush_interval,
            "redis_retention_turns": self.redis_retention_turns,
            "postgres_retention_days": self.postgres_retention_days,
            "llm": self.llm.__dict__ if hasattr(self, "llm") else None,
            "first_layer": self.first_layer.__dict__ if hasattr(self, "first_layer") else None,
            "formatter": self.formatter.__dict__ if hasattr(self, "formatter") else None,
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


# =====================================================================
# Timeout Configuration Section (Merged from timeout_config.py)
# =====================================================================

from enum import Enum

class WorkflowIntent(str, Enum):
    """Supported workflow intents."""
    CALCULATION = "calculation"
    TRADE_QUERY = "trade_query"
    GENERAL = "general"
    HS_CODE_LOOKUP = "hs_code_lookup"
    UNCLASSIFIED = "unclassified"
    SMALL_TALK = "small_talk"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val_lower = value.lower().strip()
            # Aliases → GENERAL (definition, policy variants)
            if val_lower in {"definition", "policy", "policy_query", "general_query"}:
                return cls.GENERAL
            # Aliases → UNCLASSIFIED (small_talk falls back here so coordinator handles it)
            if val_lower in {"small_talk", "smalltalk", "chit_chat"}:
                return cls.UNCLASSIFIED
            # Aliases → HS_CODE_LOOKUP
            if val_lower in {"hs_code", "hs", "hs_lookup", "commodity"}:
                return cls.HS_CODE_LOOKUP
            # Aliases → TRADE_QUERY
            if val_lower in {"trade", "trade_data", "trade_statistics"}:
                return cls.TRADE_QUERY
        return super()._missing_(value)

class TimeoutConfig:
    """
    Intent-specific timeout configuration.
    Maps workflow intents to service-specific timeout values (in seconds).
    """
    
    # Default timeout values per intent
    INTENT_TIMEOUTS = {
        WorkflowIntent.CALCULATION: 20,         # Calculation is relatively quick
        WorkflowIntent.HS_CODE_LOOKUP: 60,      # HS lookup: Gemini spec extraction + semantic search + LLM explanation (extended for multi-step LLM)
        WorkflowIntent.GENERAL: 50,             # General lookup from retrieval service with LLM
        WorkflowIntent.TRADE_QUERY: 40,         # Trade queries might need aggregation
    }
    
    # Service-specific timeout overrides (in seconds)
    SERVICE_TIMEOUTS = {
        "calculator": 20,       # Calculator service should be fast
        "retrieval": 60,        # Retrieval might need semantic search + LLM answer generation
        "trade_data": 40,       # Trade data queries might be complex
        "general": 50,          # General service queries
    }
    
    # Default timeout if intent is None
    DEFAULT_TIMEOUT = 15
    
    # Minimum and maximum allowed timeouts to prevent misconfiguration
    MIN_TIMEOUT = 2
    # Cap maximum allowed timeout at 60s
    MAX_TIMEOUT = 60
    
    def __init__(
        self,
        intent_timeouts: Optional[Dict[WorkflowIntent, int]] = None,
        service_timeouts: Optional[Dict[str, int]] = None,
        default_timeout: int = 15
    ):
        """
        Initialize timeout configuration.
        
        Args:
            intent_timeouts: Optional override for intent-specific timeouts
            service_timeouts: Optional override for service-specific timeouts
            default_timeout: Default timeout if intent not found
        """
        # Use provided values or defaults
        self.intent_timeouts = intent_timeouts or self.INTENT_TIMEOUTS.copy()
        self.service_timeouts = service_timeouts or self.SERVICE_TIMEOUTS.copy()
        self.default_timeout = max(self.MIN_TIMEOUT, min(default_timeout, self.MAX_TIMEOUT))
        
        logger.debug(
            f"[TimeoutConfig] Initialized with default={self.default_timeout}s, "
            f"intents={len(self.intent_timeouts)}, services={len(self.service_timeouts)}"
        )
    
    def get_intent_timeout(self, intent: Optional[WorkflowIntent]) -> int:
        """
        Get timeout value for a specific intent.
        
        Args:
            intent: WorkflowIntent enum value (or None)
            
        Returns:
            Timeout in seconds
        """
        if intent is None:
            return self.default_timeout
        
        timeout = self.intent_timeouts.get(intent, self.default_timeout)
        
        # Validate bounds
        timeout = max(self.MIN_TIMEOUT, min(timeout, self.MAX_TIMEOUT))
        
        logger.debug(f"[TimeoutConfig] Intent '{intent.value}' → {timeout}s timeout")
        
        return timeout
    
    def get_service_timeout(self, service_name: str) -> int:
        """
        Get timeout value for a specific service.
        
        Args:
            service_name: Name of the service (calculator, retrieval, trade_data)
            
        Returns:
            Timeout in seconds
        """
        timeout = self.service_timeouts.get(service_name, self.default_timeout)
        
        # Validate bounds
        timeout = max(self.MIN_TIMEOUT, min(timeout, self.MAX_TIMEOUT))
        
        logger.debug(f"[TimeoutConfig] Service '{service_name}' → {timeout}s timeout")
        
        return timeout
    
    def set_intent_timeout(self, intent: WorkflowIntent, timeout_sec: int):
        """
        Update timeout for a specific intent at runtime.
        
        Args:
            intent: WorkflowIntent enum value
            timeout_sec: Timeout in seconds
            
        Raises:
            ValueError: If timeout is outside allowed bounds
        """
        if timeout_sec < self.MIN_TIMEOUT or timeout_sec > self.MAX_TIMEOUT:
            raise ValueError(
                f"Timeout {timeout_sec}s outside bounds [{self.MIN_TIMEOUT}, {self.MAX_TIMEOUT}]"
            )
        
        self.intent_timeouts[intent] = timeout_sec
        logger.info(f"[TimeoutConfig] Updated intent '{intent.value}' timeout to {timeout_sec}s")
    
    def set_service_timeout(self, service_name: str, timeout_sec: int):
        """
        Update timeout for a specific service at runtime.
        
        Args:
            service_name: Service name (calculator, retrieval, trade_data)
            timeout_sec: Timeout in seconds
            
        Raises:
            ValueError: If timeout is outside allowed bounds
        """
        if timeout_sec < self.MIN_TIMEOUT or timeout_sec > self.MAX_TIMEOUT:
            raise ValueError(
                f"Timeout {timeout_sec}s outside bounds [{self.MIN_TIMEOUT}, {self.MAX_TIMEOUT}]"
            )
        
        self.service_timeouts[service_name] = timeout_sec
        logger.info(f"[TimeoutConfig] Updated service '{service_name}' timeout to {timeout_sec}s")
    
    def get_all_timeouts(self) -> Dict[str, Any]:
        """
        Get all configured timeouts for monitoring/debugging.
        
        Returns:
            Dictionary with all timeout configurations
        """
        return {
            "default": self.default_timeout,
            "intent_timeouts": {k.value: v for k, v in self.intent_timeouts.items()},
            "service_timeouts": self.service_timeouts.copy(),
            "bounds": {
                "min": self.MIN_TIMEOUT,
                "max": self.MAX_TIMEOUT
            }
        }
    
    def __repr__(self) -> str:
        """String representation for logging."""
        intents_str = ", ".join([f"{k.value}={v}s" for k, v in self.intent_timeouts.items()])
        services_str = ", ".join([f"{k}={v}s" for k, v in self.service_timeouts.items()])
        return (
            f"TimeoutConfig(default={self.default_timeout}s, "
            f"intents=[{intents_str}], "
            f"services=[{services_str}])"
        )


# Global timeout configuration singleton
_timeout_config: Optional[TimeoutConfig] = None


def get_timeout_config() -> TimeoutConfig:
    """
    Get or create global timeout configuration.
    
    Returns:
        TimeoutConfig singleton instance
    """
    global _timeout_config
    
    if _timeout_config is None:
        _timeout_config = TimeoutConfig()
        logger.debug(f"[TimeoutConfig] Created global singleton: {_timeout_config}")
    
    return _timeout_config


def initialize_timeout_config(config: Optional[TimeoutConfig] = None) -> TimeoutConfig:
    """
    Initialize or replace global timeout configuration.
    
    Args:
        config: TimeoutConfig instance (or None to use defaults)
        
    Returns:
        The initialized TimeoutConfig
    """
    global _timeout_config
    
    if config is None:
        _timeout_config = TimeoutConfig()
    else:
        _timeout_config = config
    
    logger.info(f"[TimeoutConfig] Initialized: {_timeout_config}")
    
    return _timeout_config


def reset_timeout_config():
    """Reset global timeout configuration to None (for testing)."""
    global _timeout_config
    _timeout_config = None


@dataclass
class LLMServiceConfig:
    """Provider-neutral configuration for LLM tasks."""

    intent_provider: str = field(default_factory=lambda: os.getenv("INTENT_PROVIDER", "gemini"))
    currency_provider: str = field(default_factory=lambda: os.getenv("CURRENCY_PROVIDER", "gemini"))
    rewrite_provider: str = field(default_factory=lambda: os.getenv("REWRITE_PROVIDER", "gemini"))
    summarization_provider: str = field(default_factory=lambda: os.getenv("SUMMARIZATION_PROVIDER", "gemini"))
    hs_selection_provider: str = field(default_factory=lambda: os.getenv("HS_SELECTION_PROVIDER", "gemini"))

    fallback_order: List[str] = field(default_factory=lambda: [
        x.strip() for x in os.getenv("LLM_FALLBACK_ORDER", "gemini,ollama").split(",") if x.strip()
    ])
    retries: int = field(default_factory=lambda: int(os.getenv("LLM_RETRIES", "2")))
    retry_backoff_seconds: float = field(default_factory=lambda: float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "0.5")))

    ollama_host: str = field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    ollama_timeout: int = field(default_factory=lambda: int(os.getenv("OLLAMA_TIMEOUT", "30")))

    gemini_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "") or None)
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite"))
    gemini_timeout: int = field(default_factory=lambda: int(os.getenv("GEMINI_TIMEOUT", "30")))

    openai_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", "") or None)
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    openai_timeout: int = field(default_factory=lambda: int(os.getenv("OPENAI_TIMEOUT", "30")))

    temperatures: Dict[str, float] = field(
        default_factory=lambda: {
            "intent": float(os.getenv("LLM_TEMP_INTENT", "0.0")),
            "currency": float(os.getenv("LLM_TEMP_CURRENCY", "0.1")),
            "rewrite": float(os.getenv("LLM_TEMP_REWRITE", "0.2")),
            "summarize": float(os.getenv("LLM_TEMP_SUMMARIZE", "0.2")),
            "hs_selection": float(os.getenv("LLM_TEMP_HS_SELECTION", "0.0")),
        }
    )


@dataclass
class LLMFirstLayerConfig:
    """
    Unified configuration for the first LLM layer.
    
    Consolidates configurations from:
    - validator_service
    - intent_service
    - ask_back_service
    - currency_service
    - rewriter_service
    """
    
    # ========== Gemini Configuration ==========
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.1-flash-lite"
    gemini_timeout: int = 30
    
    # ========== Validation Configuration ==========
    enable_validation: bool = True
    enable_llm_validation_fallback: bool = True
    validation_timeout: int = 5
    
    # ========== Intent Detection Configuration ==========
    enable_intent_detection: bool = True
    intent_provider: str = "gemini"  # Primary provider
    intent_confidence_threshold: float = 0.65
    intent_timeout: int = 30
    
    # ========== Ambiguity Check Configuration ==========
    enable_ask_back: bool = True
    ambiguity_confidence_threshold: float = 0.60
    ambiguity_score_gap_threshold: float = 0.15
    ask_back_timeout: int = 8
    
    # ========== Currency Detection Configuration ==========
    enable_currency_detection: bool = True
    currency_provider: str = "gemini"
    currency_timeout: int = 5
    
    # ========== Query Rewriting Configuration ==========
    enable_rewriting: bool = True
    rewrite_provider: str = "gemini"
    skip_rewrite_for_intents: list = None  # e.g., ["hs_code_lookup", "trade_query"]
    rewrite_timeout: int = 30
    
    # ========== Ollama Fallback Configuration ==========
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    ollama_enabled: bool = os.getenv("LLM_INTENT_DETECTION", "true").lower() == "true"
    
    # ========== MiniLM Configuration ==========
    minilm_model: str = "all-MiniLM-L12-v2"
    minilm_confidence_threshold: float = 0.75
    
    # ========== Session Management ==========
    session_enabled: bool = True
    max_sessions: int = 1000
    session_timeout_sec: int = 3600
    
    # ========== Pipeline Configuration ==========
    # Total timeout for entire first layer pipeline
    total_timeout: int = 60
    
    # Fail fast on validation errors
    fail_fast_on_invalid: bool = True
    
    # Collect all errors for debugging
    collect_errors: bool = True
    
    def __post_init__(self):
        """Initialize derived values and apply environment overrides."""
        # Ensure service-local environment variables are loaded
        from dotenv import load_dotenv
        from pathlib import Path
        
        service_root = Path(__file__).resolve().parents[2]
        local_env = service_root / ".env"
        if local_env.exists():
            load_dotenv(local_env)
        else:
            load_dotenv()

        # Apply environment variable overrides
        self.gemini_api_key = self.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        
        if self.skip_rewrite_for_intents is None:
            # Only the "general" catch-all intent goes through LLM rewriting.
            # hs_code_lookup, trade_query, and calculation must receive the raw
            # query unchanged so their downstream services can do their own
            # structured parsing / keyword matching without interference.
            self.skip_rewrite_for_intents = ["hs_code_lookup"]


@dataclass
class FormatterServiceConfig:
    """Configuration for LLM formatter tasks."""
    provider: str = field(default_factory=lambda: os.getenv("FORMATTER_PROVIDER", "ollama"))
    
    # Ollama configuration (legacy)
    ollama_host: str = field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"))
    ollama_port: int = 11434  # Deprecated, kept for backward compatibility
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "mistral"))
    
    # Gemini configuration
    gemini_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "") or None)
    gemini_model: Optional[str] = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "") or None)
    
    timeout: int = field(default_factory=lambda: int(os.getenv("FORMATTER_TIMEOUT", "30")))
    enabled: bool = field(default_factory=lambda: os.getenv("FORMATTER_ENABLED", "false").lower() == "true")




