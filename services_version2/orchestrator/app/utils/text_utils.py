"""
Generic text formatting utilities for the orchestrator service.

Contains string helpers that operate on text representation only —
no entity extraction, no query-intent parsing. See entity_utils.py
for functions that extract or isolate the subject/product from a query.
"""

import re
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class ResponseBuilder:
    """Helper class for building standardized responses."""
    
    @staticmethod
    def success_response(
        request_id: str,
        question: str,
        answer: Optional[str] = None,
        intent: Optional[str] = None,
        citations: Optional[list] = None,
        latency_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build a success response.
        
        Args:
            request_id: Unique request identifier
            question: Original question
            answer: Response answer
            intent: Detected intent
            citations: List of citations
            latency_ms: Processing latency
            metadata: Additional metadata
            
        Returns:
            Response dictionary
        """
        return {
            "request_id": request_id,
            "question": question,
            "answer": answer,
            "intent": intent,
            "status": "completed",
            "citations": citations or [],
            "latency_ms": latency_ms,
            "metadata": metadata or {}
        }
    
    @staticmethod
    def error_response(
        request_id: str,
        question: str,
        error_message: str,
        error_code: str = "INTERNAL_ERROR",
        latency_ms: float = 0.0
    ) -> Dict[str, Any]:
        """
        Build an error response.
        
        Args:
            request_id: Unique request identifier
            question: Original question
            error_message: Error message
            error_code: Error code
            latency_ms: Processing latency
            
        Returns:
            Error response dictionary
        """
        return {
            "request_id": request_id,
            "question": question,
            "status": "failed",
            "error": error_message,
            "error_code": error_code,
            "latency_ms": latency_ms
        }
    
    @staticmethod
    def clarification_response(
        request_id: str,
        question: str,
        clarifications: list,
        latency_ms: float = 0.0
    ) -> Dict[str, Any]:
        """
        Build a clarification response.
        
        Args:
            request_id: Unique request identifier
            question: Original question
            clarifications: List of clarifications needed
            latency_ms: Processing latency
            
        Returns:
            Clarification response dictionary
        """
        return {
            "request_id": request_id,
            "question": question,
            "status": "clarification_required",
            "clarifications": clarifications,
            "latency_ms": latency_ms
        }


class LoggerSetup:
    """Helper for setting up logging."""
    
    @staticmethod
    def setup_logger(
        name: str,
        level: str = "INFO"
    ) -> logging.Logger:
        """
        Set up a logger with standard configuration.
        
        Args:
            name: Logger name
            level: Log level
            
        Returns:
            Configured logger
        """
        logger = logging.getLogger(name)
        level_int = getattr(logging, level.upper(), logging.INFO)
        logger.setLevel(level_int)
        
        # Create console handler
        handler = logging.StreamHandler()
        handler.setLevel(level_int)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        # Add handler to logger
        if not logger.handlers:
            logger.addHandler(handler)
        
        return logger


def get_timestamp_iso() -> str:
    """
    Get current timestamp in ISO format.
    
    Returns:
        ISO format timestamp
    """
    return datetime.utcnow().isoformat() + "Z"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add if truncated

    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
