"""
GDCE Calculator Service - Settings / Configuration
====================================================
Typed, cached settings layer for the Calculator service.
Loads environment variables with sensible defaults.

Usage:
    settings = get_settings()
    settings.calculator_port
    settings.usd_to_khr_rate

Environment variables (see config.yaml for full documentation):
    CALCULATOR_HOST             - Bind address (default: 127.0.0.1)
    CALCULATOR_PORT             - TCP port (default: 8002)
    CALCULATOR_RELOAD           - Hot reload for dev (default: false)
    CALCULATOR_VERSION          - Service version (default: 2.0.0)
    
    RETRIEVAL_SERVICE_URL       - URL of Retrieval microservice
    ORCHESTRATOR_SERVICE_URL    - URL of Orchestrator microservice (optional)

    CALCULATOR_LLM_HOST         - LLM host for response formatting (default: 127.0.0.1)
    CALCULATOR_LLM_PORT         - LLM port (default: 11434)
    CALCULATOR_LLM_MODEL        - LLM model name (default: kimi-k2.6:cloud)
    CALCULATOR_LLM_ENABLED      - Enable LLM formatting (default: true)

    RATE_LIMIT_REQUESTS         - Requests per minute (default: 60)
    MAX_PAYLOAD_SIZE_MB         - Max request size (default: 5)
    ALLOWED_ORIGINS             - CORS origins comma-separated (default: *)
    
    DUTY_RATES_CSV_PATH         - Path to duty_rates.csv
    USD_TO_KHR_RATE             - Fallback USD→KHR rate (optional override)
    
    LOG_LEVEL                   - Logging level (default: INFO)
    ENABLE_CURRENCY_CACHE       - Cache exchange rates (default: true)
    ENABLE_HS_FUZZY_SEARCH      - Fuzzy HS code matching (default: true)
    
    ADMIN_API_KEY               - API key for admin endpoints (optional)
    RULES_CACHE_TTL_SECONDS     - Rules cache TTL in seconds (default: 300)
    RULES_DB_ENABLED            - Enable dynamic rules from DB (default: true)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass
class Settings:
    """
    Typed settings object for the Calculator service.
    
    All settings have sensible defaults and can be overridden via
    environment variables. Use get_settings() to get a cached instance.
    """

    # ================================================================
    # SERVER CONFIGURATION
    # ================================================================
    calculator_host: str = "127.0.0.1"
    calculator_port: int = 8002
    calculator_reload: bool = False
    calculator_version: str = "2.0.0"

    # ================================================================
    # LLM FORMATTER (Standalone — no orchestrator required)
    # ================================================================
    llm_host: str = "127.0.0.1"
    llm_port: int = 11434
    llm_model: str = "kimi-k2.6:cloud"
    llm_enabled: bool = True

    # ================================================================
    # LLM INTENT EXTRACTOR (Natural language → structured request)
    # ================================================================
    intent_llm_enabled: bool = True
    intent_llm_timeout: float = 10.0
    intent_llm_model: str = "llama3.2:3b"
    gemini_api_key: str = ""

    # ================================================================
    # EXTERNAL SERVICE ENDPOINTS
    # ================================================================
    retrieval_service_url: str = ""
    orchestrator_service_url: str = ""

    # ================================================================
    # SECURITY & MIDDLEWARE
    # ================================================================
    rate_limit_requests: int = 60
    max_payload_size_mb: int = 5
    allowed_origins: list[str] = field(default_factory=lambda: ["*"])

    # ================================================================
    # DATA & INFRASTRUCTURE
    # ================================================================
    # Calculator's own PostgreSQL database (primary source of truth).
    # This makes the calculator fully standalone — no dependency on shared DBs.
    calculator_db_host: str = "localhost"
    calculator_db_port: int = 5432
    calculator_db_name: str = "gdce_calculator"
    calculator_db_user: str = "calc_app"
    calculator_db_password: str = ""
    calculator_db_ssl_mode: str = "disable"

    # CSV fallback path — set via DUTY_RATES_CSV_PATH env var if needed.
    # CSV is offline fallback only when calculator DB is unavailable.
    duty_rates_csv_path: Path | None = None
    
    # ================================================================
    # CURRENCY SETTINGS
    # ================================================================
    usd_to_khr_rate: float | None = None
    enable_currency_cache: bool = True
    
    # ================================================================
    # HS CODE SETTINGS
    # ================================================================
    enable_hs_fuzzy_search: bool = True
    hs_code_candidate_limit: int = 5
    
    # ================================================================
    # DYNAMIC RULES ENGINE
    # ================================================================
    admin_api_key: str | None = None       # Required for admin endpoints; None = unprotected (dev mode)
    rules_cache_ttl_seconds: int = 300     # 5 minutes default
    rules_db_enabled: bool = True          # Enable loading rules from PostgreSQL

    # ================================================================
    # LOGGING
    # ================================================================
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings instance populated from environment variables.
    
    The Settings object is cached after first call for performance.
    Call get_settings.cache_clear() in tests to reset the cache.
    
    Returns:
        Settings: Typed configuration object with environment overrides
    """
    raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
    origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    csv_path_env = os.getenv("DUTY_RATES_CSV_PATH")

    usd_to_khr_rate_env = os.getenv("USD_TO_KHR_RATE")

    return Settings(
        # Server
        calculator_host=os.getenv("CALCULATOR_HOST", "127.0.0.1"),
        calculator_port=int(os.getenv("CALCULATOR_PORT", "8002")),
        calculator_reload=os.getenv("CALCULATOR_RELOAD", "false").lower() == "true",
        calculator_version=os.getenv("CALCULATOR_VERSION", "2.0.0"),
        
        # LLM
        llm_host=os.getenv("CALCULATOR_LLM_HOST", "127.0.0.1"),
        llm_port=int(os.getenv("CALCULATOR_LLM_PORT", "11434")),
        llm_model=os.getenv("CALCULATOR_LLM_MODEL", "kimi-k2.6:cloud"),
        llm_enabled=os.getenv("CALCULATOR_LLM_ENABLED", "true").lower() == "true",

        # Intent LLM
        intent_llm_enabled=os.getenv("CALCULATOR_INTENT_LLM_ENABLED", "true").lower() == "true",
        intent_llm_timeout=float(os.getenv("CALCULATOR_INTENT_LLM_TIMEOUT", "10.0")),
        intent_llm_model=os.getenv("CALCULATOR_INTENT_LLM_MODEL", "llama3.2:3b"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),

        # Services
        retrieval_service_url=os.getenv("RETRIEVAL_SERVICE_URL", ""),
        orchestrator_service_url=os.getenv("ORCHESTRATOR_SERVICE_URL", ""),
        
        # Security
        rate_limit_requests=int(os.getenv("RATE_LIMIT_REQUESTS", "60")),
        max_payload_size_mb=int(os.getenv("MAX_PAYLOAD_SIZE_MB", "5")),
        allowed_origins=origins or ["*"],
        
        # Calculator DB (standalone primary source)
        calculator_db_host=os.getenv("CALCULATOR_DB_HOST", "localhost"),
        calculator_db_port=int(os.getenv("CALCULATOR_DB_PORT", "5432")),
        calculator_db_name=os.getenv("CALCULATOR_DB_NAME", "gdce_calculator"),
        calculator_db_user=os.getenv("CALCULATOR_DB_USER", "calc_app"),
        calculator_db_password=os.getenv("CALCULATOR_DB_PASSWORD", ""),
        calculator_db_ssl_mode=os.getenv("CALCULATOR_DB_SSL_MODE", "disable"),

        # Infrastructure (CSV fallback — only if env var set)
        duty_rates_csv_path=Path(csv_path_env) if csv_path_env else None,

        # Currency
        usd_to_khr_rate=float(usd_to_khr_rate_env) if usd_to_khr_rate_env else None,
        enable_currency_cache=os.getenv("ENABLE_CURRENCY_CACHE", "true").lower() == "true",
        
        # HS Code
        enable_hs_fuzzy_search=os.getenv("ENABLE_HS_FUZZY_SEARCH", "true").lower() == "true",
        hs_code_candidate_limit=int(os.getenv("HS_CODE_CANDIDATE_LIMIT", "5")),
        
        # Dynamic Rules Engine
        admin_api_key=os.getenv("ADMIN_API_KEY"),
        rules_cache_ttl_seconds=int(os.getenv("RULES_CACHE_TTL_SECONDS", "300")),
        rules_db_enabled=os.getenv("RULES_DB_ENABLED", "true").lower() == "true",

        # Logging
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
