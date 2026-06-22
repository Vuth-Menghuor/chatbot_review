"""
GDCE Calculator Service - HS Code Handler
==========================================
Handles HS-code focused operations including validation, normalization,
lookup, and candidate suggestions for fallback scenarios.

HS Code Format:
- 4 digits: Section level (e.g., "0102")
- 6 digits: Chapter level (e.g., "010210")
- 8 digits: Sub-chapter level (e.g., "01021000")

Usage:
    handler = HSCodeHandler(db)
    normalized = handler.normalize_code("01.02.10.00")  # "0102.10.00"
    is_valid = handler.is_valid_code("0102.10.00")
    candidates = handler.get_candidates("live cattle")
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ================================================================
# HS CODE HANDLER
# ================================================================

class HSCodeHandler:
    """
    Handles all HS-code related operations.
    
    Responsibilities:
    - Validate and normalize HS codes
    - Lookup HS code descriptions
    - Generate candidate suggestions for fuzzy matches
    - Support multi-level HS code hierarchies
    """
    
    def __init__(self, db=None):
        """
        Initialize HS code handler.
        
        Args:
            db: Database interface for HS code lookups
        """
        self.db = db
    
    # ================================================================
    # VALIDATION
    # ================================================================
    
    def is_valid_code(self, hs_code: str) -> bool:
        """
        Check if HS code has valid format.
        
        Valid formats:
        - 4 digits: "0102"
        - 6 digits: "010210" or "0102.10"
        - 8 digits: "01021000" or "0102.10.00"
        
        Args:
            hs_code: HS code string (may contain dots)
            
        Returns:
            True if valid format
        """
        if not hs_code or not isinstance(hs_code, str):
            return False
        
        # Remove dots for validation
        clean = hs_code.replace(".", "")
        
        # Must be 4, 6, or 8 digits
        if not clean.isdigit():
            return False
        
        return len(clean) in [4, 6, 8]
    
    def validate_code(self, hs_code: str) -> str:
        """
        Validate and normalize HS code.
        
        Args:
            hs_code: HS code string
            
        Returns:
            Normalized HS code
            
        Raises:
            ValueError: If HS code format is invalid
        """
        if not self.is_valid_code(hs_code):
            raise ValueError(
                f"Invalid HS code format: '{hs_code}'. "
                "Expected 4, 6, or 8 digits (with or without dots)."
            )
        return self.normalize_code(hs_code)
    
    # ================================================================
    # NORMALIZATION
    # ================================================================
    
    def normalize_code(self, hs_code: str) -> str:
        """
        Normalize HS code to standard dotted format.
        
        Examples:
        - "0102" → "0102"
        - "010210" → "0102.10"
        - "01021000" → "0102.10.00"
        - "0102.10.00" → "0102.10.00" (already normalized)
        
        Args:
            hs_code: HS code string
            
        Returns:
            Normalized HS code with dots
        """
        if not hs_code:
            return ""
        
        # Remove all dots
        clean = hs_code.replace(".", "")
        
        # Apply normalization based on length
        if len(clean) == 4:
            return clean
        elif len(clean) == 6:
            return f"{clean[:4]}.{clean[4:6]}"
        elif len(clean) == 8:
            return f"{clean[:4]}.{clean[4:6]}.{clean[6:8]}"
        else:
            return clean
    
    def denormalize_code(self, hs_code: str) -> str:
        """
        Convert normalized HS code to simple digit string.
        
        Examples:
        - "0102" → "0102"
        - "0102.10" → "010210"
        - "0102.10.00" → "01021000"
        """
        return hs_code.replace(".", "")
    
    # ================================================================
    # LOOKUP
    # ================================================================
    
    def get_code_info(self, hs_code: str) -> Optional[dict]:
        """
        Get HS code information (description, unit, etc).
        
        Args:
            hs_code: HS code to lookup
            
        Returns:
            Dict with keys: description, unit, or None if not found
        """
        if not self.db:
            logger.warning("Database not configured for HS code lookup")
            return None
        
        try:
            normalized = self.normalize_code(hs_code)
            info = self.db.get_hs_code_info(normalized)
            if info:
                return {
                    "hs_code": normalized,
                    "description": info.get("description", ""),
                    "unit": info.get("unit", ""),
                }
            return None
        except Exception as e:
            logger.error(f"Error looking up HS code {hs_code}: {e}")
            return None
    
    # ================================================================
    # CANDIDATE SUGGESTIONS
    # ================================================================
    
    def get_candidates(
        self,
        query: str,
        limit: int = 5,
        fuzzy: bool = True
    ) -> list[dict]:
        """
        Get candidate HS codes for a description/query.
        
        Used for fallback scenarios where HS code is not provided
        or is unknown. Queries the database for matching descriptions.
        
        Args:
            query: Search query (can be description or partial HS code)
            limit: Maximum number of candidates to return
            fuzzy: Enable fuzzy matching (approximate matches)
            
        Returns:
            List of dicts with keys: hs_code, description, score
            Empty list if no candidates found
        """
        if not self.db:
            logger.warning("Database not configured for HS code candidate search")
            return []
        
        if not query or not isinstance(query, str):
            return []
        
        try:
            # Try database lookup first
            if hasattr(self.db, "get_hs_code_candidates"):
                candidates = self.db.get_hs_code_candidates(
                    query,
                    limit=limit,
                    fuzzy=fuzzy
                )
                if candidates:
                    return candidates
            
            # Fallback: basic text matching
            return self._basic_text_match(query, limit)
        
        except Exception as e:
            logger.error(f"Error getting HS code candidates for '{query}': {e}")
            return []
    
    def _basic_text_match(self, query: str, limit: int) -> list[dict]:
        """
        Basic text matching fallback (case-insensitive substring match).
        Used if database doesn't support fuzzy search.
        """
        if not self.db:
            return []
        
        query_lower = query.lower().strip()
        if len(query_lower) < 2:
            return []
        
        candidates = []
        
        # Try to search database if it has a method
        if hasattr(self.db, "search_hs_codes"):
            try:
                results = self.db.search_hs_codes(query_lower, limit=limit)
                return results
            except Exception:
                pass
        
        return candidates
    
    # ================================================================
    # HIERARCHICAL LOOKUP
    # ================================================================
    
    def get_parent_codes(self, hs_code: str) -> list[str]:
        """
        Get parent HS codes at higher levels.
        
        Examples:
        - "0102.10.00" → ["0102.10", "0102"]
        - "0102.10" → ["0102"]
        - "0102" → []
        
        Args:
            hs_code: HS code string (normalized or not)
            
        Returns:
            List of parent codes from most specific to least specific
        """
        normalized = self.normalize_code(hs_code)
        clean = self.denormalize_code(normalized)
        
        parents = []
        if len(clean) == 8:
            parents.append(f"{clean[:4]}.{clean[4:6]}")
            parents.append(clean[:4])
        elif len(clean) == 6:
            parents.append(clean[:4])
        
        return parents
    
    def get_child_level(self, hs_code: str) -> str:
        """
        Get the hierarchical level of an HS code.
        
        Returns:
        - "section" for 4-digit codes
        - "chapter" for 6-digit codes
        - "subchapter" for 8-digit codes
        
        Args:
            hs_code: HS code string
            
        Returns:
            Level name
        """
        normalized = self.normalize_code(hs_code)
        clean = self.denormalize_code(normalized)
        
        if len(clean) == 4:
            return "section"
        elif len(clean) == 6:
            return "chapter"
        elif len(clean) == 8:
            return "subchapter"
        else:
            return "unknown"
    
    # ================================================================
    # UTILITY
    # ================================================================
    
    def extract_hs_code_from_text(self, text: str) -> Optional[str]:
        """
        Extract HS code from unstructured text.
        
        Looks for patterns like:
        - "0102.10.00"
        - "0102 1000"
        - "HS 0102.10.00"
        
        Args:
            text: Text to search
            
        Returns:
            Normalized HS code if found, None otherwise
        """
        if not text:
            return None
        
        # Pattern: 4-8 digits with optional dots/spaces
        pattern = r'\b(\d{4})[\.\s]?(\d{2})?[\.\s]?(\d{2})?\b'
        match = re.search(pattern, text)
        
        if match:
            digits = match.group(1)
            if match.group(2):
                digits += match.group(2)
            if match.group(3):
                digits += match.group(3)
            
            if self.is_valid_code(digits):
                return self.normalize_code(digits)
        
        return None
    
    def format_for_display(self, hs_code: str, include_description: bool = False) -> str:
        """
        Format HS code for display in responses.
        
        Args:
            hs_code: HS code to format
            include_description: Include description if available
            
        Returns:
            Formatted string
        """
        normalized = self.normalize_code(hs_code)
        
        if include_description:
            info = self.get_code_info(normalized)
            if info and info.get("description"):
                return f"{normalized} ({info['description']})"
        
        return normalized
