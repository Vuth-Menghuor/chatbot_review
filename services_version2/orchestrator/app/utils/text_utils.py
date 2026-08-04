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


def strip_clarification_questions_from_prose(answer: str, questions: list) -> str:
    """
    Safely removes the trailing clarification questions section and headers from
    the natural language prose using a three-tier matching strategy.
    
    Tiers 2 and 3 are strictly scoped to list/bulleted lines to prevent over-stripping
    unrelated prose sentences.
    """
    if not answer:
        return ""
    if not questions:
        return answer
        
    lines = answer.split("\n")
    
    # Tier 1: Header-based truncation
    headers = [
        "[clarification questions]",
        "clarification questions:",
        "clarification questions",
        "clarifying questions:",
        "clarifying questions",
    ]
    for i, line in enumerate(lines):
        stripped = line.strip().lower()
        if any(stripped == h or stripped.startswith(h) for h in headers):
            # Truncate all lines from this header onwards
            return "\n".join(lines[:i]).strip()
            
    # Tier 2 & 3: Bullet-scoped line matching
    def normalize(text: str) -> str:
        # Lowercase, remove common punctuation, bullets, symbols, and extra spacing
        return re.sub(r"[-*❓\s\d\.\?៛$€£¥₩]+", "", text).strip().lower()
        
    normalized_questions = [normalize(q) for q in questions if q.strip()]
    cleaned_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Check if line looks like a list item or bullet point
        is_list_item = (
            stripped.startswith("-")
            or stripped.startswith("*")
            or stripped.startswith("❓")
            or bool(re.match(r"^\d+\.", stripped))
        )
        
        if is_list_item:
            norm_line = normalize(stripped)
            is_match = False
            for norm_q in normalized_questions:
                if not norm_q:
                    continue
                # Tier 2: Exact normalized match
                if norm_line == norm_q:
                    is_match = True
                    break
                # Tier 3: Substring match (restricted strictly to list items)
                if norm_q in norm_line or norm_line in norm_q:
                    is_match = True
                    break
            if is_match:
                # Strip this line
                continue
                
        cleaned_lines.append(line)
        
    # Remove trailing empty lines
    while cleaned_lines and not cleaned_lines[-1].strip():
        cleaned_lines.pop()
        
    return "\n".join(cleaned_lines).strip()


