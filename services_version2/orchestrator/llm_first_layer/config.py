"""Configuration for the unified LLM first layer."""

from dataclasses import dataclass
import os
from typing import Optional


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
    ambiguity_confidence_threshold: float = 0.65
    ambiguity_score_gap_threshold: float = 0.15
    ask_back_timeout: int = 8
    
    # ========== Currency Detection Configuration ==========
    enable_currency_detection: bool = True
    currency_provider: str = "minilm"  # Fast pattern matching first
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
        # Apply environment variable overrides
        self.gemini_api_key = self.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        
        if self.skip_rewrite_for_intents is None:
            self.skip_rewrite_for_intents = ["hs_code_lookup", "trade_query"]
