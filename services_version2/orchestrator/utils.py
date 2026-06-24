"""
Utility functions for the orchestrator service
"""

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


def standardize_hs_codes_in_text(text: str) -> str:
    """
    Finds potential HS codes in text (8-digit or 6-digit variants)
    and formats them to their formal dotted representation:
    - 8 digits: BBBB.SS.SS (e.g., 0101.21.00)
    - 6 digits: BBBB.SS (e.g., 0101.21)
    
    Avoids formatting numbers that are likely monetary amounts or years.
    """
    import re

    if not text:
        return text

    # Matches:
    # 1. 8-digit formats (01012100, 0101.2100, 010121.00, 0101 21 00, 0101-21-00, 0101.21.00)
    # 2. 6-digit formats (010121, 0101.21, 0101 21, 0101-21)
    pattern = r'\b(?:\d{4}[.\s-]\d{2}[.\s-]\d{2}|\d{4}[.\s-]\d{4}|\d{6}[.\s-]\d{2}|\d{8}|\d{4}[.\s-]\d{2}|\d{6})\b'
    
    last_idx = 0
    parts = []
    
    for match in re.finditer(pattern, text):
        start, end = match.span()
        matched_text = match.group(0)
        
        parts.append(text[last_idx:start])
        
        digits = re.sub(r'[^\d]', '', matched_text)
        preceding_text = text[max(0, start - 20):start].lower()
        
        # Determine if matches look like currency/prices/quantities
        is_currency_or_val = False
        if any(marker in preceding_text for marker in ['$', 'cif', 'fob', 'usd', 'khr', 'riel', 'riels', 'worth', 'value', 'price', 'cost', 'amount', 'total']):
            is_currency_or_val = True
            if any(marker in preceding_text for marker in ['hs', 'code', 'tariff', 'classify', 'classification']):
                is_currency_or_val = False
                
        is_hs_code = False
        if len(digits) == 8:
            if not is_currency_or_val:
                is_hs_code = True
        elif len(digits) == 6:
            has_separator = any(sep in matched_text for sep in ['.', ' ', '-'])
            starts_with_zero = digits.startswith('0')
            has_hs_marker = any(marker in preceding_text for marker in ['hs', 'code', 'tariff', 'classify', 'classification'])
            
            if not is_currency_or_val:
                if has_separator or starts_with_zero or has_hs_marker:
                    is_hs_code = True
                    
        if is_hs_code:
            if len(digits) == 8:
                formatted = f"{digits[:4]}.{digits[4:6]}.{digits[6:]}"
            else:
                formatted = f"{digits[:4]}.{digits[4:]}"
            parts.append(formatted)
        else:
            parts.append(matched_text)
            
        last_idx = end
        
    parts.append(text[last_idx:])
    return "".join(parts)


def extract_entity(query: str) -> Optional[str]:
    """
    Extract the core subject entity (noun phrase) from a user query.

    This is a **stateless utility** used by:
    - Session-state writer: to populate ``SessionContext.last_entity`` after
      each processed turn.
    - ``ServiceCoordinator._merge_pending_with_clarification``: to fall back
      to the turn-1 entity when the turn-2 fragment carries no entity of its
      own.

    Strategy:
    1. Strip trailing punctuation first so that pure-filler fragments like
       "and for?" or "for?" match their prefix patterns cleanly.
    2. Iteratively strip well-known intent-keyword prefixes ("hs code of",
       "trade data for", "calculate import duty for", etc.) until only the
       product / subject noun phrase remains.
    3. Strip any residual trailing punctuation.
    4. Remove obvious stopwords.
    5. Return ``None`` if nothing meaningful survives.

    Args:
        query: Raw or normalised user query string.

    Returns:
        Lowercase entity string (e.g. ``"car"``, ``"boat"``, ``"rice"``),
        or ``None`` if extraction yields nothing usable.
    """
    import re as _re

    if not query or not query.strip():
        return None

    text = query.strip().lower()

    # ------------------------------------------------------------------
    # Step 1: Strip trailing punctuation FIRST so that pure-filler
    # fragments like "and for?" match the prefix patterns below.
    # The prefix patterns require the keyword to be followed by whitespace
    # or end-of-string; removing trailing '?' here enables them to fire.
    # ------------------------------------------------------------------
    text = _re.sub(r"[?!.,;:]+$", "", text).strip()
    if not text:
        return None

    # ------------------------------------------------------------------
    # Step 2: Strip leading intent-keyword prefixes iteratively.
    # Chained prefixes collapse on repeated passes.
    # ------------------------------------------------------------------
    PREFIXES = [
        # HS-code signals
        r"^(?:what(?:'?s|\s+is)?(?:\s+the)?\s+)?hs\s*(?:code|codes|number|tariff)?\s*(?:of|for|on)?\s*",
        r"^(?:find|get|look\s+up|give\s+me|tell\s+me)(?:\s+the)?\s+hs\s*(?:code|codes|number)?\s*(?:of|for|on)?\s*",
        r"^classify(?:\s+the)?\s*(?:product)?\s*",
        # Trade-query signals
        r"^(?:what(?:'?s|\s+is)?(?:\s+the)?\s+)?trade\s+(?:data|statistics|volume|flow|flows)?\s*(?:of|for|on|about)?\s*",
        r"^(?:import|export)\s+(?:data|statistics|volume|flow)?\s*(?:of|for|on|from|to)?\s*",
        # Calculation signals
        r"^(?:calculate|compute|how\s+much\s+(?:is|are|does)?)\s+(?:the\s+)?(?:import\s+)?(?:duty|tax|tariff|vat|fee)?\s*(?:of|for|on)?\s*",
        r"^(?:import|export)\s+(?:duty|tax|tariff|fee)\s+(?:of|for|on)?\s*",
        r"^what(?:'?s|\s+is)\s+(?:the\s+)?(?:import|export)?\s+(?:duty|tax|tariff)\s+(?:for|on)?\s*",
        # General / definition signals
        r"^(?:what(?:'?s|\s+is)|define|explain|describe|tell\s+me\s+about|how\s+to)\s+",
        # Generic question starters
        r"^(?:about|regarding|re:?)\s+",
        # Conversational fragment starters ("what about X", "and for X", "for X")
        r"^(?:what|how)\s+about\s+",
        r"^and\s+for\s+",
        r"^and\s+for$",        # handles "and for" (after trailing punctuation stripped)
        r"^for\s+",
        r"^for$",              # handles standalone "for" (after trailing punctuation stripped)
    ]

    changed = True
    while changed:
        changed = False
        for prefix_pattern in PREFIXES:
            new_text = _re.sub(prefix_pattern, "", text, flags=_re.IGNORECASE).strip()
            if new_text != text:
                text = new_text
                changed = True
                break  # restart loop so earlier patterns re-run

    # ------------------------------------------------------------------
    # Step 3: Strip any residual trailing punctuation
    # ------------------------------------------------------------------
    text = _re.sub(r"[?!.,;:]+$", "", text).strip()

    # ------------------------------------------------------------------
    # Step 4: Remove obvious stopwords that survived stripping
    # ------------------------------------------------------------------
    STOPWORDS = {"a", "an", "the", "its", "it", "that", "this", "these", "those", "some"}
    words = text.split()
    words = [w for w in words if w not in STOPWORDS]
    text = " ".join(words).strip()

    # Return None when nothing meaningful is left (empty or single char)
    if not text or len(text) <= 1:
        return None

    return text
