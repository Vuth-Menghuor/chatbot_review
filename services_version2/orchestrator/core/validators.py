"""
Validators Module - Input Validation & Scope Checking
=======================================================

Implements comprehensive input validation for orchestrator service:
  ✓ Security checks (injection detection)
  ✓ Scope checks (customs domain validation)
  ✓ Format validation (length, character whitelist)

Usage:
    validator = InputValidator()
    result = validator.validate_input(question)
    is_in_scope, scope_reason = validator.check_scope(question)
"""

import logging
import re
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of input validation."""
    is_valid: bool
    reason: str
    is_in_scope: bool = True
    scope_reason: str = ""
    scope_keywords_matched: List[str] = field(default_factory=list)


class InputValidator:
    """
    Comprehensive input validation for orchestrator service.
    
    Scope Keywords Organization:
    - Aligned with 6 intent types: HS_CODE_LOOKUP, CALCULATION, TRADE_QUERY, 
      POLICY_QUERY, DEFINITION, plus general customs keywords
    - Total: 100+ keywords across 6 categories
    
    Validation Pipeline:
    1. Security Check → Detect injection patterns
    2. Scope Check → Verify customs domain relevance (using 6 intent categories)
    3. Format Check → Length & character validation
    """

    def __init__(self):
        """Initialize validator with scope keywords."""
        self._init_scope_keywords()

    def _init_scope_keywords(self):
        """Initialize 6 categories of scope keywords matching intent types."""
        self.scope_keywords = {
            # Intent 1: HS Code Lookup (Retrieval Service)
            "hs_code_lookup": [
                "hs code", "hs", "ahtn", "harmonized code",
                "classify", "classification", "hs classification",
                "tariff code", "commodity code", "product code",
                "code for", "qip", "sez", "what is the code"
            ],
            # Intent 2: Calculation (Calculator Service)
            "calculation": [
                "calculate", "compute", "calculate tax", "calculate duty",
                "how much", "total", "cost", "import cost", "total cost",
                "duty", "tax", "import tax", "import duty", "special tax",
                "cif", "fob", "c&f", "value", "vat", "excise"
            ],
            # Intent 3: Trade Query (Trade Data Service)
            "trade_query": [
                "import", "export", "import procedure", "export procedure",
                "trade", "procedure", "process", "requirement", "requirements",
                "document", "documentation", "step", "steps for",
                "cargo", "freight", "shipping", "shipment", "goods", "commodity",
                "consignment", "customs procedure", "how to import", "how to export"
            ],
            # Intent 4: Policy Query (General info + Trade Data Service)
            "policy_query": [
                "regulation", "rule", "requirement", "fta",
                "free trade agreement", "agreement", "compliance",
                "policy", "law", "decree", "procedure",
                "rcep", "atiga", "asean", "arrangement",
                "what is", "what are", "definition", "define", "explain"
            ],
            # Intent 5: Definition (General knowledge)
            "definition": [
                "define", "definition", "meaning", "meaning of", "what is",
                "what are", "explain", "describe", "background", "overview",
                "introduction", "basics", "concept", "how does", "how is"
            ],
            # General scope keywords (applies to all)
            "customs_general": [
                "customs", "customs declaration", "customs procedure",
                "origin", "destination", "country", "from", "to",
                "invoice", "packing list", "bill of lading", "bol",
                "certificate", "permit", "document", "form",
                "cambodia", "asean", "trading", "commerce"
            ]
        }

    def validate_input(self, question: str) -> ValidationResult:
        """
        Full validation pipeline: Security → Scope → Format.
        
        Args:
            question: User input question
            
        Returns:
            ValidationResult with is_valid, reason, scope info
        """
        # Step 1: Security check
        is_secure, security_reason = self._check_security(question)
        if not is_secure:
            logger.warning(f"Security check failed: {security_reason}")
            return ValidationResult(
                is_valid=False,
                reason=security_reason,
                is_in_scope=False,
                scope_reason="Security check failed"
            )

        # Step 2: Scope check
        is_in_scope, scope_reason, matched_keywords = self._check_scope(question)
        if not is_in_scope:
            logger.debug(f"Out of scope: {scope_reason}")
            return ValidationResult(
                is_valid=False,
                reason=f"Question is out of scope: {scope_reason}",
                is_in_scope=False,
                scope_reason=scope_reason,
                scope_keywords_matched=matched_keywords
            )

        # Step 3: Format check
        is_formatted, format_reason = self._check_format(question)
        if not is_formatted:
            logger.warning(f"Format check failed: {format_reason}")
            return ValidationResult(
                is_valid=False,
                reason=format_reason,
                is_in_scope=True,
                scope_reason="Valid scope",
                scope_keywords_matched=matched_keywords
            )

        # All checks passed
        logger.debug(f"Input validation passed. Scope keywords: {matched_keywords}")
        return ValidationResult(
            is_valid=True,
            reason="Valid input",
            is_in_scope=True,
            scope_reason="Customs domain question",
            scope_keywords_matched=matched_keywords
        )

    def _check_security(self, question: str) -> Tuple[bool, str]:
        """
        Security check: Detect injection patterns.
        
        Args:
            question: User input
            
        Returns:
            (is_secure, reason)
        """
        # SQL injection patterns
        sql_patterns = [
            r"(\bor\b|\band\b).*['\"].*[=<>]",
            r"(drop|delete|update|insert|exec|execute|script)\s",
            r"(\-\-|;|\/\*|\*\/)",
            r"(union|select|from|where).*select",
        ]

        for pattern in sql_patterns:
            if re.search(pattern, question.lower()):
                return False, f"Potential SQL injection detected: {pattern}"

        # Prompt injection patterns
        if re.search(r"(ignore|forget|override|bypass|disregard).*instruction", question.lower()):
            return False, "Potential prompt injection detected"

        # Command injection patterns
        if re.search(r"`", question) or re.search(r"\$\(", question):
            return False, "Suspicious command characters detected"

        return True, "Security check passed"

    def _check_scope(self, question: str) -> Tuple[bool, str, List[str]]:
        """
        Scope check: Verify customs domain relevance.
        
        Uses 6 keyword categories to determine if question is in-scope.
        
        Args:
            question: User input
            
        Returns:
            (is_in_scope, reason, matched_keywords_list)
        """
        question_lower = question.lower()
        matched_keywords = []

        # Whitelist obvious small talk phrases so they pass scope validation
        norm = re.sub(r"[^\w\s]", "", question_lower).strip()
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "howdy", "greetings"]
        small_talk_patterns = [
            "thanks", "thank you", "appreciate",
            "bye", "goodbye", "farewell", "have a good day", "have a nice day",
            "nice to meet you", "pleasure to meet you", "glad to meet you",
            "how are you", "whats up", "how is your day", "hows your day", "hows it going", "how is it going",
            "tell me a joke", "tell a joke", "make me laugh", "joke", "roast me"
        ]
        if norm in greetings or any(re.search(rf"\b{re.escape(w)}\b", norm) for w in greetings) or any(re.search(rf"\b{re.escape(p)}\b", norm) for p in small_talk_patterns):
            return True, "Small talk query whitelisted", []

        # Allow concise product-only lookups such as "bus?" or "car.".
        # These are valid HS lookup entry points even when they do not yet
        # contain an explicit customs keyword.
        stripped = re.sub(r'[^a-z]', '', question_lower)
        if stripped and len(stripped) <= 5 and stripped.isalpha():
            return True, "Short product lookup accepted", []

        # Short product-like phrases: treat short noun phrases (<=5 words)
        # that contain known product tokens as in-scope.
        product_keywords = [
            "laptop", "phone", "computer", "car", "vehicle", "truck", "motorcycle",
            "bus", "rubber", "rice", "grain", "sugar", "oil", "fish", "meat",
            "textile", "fabric", "cloth", "cotton", "plastic", "metal", "machinery",
            "electronics", "device", "container", "bag", "footwear", "garment",
            "toy", "watch", "shoes", "clothing", "apparel", "furniture", "tool",
            "appliance", "glass", "paper", "wood", "steel", "iron", "copper",
            "aluminum", "chemical", "medicine", "gold", "silver", "jewelry",
            "cement", "excavator", "generator", "cable", "wire", "battery", "charger"
        ]
        words = re.findall(r"[A-Za-z]+", question_lower)
        if 0 < len(words) <= 5 and any(pk in question_lower for pk in product_keywords):
            matched = [pk for pk in product_keywords if pk in question_lower]
            return True, f"In-scope product phrase: {', '.join(matched[:3])}", matched

        # Short product question fallback (e.g., "what is ATIGA")
        m = re.search(r"(?:what is|what's|what are|define|tell me about)\s+([A-Za-z]{1,20})\b", question_lower)
        if m:
            candidate = m.group(1)
            if candidate.isalpha() and len(candidate) <= 5:
                return True, f"Short product question accepted: {candidate}", [candidate]

        # Check all categories for keyword matches
        for category, keywords in self.scope_keywords.items():
            for keyword in keywords:
                if keyword in question_lower:
                    matched_keywords.append(keyword)

        # If any keywords matched → in scope
        if matched_keywords:
            unique_keywords = list(set(matched_keywords))[:3]  # Top 3 for readability
            reason = f"In-scope customs domain. Keywords: {', '.join(unique_keywords)}"
            logger.debug(f"Scope check passed. Matched keywords: {matched_keywords[:5]}")
            return True, reason, matched_keywords

        # Out of scope: No customs keywords found
        reason = (
            "Out of scope: Question does not contain customs/trade domain keywords. "
            "Expected keywords from: HS code lookup, calculation, trade query, "
            "policy, definition, or general customs categories."
        )
        logger.debug(reason)
        return False, reason, []

    def _check_format(self, question: str) -> Tuple[bool, str]:
        """
        Format check: Length and character whitelist.
        
        Args:
            question: User input
            
        Returns:
            (is_formatted, reason)
        """
        normalized = question.strip()

        # Allow very short product-like lookups such as "bus?" or "car."
        # These are common HS-code entry points and are validated more
        # specifically by downstream intent routing.
        short_product = re.sub(r"[^a-z]", "", normalized.lower())
        if short_product and len(short_product) <= 5 and short_product.isalpha():
            return True, "Short product lookup accepted"

        # Length check
        if len(question) < 5:  # Allow shorter questions
            return False, "Question too short (minimum 5 characters)"

        if len(question) > 5000:
            return False, "Question too long (maximum 5000 characters)"

        # Character whitelist (allow common text + numbers + punctuation)
        # Allow: letters, numbers, punctuation, spaces, common symbols
        if not re.match(r"^[a-zA-Z0-9\s\.\,\?\!\-\:\;\'\"\(\)\/$&#+%@=]+$", question):
            return False, (
                "Question contains invalid characters. "
                "Allowed: letters, numbers, spaces, and basic punctuation"
            )

        return True, "Format check passed"

    def check_scope(self, question: str) -> Tuple[bool, str]:
        """
        Quick scope check without full validation.
        
        Args:
            question: User input
            
        Returns:
            (is_in_scope, reason)
        """
        is_in_scope, reason, _ = self._check_scope(question)
        return is_in_scope, reason

    def validate_scope_with_intent(
        self,
        question: str,
        detected_intent: str
    ) -> Tuple[bool, str]:
        """
        Validate scope + intent-specific validation.
        
        Some intents require additional scope confirmation.
        
        Args:
            question: User question
            detected_intent: Intent classification (e.g., "hs_code_lookup")
            
        Returns:
            (is_valid, reason)
        """
        # Basic scope check
        is_in_scope, scope_reason = self.check_scope(question)
        if not is_in_scope:
            return False, scope_reason

        # Intent-specific validation
        if detected_intent == "hs_code_lookup":
            # HS code lookups should have trade/commerce keywords
            if not any(kw in question.lower() for kw in 
                      ["import", "export", "hs", "classify", "product", "code"]):
                return False, "HS code lookup should mention import/export or products"

        elif detected_intent == "calculation":
            # Calculations should have financial keywords
            if not any(kw in question.lower() for kw in
                      ["calculate", "duty", "tax", "how much", "cost", "price"]):
                return False, "Calculation query should mention duty/tax/cost"

        elif detected_intent == "trade_query":
            # Trade queries should have procedure/requirement keywords
            if not any(kw in question.lower() for kw in
                      ["import", "export", "procedure", "requirement", "document"]):
                return False, "Trade query should mention import/export procedures"

        return True, "Scope and intent validation passed"

    def get_scope_keywords_by_category(self) -> Dict[str, List[str]]:
        """
        Get scope keywords organized by category.
        
        Useful for documentation and debugging.
        
        Returns:
            Dictionary mapping category name to keyword list
        """
        return self.scope_keywords

    def get_scope_summary(self) -> str:
        """
        Get summary of scope keywords.
        
        Returns:
            String summary of 6 intent-aligned keyword categories and keyword count
        """
        summary = "Scope Keywords by Intent Category:\n"
        for category, keywords in self.scope_keywords.items():
            summary += f"  • {category}: {len(keywords)} keywords\n"
        total = sum(len(kws) for kws in self.scope_keywords.values())
        summary += f"  Total: {total} keywords across 6 intent categories"
        return summary


# Singleton instance factory
_validator_instance: Optional[InputValidator] = None


def get_validator() -> InputValidator:
    """
    Get or create singleton validator instance.
    
    Returns:
        InputValidator instance
    """
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = InputValidator()
        logger.info("Initialized InputValidator singleton")
    return _validator_instance
