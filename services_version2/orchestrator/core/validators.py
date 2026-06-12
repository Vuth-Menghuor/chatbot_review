"""
Validators Module - Input Validation & Scope Checking
=======================================================

Implements comprehensive input validation for orchestrator service:
  ✓ Security checks (injection detection)
  ✓ Scope checks (Pass-through to let prompt layer handle boundaries)
  ✓ Format validation (length boundaries)

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
    
    Validation Pipeline:
    1. Security Check → Detect injection patterns
    2. Scope Check → Lenient gateway pass-through supporting prompt routing
    3. Format Check → Length boundary confirmation
    """

    def __init__(self):
        """Initialize validator with scope keywords."""
        self._init_scope_keywords()

    def _init_scope_keywords(self):
        """Initialize keyword maps purely for legacy tracking compatibility."""
        self.scope_keywords = {
            "hs_code_lookup": ["hs code", "hs", "classify", "classification", "tariff code", "commodity code", "product code"],
            "calculation": ["calculate", "compute", "duty", "tax", "cif", "fob", "vat"],
            "trade_query": ["import", "export", "trade", "procedure", "process", "requirement", "shipping"],
            "policy_query": ["regulation", "rule", "fta", "agreement", "compliance", "policy", "law", "decree"],
            "definition": ["define", "definition", "meaning", "explain", "describe"],
            "customs_general": ["customs", "declaration", "invoice", "packing list", "certificate", "cambodia"]
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

        # Step 2: Scope check (Lenient Gateway Pass-through)
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
        """Security check: Detect malicious injection patterns."""
        sql_patterns = [
            r"(\bor\b|\band\b).*['\"].*[=<>]",
            r"(drop|delete|update|insert|exec|execute|script)\s",
            r"(\-\-|;|\/\*|\*\/)",
            r"(union|select|from|where).*select",
        ]

        for pattern in sql_patterns:
            if re.search(pattern, question.lower()):
                return False, f"Potential SQL injection detected: {pattern}"

        if re.search(r"(ignore|forget|override|bypass|disregard).*instruction", question.lower()):
            return False, "Potential prompt injection detected"

        if re.search(r"`", question) or re.search(r"\$\(", question):
            return False, "Suspicious command characters detected"

        return True, "Security check passed"

    def _check_scope(self, question: str) -> Tuple[bool, str, List[str]]:
        """
        Lenient Scope Gateway Pass-through.
        Trusts length-compliant strings and hands them over to the LLM Few-Shot 
        Intent Detector to perform advanced categorization.
        """
        question_lower = question.lower()
        
        # Check for small talk greetings using whole words
        greetings = ["hello", "hi", "hey", "greetings", "good morning", "good afternoon", "good evening", "howdy"]
        words = re.findall(r'\b\w+\b', question_lower)
        if any(g in words for g in greetings):
            return True, "Small talk query whitelisted", []

        matched_keywords = []

        # Gather any matched keywords purely for system tracing metrics
        for category, keywords in self.scope_keywords.items():
            for keyword in keywords:
                if keyword in question_lower:
                    matched_keywords.append(keyword)

        return True, "Passed to prompt-driven intent classifier layer", matched_keywords

    def _check_format(self, question: str) -> Tuple[bool, str]:
        """Format check: Basic text length boundaries."""
        if len(question) < 3:
            return False, "Question too short (minimum 3 characters)"

        if len(question) > 5000:
            return False, "Question too long (maximum 5000 characters)"

        return True, "Format check passed"

    def check_scope(self, question: str) -> Tuple[bool, str]:
        is_in_scope, reason, _ = self._check_scope(question)
        return is_in_scope, reason

    def validate_scope_with_intent(
        self,
        question: str,
        detected_intent: str
    ) -> Tuple[bool, str]:
        """
        Lenient Scope + Intent validation gateway rule.
        Always returns True to prevent hardcoded keyword gates from blocking 
        legitimate naked commodity details routed by the LLM Intent Engine.
        """
        logger.info(f"Pass-through gate accepted intent: {detected_intent}")
        return True, "Scope and intent validation passed via prompt-driven pass-through"

    def get_scope_keywords_by_category(self) -> Dict[str, List[str]]:
        return self.scope_keywords

    def get_scope_summary(self) -> str:
        summary = "Scope Keywords by Intent Category:\n"
        for category, keywords in self.scope_keywords.items():
            summary += f"  • {category}: {len(keywords)} keywords\n"
        total = sum(len(kws) for kws in self.scope_keywords.values())
        summary += f"  Total: {total} keywords across 6 intent categories"
        return summary


# Singleton instance factory
_validator_instance: Optional[InputValidator] = None


def get_validator() -> InputValidator:
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = InputValidator()
        logger.info("Initialized InputValidator singleton")
    return _validator_instance