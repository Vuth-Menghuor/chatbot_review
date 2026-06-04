"""Validator service implementation (moved into llm_first_layer shims).

Provides a rule-based validator and lightweight async hooks used by the
orchestrator tests. This implements the APIs expected by
`tests/test_validator_service.py` so the module can be moved without
breaking callers.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Any, Dict, List
import re
import asyncio


class ValidationDecision(str, Enum):
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    INJECTION = "injection"
    FORMAT_ERROR = "format_error"
    AMBIGUOUS = "ambiguous"


@dataclass
class ValidationResult:
    decision: ValidationDecision
    is_valid: bool
    reason: Optional[str] = None
    scope_keywords_matched: Optional[List[str]] = None
    provider: Optional[str] = None

    @property
    def is_in_scope(self) -> bool:
        return self.decision == ValidationDecision.IN_SCOPE

    @classmethod
    def in_scope(cls, reason: Optional[str] = None, keywords: Optional[List[str]] = None, provider: Optional[str] = None):
        return cls(decision=ValidationDecision.IN_SCOPE, is_valid=True, reason=reason, scope_keywords_matched=keywords or [], provider=provider)

    @classmethod
    def out_of_scope(cls, reason: Optional[str] = None):
        return cls(decision=ValidationDecision.OUT_OF_SCOPE, is_valid=False, reason=reason)

    @classmethod
    def injection(cls, reason: Optional[str] = None):
        return cls(decision=ValidationDecision.INJECTION, is_valid=False, reason=reason)

    @classmethod
    def format_error(cls, reason: Optional[str] = None):
        return cls(decision=ValidationDecision.FORMAT_ERROR, is_valid=False, reason=reason)

    @classmethod
    def ambiguous(cls, reason: Optional[str] = None):
        return cls(decision=ValidationDecision.AMBIGUOUS, is_valid=False, reason=reason)

    def to_simple_tuple(self) -> Tuple[bool, Optional[str]]:
        if self.is_valid:
            return True, None
        if self.decision == ValidationDecision.OUT_OF_SCOPE:
            return False, "out_of_scope"
        if self.decision == ValidationDecision.INJECTION:
            return False, "injection_detected"
        if self.decision == ValidationDecision.FORMAT_ERROR:
            return False, f"format_error:{self.reason or 'invalid'}"
        if self.decision == ValidationDecision.AMBIGUOUS:
            return False, "out_of_scope"
        return False, self.reason


class RuleBasedValidatorProvider:
    """Simple, deterministic rule-based validator used as stage 1.

    The heuristics here are intentionally conservative to match tests: clear
    injections and out-of-scope queries are rejected; short product names may
    pass heuristically; unknown inputs are marked ambiguous.
    """

    BLOCKLIST = [
        r"\b(recipe|cooking|pasta|movie|film|invest|investment|cryptocurrency|football|gambling|betting)\b",
    ]

    INJECTION_PATTERNS = [
        r"ignore all previous",
        r"you are now",
        r"act as",
        r"drop table",
        r"union select",
        r"ignore previous",
        r"jailbreak",
    ]

    SCOPE_KEYWORDS = {
        "calculation": ["calculate", "compute", "duty", "tax", "import", "cif", "hs code", "hs"],
        "hs_code_lookup": ["hs code", "classify", "what code", "tariff code", "lookup code"],
        "trade_query": ["trade", "export", "import", "shipping", "freight"],
    }

    # Certificate detection patterns reused by orchestrator
    CERT_PATTERNS = [
        r'form\s*d',
        r'form\s*e',
        r'certificate\s+of\s+origin',
        r'form\s*ak',
        r'form\s*aj',
        r'prakas',
        r'qip\s+certificate',
        r'qip',
        r'fta\s+certificate',
        r'origin\s+certificate',
    ]

    def is_available(self) -> bool:
        return True

    def validate(self, text: str) -> ValidationResult:
        t = (text or "").strip()
        if not t:
            return ValidationResult.format_error("empty")

        if len(t) > 5000:
            return ValidationResult.format_error("too long")

        low = t.lower()

        # Injection checks
        for p in self.INJECTION_PATTERNS:
            if re.search(p, low):
                return ValidationResult.injection("injection detected")

        # Whitelist obvious small talk phrases
        norm = re.sub(r"[^\w\s]", "", low).strip()
        greetings = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening", "howdy", "greetings"]
        small_talk_patterns = [
            "thanks", "thank you", "appreciate",
            "bye", "goodbye", "farewell", "have a good day", "have a nice day",
            "nice to meet you", "pleasure to meet you", "glad to meet you",
            "how are you", "whats up", "how is your day", "hows your day", "hows it going", "how is it going",
            "tell me a joke", "tell a joke", "make me laugh", "joke", "roast me"
        ]
        if norm in greetings or any(re.search(rf"\b{re.escape(w)}\b", norm) for w in greetings) or any(re.search(rf"\b{re.escape(p)}\b", norm) for p in small_talk_patterns):
            return ValidationResult.in_scope("small_talk_whitelist")

        # Blocklist/out-of-scope
        for p in self.BLOCKLIST:
            if re.search(p, low):
                return ValidationResult.out_of_scope("out_of_scope")

        # Scope keyword match
        matched = []
        for cat, kws in self.SCOPE_KEYWORDS.items():
            for kw in kws:
                if kw in low:
                    matched.append(kw)
        if matched:
            return ValidationResult.in_scope("ok", keywords=matched)

        # Short product-like strings: treat as in-scope heuristically
        # Accept short single-word product tokens even if they include
        # trailing punctuation (e.g., "bus?", "car."). Strip non-alpha
        # characters before checking length.
        stripped = re.sub(r'[^a-z]', '', low)
        if stripped and len(stripped) <= 5 and stripped.isalpha():
            return ValidationResult.in_scope("short_product")

        # If the input is a short single-token question like "what is ATIGA",
        # extract the candidate token and treat as short product when appropriate.
        m = re.search(r"(?:what is|what's|what are|define|tell me about)\s+([A-Za-z]{1,20})\b", low)
        if m:
            candidate = m.group(1)
            if candidate.isalpha() and len(candidate) <= 5:
                return ValidationResult.in_scope("short_product_question", keywords=[candidate])

        # Short product-like phrases: treat short noun phrases (<=5 words)
        # that contain known product tokens as in-scope. This handles cases
        # like "pick up truck" or "used pickup truck" which are short
        # product descriptions and should route to HS lookup.
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
        words = re.findall(r"[A-Za-z]+", low)
        if 0 < len(words) <= 5 and any(pk in low for pk in product_keywords):
            # Return in-scope and include matched keywords for debugging
            matched = [pk for pk in product_keywords if pk in low]
            return ValidationResult.in_scope("short_product_phrase", keywords=matched)

        # Otherwise ambiguous
        return ValidationResult.ambiguous()

    # Certificate helpers
    def mentions_certificate(self, text: str) -> bool:
        if not text:
            return False
        t = text.lower()
        for p in self.CERT_PATTERNS:
            if re.search(p, t):
                return True
        return False

    def extract_certificate_type(self, text: str) -> Optional[str]:
        if not text:
            return None
        t = text.lower()
        if re.search(r'form\s*d', t):
            return 'FORM_D'
        if re.search(r'form\s*e', t):
            return 'FORM_E'
        if 'acfta' in t or ('china' in t and 'form e' in t):
            return 'ACFTA'
        if 'qip' in t:
            return 'QIP'
        if 'certificate of origin' in t:
            return 'COO'
        return None

    def is_short_rate_reply(self, text: str) -> bool:
        if not text:
            return False
        t = text.strip().lower()
        if re.match(r'^(?:\d+(?:\.\d+)?\s*%?|duty[-\s]?free|zero|0)$', t):
            return True
        if re.match(r'^\d+(?:\.\d+)?$', t):
            return True
        return False

    def check_scope(self, question: str) -> Tuple[bool, Optional[str]]:
        r = self.validate(question)
        ok, reason = r.to_simple_tuple()
        return ok, reason

    def validate_calculation_input(self, text: str) -> Tuple[bool, Optional[List[str]]]:
        # Minimal checks: presence of HS or product and a value/currency
        low = (text or "").lower()
        has_value = bool(re.search(r"\$|\busd\b|\bcif\b|value|price", low))
        has_product = bool(
            re.search(r"hs\s*\d", low)
            or re.search(r"\bproduct\b", low)
            or re.search(r"\bfor\s+[a-z]{4,}", low)
        )
        if has_value and has_product:
            return True, None
        missing = []
        if not has_product:
            missing.append("product/hs_code")
        if not has_value:
            missing.append("customs_value")
        return False, missing

    # Backward-compatible helper used by older code expecting a simple
    # validation function for calculation fields
    def validate_calculation_required_fields(self, question: str) -> Tuple[bool, Optional[List[str]]]:
        return self.validate_calculation_input(question)

    def get_scope_keywords_by_category(self) -> Dict[str, List[str]]:
        return {k: list(v) for k, v in self.SCOPE_KEYWORDS.items()}

    def get_scope_summary(self) -> str:
        total = sum(len(v) for v in self.SCOPE_KEYWORDS.values())
        return f"Total scope keywords: {total}"


class OutputValidator:
    def validate_response(self, response: str) -> Tuple[bool, Optional[str]]:
        if not response or not response.strip():
            return False, "empty"
        if len(response.strip()) < 10:
            return False, "too short"
        low = response.lower()
        if "api_key" in low or "password" in low:
            return False, "dangerous_content"
        return True, None


class ValidatorServiceConfig:
    def __init__(self, **kwargs):
        self.enable_llm_fallback = kwargs.get("enable_llm_fallback", False)


class ValidatorService:
    def __init__(self, config: Optional[ValidatorServiceConfig] = None):
        self.config = config or ValidatorServiceConfig()
        self._provider = RuleBasedValidatorProvider()
        self._llm_provider = None

    def validate_input(self, text: str) -> Tuple[bool, Optional[str]]:
        r = self._provider.validate(text)
        ok, reason = r.to_simple_tuple()
        return ok, reason

    async def validate_input_async(self, text: str) -> Tuple[bool, Optional[str]]:
        r = self._provider.validate(text)
        if r.decision == ValidationDecision.AMBIGUOUS and self.config.enable_llm_fallback:
            # Simulate calling LLM provider if available
            if hasattr(self, "_llm_provider") and self._llm_provider:
                res = await self._llm_provider.validate_async(text)
                ok, reason = res.to_simple_tuple()
                return ok, reason
            return False, "out_of_scope"
        return r.to_simple_tuple()

    def validate_input_full(self, text: str) -> ValidationResult:
        return self._provider.validate(text)

    async def validate_input_full_async(self, text: str) -> ValidationResult:
        return self._provider.validate(text)

    def validate_scope_with_intent(self, text: str, intent: str) -> Tuple[bool, Optional[str]]:
        # For now, delegate to provider and do a simple check
        ok, reason = self.validate_input(text)
        return ok, reason

    def validate_calculation_input(self, text: str) -> Tuple[bool, Optional[List[str]]]:
        return self._provider.validate_calculation_input(text)

    def get_scope_keywords_by_category(self):
        return self._provider.get_scope_keywords_by_category()

    def get_scope_summary(self):
        return self._provider.get_scope_summary()


# Singleton factories expected by tests
_input_validator_instance: Optional[ValidatorService] = None
_output_validator_instance: Optional[OutputValidator] = None


def get_input_validator() -> ValidatorService:
    global _input_validator_instance
    if _input_validator_instance is None:
        _input_validator_instance = ValidatorService()
    return _input_validator_instance


def get_output_validator() -> OutputValidator:
    global _output_validator_instance
    if _output_validator_instance is None:
        _output_validator_instance = OutputValidator()
    return _output_validator_instance


def get_validator() -> ValidatorService:
    return get_input_validator()


# Backward-compat aliases
InputValidator = ValidatorService


__all__ = [
    "ValidationDecision",
    "ValidationResult",
    "RuleBasedValidatorProvider",
    "OutputValidator",
    "ValidatorService",
    "ValidatorServiceConfig",
    "get_input_validator",
    "get_output_validator",
    "get_validator",
    "InputValidator",
]


# Compatibility helpers mirroring the previous standalone validators API
def mentions_certificate(text: str) -> bool:
    return get_input_validator()._provider.mentions_certificate(text)


def extract_certificate_type(text: str) -> Optional[str]:
    return get_input_validator()._provider.extract_certificate_type(text)


def is_short_rate_reply(text: str) -> bool:
    return get_input_validator()._provider.is_short_rate_reply(text)


def get_certificate_validator() -> ValidatorService:
    return get_input_validator()


def is_acfta(text: str) -> bool:
    """Return True when the text mentions ACFTA (or equivalent Form E for China)."""
    cert = extract_certificate_type(text)
    return cert == 'ACFTA'


