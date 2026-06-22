"""
Timeout Configuration Module - Intent-Specific Timeout Management
Configure timeouts based on query intent for better resource management
"""

import logging
from enum import Enum
from typing import Optional, Dict, Any
from .workflow import WorkflowIntent

logger = logging.getLogger(__name__)


class TimeoutConfig:
    """
    Intent-specific timeout configuration.
    Maps workflow intents to service-specific timeout values (in seconds).
    """
    
    # Default timeout values per intent
    INTENT_TIMEOUTS = {
        WorkflowIntent.CALCULATION: 10,         # Calculation is relatively quick
        WorkflowIntent.HS_CODE_LOOKUP: 45,      # HS lookup: Gemini spec extraction + semantic search + LLM explanation (extended for multi-step LLM)
        WorkflowIntent.GENERAL: 35,             # General lookup from retrieval service with LLM
        WorkflowIntent.TRADE_QUERY: 20,         # Trade queries might need aggregation
    }
    
    # Service-specific timeout overrides (in seconds)
    SERVICE_TIMEOUTS = {
        "calculator": 10,       # Calculator service should be fast
        "retrieval": 45,        # Retrieval might need semantic search + LLM answer generation
        "trade_data": 20,       # Trade data queries might be complex
        "general": 35,          # General service queries
    }
    
    # Default timeout if intent is None
    DEFAULT_TIMEOUT = 15
    
    # Minimum and maximum allowed timeouts to prevent misconfiguration
    MIN_TIMEOUT = 2
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
            
        Examples:
            >>> config = TimeoutConfig()
            >>> config.get_intent_timeout(WorkflowIntent.CALCULATION)
            10
            >>> config.get_intent_timeout(None)
            15
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
            
        Examples:
            >>> config = TimeoutConfig()
            >>> config.get_service_timeout("calculator")
            10
            >>> config.get_service_timeout("retrieval")
            15
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
