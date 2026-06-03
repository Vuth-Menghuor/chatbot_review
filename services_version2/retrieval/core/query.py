"""
Query Processing Module - Retrieval service
Handles query normalization, validation, and preparation for retrieval
"""

import logging
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from .language_utils import normalize_by_language, expand_by_language

logger = logging.getLogger(__name__)


@dataclass
class ProcessedQuery:
    """Processed query ready for retrieval."""
    original: str
    normalized: str
    expanded: str
    tokens: List[str]
    language: str = "en"
    min_length: int = 2
    max_length: int = 2000


class QueryProcessor:
    """
    Processes user queries for retrieval.
    
    Responsibilities:
    - Query validation
    - Text normalization
    - Query expansion
    - Token extraction
    """
    
    def __init__(self):
        """Initialize query processor."""
        self.expansion_rules = {
            "cif": "cost insurance freight customs valuation",
            "vat": "value added tax import vat cambodia",
            "hs code": "harmonized system tariff classification",
            "cd": "customs duty tariff rate",
            "st": "special tax import",
            "atiga": "asean trade in goods agreement preferential tariff",
        }
        
        self.stopwords = {
            "what", "which", "with", "from", "into", "must", "have", "that",
            "this", "they", "them", "your", "about", "under", "the", "a", "an",
            "are", "is", "be", "being", "been", "and", "or", "but", "if",
            "per", "for", "to", "of", "in", "by", "on", "at", "as", "it"
        }
    
    def validate(self, query: str) -> tuple:
        """
        Validate query.
        
        Returns:
            (is_valid: bool, error_message: Optional[str])
        """
        if not query or not query.strip():
            return False, "Query cannot be empty"
        
        if len(query) < 2:
            return False, "Query must be at least 2 characters"
        
        if len(query) > 2000:
            return False, "Query must not exceed 2000 characters"
        
        return True, None
    
    def normalize(self, query: str) -> str:
        """
        Normalize query text.
        
        - Lowercase
        - Remove extra whitespace
        - Remove special characters (but keep meaningful punctuation)
        """
        normalized, _ = normalize_by_language(query)
        # Keep alphanumerics and common trade separators while removing noisy symbols.
        normalized = re.sub(r"[^\w\s\-\./%]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized
    
    def expand(self, query: str, language: str = "en") -> str:
        """
        Expand query with domain-specific synonyms and related terms.
        """
        expanded = expand_by_language(query, language)
        
        for abbreviation, expansion in self.expansion_rules.items():
            if abbreviation in query:
                expanded += " " + expansion
        
        return expanded.strip()
    
    def tokenize(self, query: str, language: str = "en") -> List[str]:
        """
        Extract meaningful tokens from query.
        
        - Remove stopwords
        - Keep domain-relevant terms
        """
        tokens = re.findall(r'\b\w+\b', query.lower())
        if language == "en":
            tokens = [t for t in tokens if t not in self.stopwords and len(t) > 1]
        else:
            tokens = [t for t in tokens if len(t) > 1]
        return list(set(tokens))  # Remove duplicates
    
    def process(self, query: str) -> Optional[ProcessedQuery]:
        """
        Process raw query into format suitable for retrieval.
        
        Args:
            query: Raw user query
            
        Returns:
            ProcessedQuery or None if invalid
        """
        # Validate
        is_valid, error = self.validate(query)
        if not is_valid:
            logger.warning(f"Query validation failed: {error}")
            return None
        
        # Normalize
        _, language = normalize_by_language(query)
        normalized = self.normalize(query)
        
        # Expand
        expanded = self.expand(normalized, language=language)
        
        # Tokenize
        tokens = self.tokenize(normalized, language=language)
        
        return ProcessedQuery(
            original=query,
            normalized=normalized,
            expanded=expanded,
            tokens=tokens,
            language=language,
        )
