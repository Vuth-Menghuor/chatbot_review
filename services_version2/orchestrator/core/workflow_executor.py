"""
Workflow Executor Module - Two-Layer Intent Detection & Workflow Selection
============================================================================

Implements intelligent intent detection using:
  ✓ Layer 1 (Primary): MiniLM-based semantic classification (fast embeddings)
  ✓ Layer 2 (Fallback): Keyword/Rule-based detection (always available)

Features:
  - MiniLM embeddings (<100ms inference, no GPU required)
  - Semantic similarity to intent patterns
  - Automatic fallback from Layer 1 to Layer 2
  - Currency detection using MiniLM semantic matching
  - Comprehensive keyword/rule-based fallback system

Usage:
    executor = WorkflowExecutor()
    intent, confidence, source = executor.detect_intent(question)
    workflow_seq = executor.select_workflow(intent)
    currency, conf = executor.detect_currency(question)
"""

import logging
import numpy as np 
from .embedding_service import get_embedding_service
from ..llm_first_layer.shims.intent_service import IntentServiceConfig
from ..llm_first_layer import get_llm_first_layer_service as get_intent_service
import re
import os
from typing import Optional, Dict, Any, List, Tuple, Callable
from enum import Enum
from dataclasses import dataclass, field
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# ============================================================================
# Enums & Models
# ============================================================================

class WorkflowIntent(str, Enum):
    """Supported workflow intents."""
    CALCULATION = "calculation"
    TRADE_QUERY = "trade_query"
    DEFINITION = "definition"
    POLICY_QUERY = "policy_query"
    HS_CODE_LOOKUP = "hs_code_lookup"
    GENERAL = "general"


class IntentDetectionLayer(str, Enum):
    """Which layer provided the final intent."""
    LLM_PRIMARY = "layer_1_llm"
    KEYWORD_EXACT = "layer_2_keyword_exact"
    PATTERN_MATCH = "layer_2_pattern_regex"
    COMPOUND_RULE = "layer_2_compound_rule"
    FALLBACK = "layer_2_fallback"
    ERROR = "error"


@dataclass
class IntentDetectionResult:
    """Result from intent detection process."""
    intent: WorkflowIntent
    confidence: float  # 0.0 to 1.0
    source_layer: IntentDetectionLayer
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_in_scope: bool = True  # NEW: Track if question passed scope check
    scope_reason: Optional[str] = None  # NEW: Reason for scope decision
    
    def __str__(self):
        return (f"Intent={self.intent.value} | Confidence={self.confidence:.2f} | "
                f"Layer={self.source_layer.value} | Scope={'✓' if self.is_in_scope else '✗'} | Reason={self.reasoning[:50]}")


@dataclass
class WorkflowSequence:
    """Workflow sequence for a detected intent."""
    intent: WorkflowIntent
    primary_service: str
    secondary_services: List[str] = field(default_factory=list)
    fallback_service: str = "retrieval"
    description: str = ""


# ============================================================================
# Layer 2: Keyword & Rule-Based Detection (Fallback)
# ============================================================================

class KeywordMatcher:
    """
    Layer 2a: Exact keyword matching with confidence scoring.
    Fast, reliable, and always available.
    """
    
    # Keyword mappings to intents
    KEYWORDS = {
        WorkflowIntent.CALCULATION: [
            "calculate", "compute", "how much", "what cost", "what duty",
            "what tax", "tax for", "duty for", "dues", "import tax",
            "import cost", "determine tax", "determine duty", "tariff rate",
            "hs code tax", "duty amount", "tax amount", "how many", "compute",
            "figure out cost", "figure out duty", "figure out tax",
            "price", "cost", "rate", "percentage", "%"
        ],
        WorkflowIntent.HS_CODE_LOOKUP: [
            "hs code", "classify", "what code", "tariff code", "code for",
            "find code", "lookup code", "code classification", "classifier",
            "hs classification", "product code", "harmonized code",
            "schedule code", "chapter", "subheading", "harmonized tariff"
        ],
        WorkflowIntent.TRADE_QUERY: [
            "trade", "export", "import", "trade data", "trade volume",
            "shipping", "transport", "cargo", "freight", "trade flow",
            "trade route", "country", "data", "statistics", "volume",
            "flow", "direction", "bilateral"
        ],
        WorkflowIntent.DEFINITION: [
            "what is", "what are", "how is", "explain", "define",
            "tell me about", "describe", "what does", "meaning",
            "concept", "information", "knowledge", "background",
            "introduction to", "primer on"
        ],
        WorkflowIntent.POLICY_QUERY: [
            "policy", "procedure", "regulation", "requirement",
            "process", "steps", "how to", "compliance", "rule",
            "mechanism", "workflow", "procedure", "guideline",
            "instruction", "process of"
        ],
    }
    
    @classmethod
    def match(cls, question: str) -> Tuple[Optional[WorkflowIntent], float, str]:
        """
        Match question against keywords.
        
        Args:
            question: User question
            
        Returns:
            (intent, confidence, reasoning) or (None, 0.0, "No match")
        """
        q_lower = question.lower()
        
        # Count keyword matches per intent
        intent_scores = {}
        for intent, keywords in cls.KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in q_lower)
            if matches > 0:
                intent_scores[intent] = matches
        
        if not intent_scores:
            return None, 0.0, "No keywords matched"
        
        # Best matching intent
        best_intent = max(intent_scores, key=intent_scores.get)
        match_count = intent_scores[best_intent]
        total_possible = len(cls.KEYWORDS[best_intent])
        confidence = min(0.85, (match_count / total_possible) * 0.85)
        
        reasoning = f"Matched {match_count} keywords for {best_intent.value}"
        logger.debug(reasoning)
        
        return best_intent, confidence, reasoning


class PatternMatcher:
    """
    Layer 2b: Regex pattern matching for specialized intents.
    Detects specific patterns like product codes, numbers, etc.
    """
    
    PATTERNS = {
        WorkflowIntent.HS_CODE_LOOKUP: [
            r'\bHS\s+\d{2,6}\b',                   # "HS 0201", "HS 621212"
            r'\bHS\-?\d{2,6}\b',                   # "HS-0201"
            r'chapter\s+\d{2}\b',                  # "chapter 01"
            r'HS\s+code\s+for\s+\w+',             # "HS code for X"
            r'classify.*(?:product|goods|item)', # "classify products"
        ],
        WorkflowIntent.CALCULATION: [
            r'\$\s*\d+(?:,\d{3})*(?:\.\d{2})?',  # "$1,234.50"
            r'CIF.*\$',                            # "CIF $X"
            r'FOB\s+\$',                           # "FOB $X"
            r'\d+\s*(?:USD|EUR|KHR|THB|VND|GBP)', # "100 USD", "50 KHR"
            r'(?:calculate|compute).*(?:duty|tax|tariff)', # "calculate duty"
            r'\+\s*?\d+%',                         # "+ 50%"
        ],
        WorkflowIntent.TRADE_QUERY: [
            r'(?:trade|commerce).*between.*(?:country|countries)',
            r'(?:import|export)\s+(?:data|volume|statistics)',
            r'(?:country|nation|region)\s+(?:to|and)\s+(?:country|nation)',
        ],
    }
    
    @classmethod
    def match(cls, question: str) -> Tuple[Optional[WorkflowIntent], float, str]:
        """
        Match question against patterns.
        
        Args:
            question: User question
            
        Returns:
            (intent, confidence, reasoning) or (None, 0.0, "No match")
        """
        q_lower = question.lower()
        
        for intent, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, q_lower, re.IGNORECASE):
                    reasoning = f"Matched pattern '{pattern[:30]}...' for {intent.value}"
                    logger.debug(reasoning)
                    return intent, 0.80, reasoning  # Pattern match confidence: 0.80
        
        return None, 0.0, "No patterns matched"


class CompoundRuleEngine:
    """
    Layer 2c: Compound rules using multiple signals (keywords + patterns + logic).
    Handles complex queries that combine multiple intents.
    """
    
    def __init__(self):
        """Initialize compound rule engine."""
        self.rules: List[Tuple[Callable[[str], bool], WorkflowIntent, str]] = []
        self._register_rules()
    
    def _register_rules(self):
        """Register compound rules."""
        # Rule 1: Comparison query (implies calculation or trade query)
        self.rules.append((
            lambda q: bool(re.search(r'compare|difference|vs\.?|versus|versus', q, re.I)) and
                      bool(re.search(r'(?:HS|code|duty|tax|tariff|country|import|export)', q, re.I)),
            WorkflowIntent.CALCULATION,
            "Comparison query detected"
        ))
        
        # Rule 2: Multi-country trade query
        self.rules.append((
            lambda q: bool(re.search(r'(?:country|nation|region)', q, re.I)) and
                      bool(re.search(r'\d+', q)) and
                      bool(re.search(r'(?:trade|import|export|flow|route)', q, re.I)),
            WorkflowIntent.TRADE_QUERY,
            "Multi-country trade query detected"
        ))
        
        # Rule 3: Policy/procedure inquiry
        self.rules.append((
            lambda q: bool(re.search(r'(?:procedure|process|steps|how\s+to|guide)', q, re.I)) and
                      bool(re.search(r'(?:import|export|customs|clearance|duty)', q, re.I)),
            WorkflowIntent.POLICY_QUERY,
            "Policy/procedure inquiry detected"
        ))
        
        # Rule 4: HS code + calculation (combined intent)
        self.rules.append((
            lambda q: bool(re.search(r'(?:HS|code)', q, re.I)) and
                      bool(re.search(r'(?:calculate|tax|duty|cost)', q, re.I)),
            WorkflowIntent.CALCULATION,
            "HS code + calculation query detected"
        ))
    
    def evaluate(self, question: str) -> Tuple[Optional[WorkflowIntent], float, str]:
        """
        Evaluate compound rules.
        
        Args:
            question: User question
            
        Returns:
            (intent, confidence, reasoning) or (None, 0.0, "No rules matched")
        """
        for rule_fn, intent, reason in self.rules:
            try:
                if rule_fn(question):
                    logger.debug(reason)
                    return intent, 0.75, reason  # Compound rule confidence: 0.75
            except Exception as e:
                logger.warning(f"Compound rule evaluation failed: {e}")
        
        return None, 0.0, "No compound rules matched"


class Layer2FallbackDetector:
    """
    Layer 2: Complete keyword/rule-based fallback detection.
    Combines keyword matching, pattern matching, and compound rules.
    """
    
    def __init__(self):
        """Initialize Layer 2 detector."""
        self.keyword_matcher = KeywordMatcher()
        self.pattern_matcher = PatternMatcher()
        self.compound_engine = CompoundRuleEngine()
        
        logger.info("Layer 2 Fallback Detector initialized (Keyword + Pattern + Compound Rules)")
    
    def detect(self, question: str) -> IntentDetectionResult:
        """
        Detect intent using Layer 2 (keyword/rule-based).
        Falls through: Keyword → Pattern → Compound → Fallback.
        
        Args:
            question: User question
            
        Returns:
            IntentDetectionResult with Layer 2 source
        """
        # Try keyword matching first (highest confidence: 0.85)
        intent, confidence, reason = self.keyword_matcher.match(question)
        if intent:
            return IntentDetectionResult(
                intent=intent,
                confidence=0.85,  # Exact keyword match
                source_layer=IntentDetectionLayer.KEYWORD_EXACT,
                reasoning=reason,
            )
        
        # Try pattern matching (medium confidence: 0.80)
        intent, confidence, reason = self.pattern_matcher.match(question)
        if intent:
            return IntentDetectionResult(
                intent=intent,
                confidence=0.80,  # Pattern match
                source_layer=IntentDetectionLayer.PATTERN_MATCH,
                reasoning=reason,
            )
        
        # Try compound rules (lower confidence: 0.75)
        intent, confidence, reason = self.compound_engine.evaluate(question)
        if intent:
            return IntentDetectionResult(
                intent=intent,
                confidence=0.75,  # Compound rule match
                source_layer=IntentDetectionLayer.COMPOUND_RULE,
                reasoning=reason,
            )
        
        # Layer 2e: Check for GENERAL intent characteristics (informational queries)
        # Before falling back to default, explicitly detect general/informational queries
        is_general = self._detect_general_intent(question)
        if is_general:
            return IntentDetectionResult(
                intent=WorkflowIntent.GENERAL,
                confidence=0.65,  # General intent detection
                source_layer=IntentDetectionLayer.FALLBACK,
                reasoning="Informational query - no specific intent matched. Routed to Retrieval for general information.",
            )
        
        # Layer 2f: Final fallback - nothing matched
        # This should rarely happen if keywords and general detection are comprehensive
        logger.warning("[Layer 2] No match found in any detection layer → Using extreme fallback")
        return IntentDetectionResult(
            intent=WorkflowIntent.GENERAL,
            confidence=0.50,  # Extreme fallback
            source_layer=IntentDetectionLayer.FALLBACK,
            reasoning="No keywords, patterns, rules, or general characteristics detected - using fallback intent",
        )
    
    def _detect_general_intent(self, question: str) -> bool:
        """
        Detect GENERAL intent (informational queries).
        
        ⚠️ IMPORTANT: Double-check for HS code keywords!
        
        Even if question starts with "what is", if it contains HS code keywords,
        it's HS_CODE_LOOKUP, NOT GENERAL.
        
        Example:
        ✗ "What is the HS code for chickens?" → HS_CODE_LOOKUP (not GENERAL)
        ✓ "What is an HS code?" → GENERAL (general definition)
        
        GENERAL intent characteristics:
          - Asks for explanation/definition (what is, explain, how does)
          - Seeks background information (describe, background on)
          - NO specific intent parameters (no HS codes, no calculations, no lookups)
          - Broad informational scope (introduction, overview, concept)
        
        Args:
            question: User question
            
        Returns:
            True if question appears to be general/informational
        """
        question_lower = question.lower()
        
        # General intent indicators (information-seeking)
        general_indicators = [
            "what is", "what are", "how does", "how is", "explain",
            "define", "meaning of", "describe", "tell me about",
            "information", "background", "overview", "introduction",
            "basics of", "concept of", "what does", "how come", "why",
            "can you tell", "please tell", "information about", "describe"
        ]
        
        # Check if question contains general inquiry indicators
        has_general_indicator = any(ind in question_lower for ind in general_indicators)
        
        if has_general_indicator:
            # ⚠️ CRITICAL: Double-check for specific intent keywords
            # Even with general indicators, these keywords indicate specific intent
            
            # HS Code Lookup keywords
            hs_code_keywords = [
                "hs code", "classify", "classification", "tariff code",
                "product code", "code for", "hs ", "ahtn", "harmonized code"
            ]
            has_hs_keywords = any(kw in question_lower for kw in hs_code_keywords)
            
            # Calculation keywords
            calc_keywords = [
                "calculate", "compute", "how much", "total", "cost",
                "duty", "tax", "import tax", "import duty", "import cost",
                "cif", "fob", "value"
            ]
            has_calc_keywords = any(kw in question_lower for kw in calc_keywords)
            
            # Trade Query keywords
            trade_keywords = [
                "export", "import", "procedure", "document", "requirement",
                "steps for", "process of", "how do i", "how to import"
            ]
            has_trade_keywords = any(kw in question_lower for kw in trade_keywords)
            
            # Policy keywords
            policy_keywords = [
                "regulation", "rule", "requirement", "fta", "agreement",
                "policy", "compliance", "procedure", "regulation"
            ]
            has_policy_keywords = any(kw in question_lower for kw in policy_keywords)
            
            # HS code pattern match (e.g., "0102.29.11")
            has_hs_code_pattern = bool(re.search(r'\d{4}\.\d{2}\.\d{2}', question))
            
            # If question has ANY specific intent keywords → NOT GENERAL
            if (has_hs_keywords or has_calc_keywords or 
                has_trade_keywords or has_policy_keywords or 
                has_hs_code_pattern):
                # Build detailed reason for rejection
                reason_parts = []
                if has_hs_keywords:
                    reason_parts.append("HS code keywords")
                if has_calc_keywords:
                    reason_parts.append("calculation keywords")
                if has_trade_keywords:
                    reason_parts.append("trade keywords")
                if has_policy_keywords:
                    reason_parts.append("policy keywords")
                if has_hs_code_pattern:
                    reason_parts.append("HS code pattern")
                
                reason = ", ".join(reason_parts)
                logger.debug(
                    f"Question has general indicator BUT also has specific keywords ({reason}). "
                    f"Classification: SPECIFIC INTENT (not GENERAL). "
                    f"Question: '{question}'"
                )
                return False
            
            # No specific intent keywords found → It's GENERAL
            logger.debug(f"Detected GENERAL intent - informational query with no specific parameters. Question: '{question}'")
            return True
        
        return False


# ============================================================================
# Layer 1: MiniLM-Based Intent Detection (Primary)
# ============================================================================

class MiniLMLayer1Detector:
    """
    Layer 1: MiniLM-based intent detection using fast semantic embeddings.
    Primary method; provides semantic understanding without LLM API calls.
    
    Uses all-MiniLM-L12-v2:
      - Fast inference (<100ms)
      - No GPU required
      - 384-dimensional embeddings
      - Semantic similarity to intent patterns
    """
    
    def __init__(self):
        """Initialize MiniLM detector."""
        self.enabled = os.getenv("MINILM_INTENT_DETECTION_ENABLED", "true").lower() == "true"
        
        if not self.enabled:
            logger.info("MiniLM intent detection disabled via environment variable")
            self.detector = None
            self.available = False
            return
        
        try:
            self.detector = get_intent_service(IntentServiceConfig(provider="minilm"))
            self.available = True
            self.confidence_threshold = float(
                os.getenv("MINILM_CONFIDENCE_THRESHOLD", 0.75)
            )
            logger.info(f"✓ MiniLM Intent Detector (Layer 1) initialized")
            logger.info(f"  Model: all-MiniLM-L12-v2")
            logger.info(f"  Confidence threshold: {self.confidence_threshold}")
        except Exception as e:
            logger.error(f"Failed to initialize MiniLM detector: {e}")
            self.available = False
            self.detector = None
    
    def detect(self, question: str) -> Optional[IntentDetectionResult]:
        """
        Detect intent using MiniLM embeddings (semantic similarity approach).
        
        Returns None if MiniLM unavailable (triggers Layer 2 fallback).
        
        Args:
            question: User question
            
        Returns:
            IntentDetectionResult or None
        """
        if not self.available or not self.detector:
            return None
        
        try:
            # Use MiniLM for semantic intent classification
            intent, confidence, reasoning = self.detector.detect_intent(question)
            
            # Check confidence threshold
            if confidence >= self.confidence_threshold:
                logger.info(
                    f"[Layer 1 MiniLM] {intent.value} | "
                    f"Confidence: {confidence:.3f} | Score above threshold {self.confidence_threshold}"
                )
                return IntentDetectionResult(
                    intent=intent,
                    confidence=confidence,
                    source_layer=IntentDetectionLayer.LLM_PRIMARY,
                    reasoning=reasoning,
                )
            else:
                logger.debug(
                    f"[Layer 1 MiniLM] {intent.value} confidence {confidence:.3f} "
                    f"below threshold {self.confidence_threshold} → triggering Layer 2"
                )
                return None  # Trigger Layer 2 fallback
        
        except Exception as e:
            logger.warning(f"[Layer 1 MiniLM] Detection failed: {e}")
            return None  # Trigger Layer 2 fallback
    
    def detect_currency(self, question: str) -> Tuple[Optional[str], float]:
        """
        Detect currency using MiniLM semantic matching.
        
        Args:
            question: User question
            
        Returns:
            (currency_code, confidence) or (None, 0.0)
        """
        if not self.available or not self.detector:
            return None, 0.0
        
        try:
            currency, confidence, reasoning = self.detector.detect_currency(question)
            logger.debug(f"[Layer 1 Currency] {currency}: confidence={confidence:.3f}")
            return currency, confidence
        except Exception as e:
            logger.warning(f"[Layer 1 Currency] Detection failed: {e}")
            return None, 0.0



# ============================================================================
# Two-Layer Workflow Executor
# ============================================================================

class WorkflowExecutor:
    """
    Main workflow executor implementing two-layer intent detection.
    
    Layer 1 (Primary): LLM-based semantic classification (fast & accurate)
    Layer 2 (Fallback): Keyword/rule-based detection (always available)
    
    Features:
      - Automatic fallback from Layer 1 to Layer 2 on timeout/low confidence
      - Confidence scoring and reasoning
      - Workflow selection based on intent
      - Support for intent-based service routing
    """
    
    def __init__(self, use_llm: bool = True):
        """
        Initialize workflow executor with two-layer detection.
        
        Args:
            use_llm: Whether to use MiniLM for Layer 1 (default: True)
        """
        self.use_minilm = use_llm
        
        # Initialize Layer 1 (MiniLM)
        if use_llm:
            self.layer1_detector = MiniLMLayer1Detector()
        else:
            self.layer1_detector = None
        
        # Initialize Layer 2 (Keyword/Rule-based) - always available
        self.layer2_detector = Layer2FallbackDetector()
        
        # Workflow sequences
        self.workflows = self._init_workflows()
        
        logger.info("✓ WorkflowExecutor initialized with two-layer intent detection")
        logger.info(f"  Layer 1 (MiniLM): {('enabled' if use_llm and self.layer1_detector and self.layer1_detector.available else 'disabled')}")
        logger.info(f"  Layer 2 (Keyword/Rule): enabled (always available)")
    
    def detect_intent_with_scope_check(
        self,
        question: str,
        validators: Optional[Any] = None
    ) -> IntentDetectionResult:
        """
        Complete intent detection pipeline with scope checking.
        
        Pipeline (matches architecture Step 2 → Step 3):
          Step 2: Validate input + check scope (keywords)
            - If out-of-scope → return GENERAL intent with is_in_scope=False
            - If in-scope → proceed to Step 3
          Step 3: Detect intent using LLM (Layer 1) or Keyword/Rule (Layer 2)
            - LLM provides semantic understanding
            - Keyword/Rule serves as fallback
        
        Args:
            question: User question
            validators: Optional InputValidator instance (for scope check)
            
        Returns:
            IntentDetectionResult with scope and intent information
        """
        # Step 2: Scope validation (using keyword check)
        if validators:
            is_valid, reason = validators.validate_input(question)
            if not is_valid:
                if reason == "out_of_scope":
                    logger.warning(f"[Scope] Question out of scope: {question[:80]}")
                    return IntentDetectionResult(
                        intent=WorkflowIntent.GENERAL,
                        confidence=0.0,
                        source_layer=IntentDetectionLayer.ERROR,
                        reasoning="Question is outside customs domain scope",
                        is_in_scope=False,
                        scope_reason="No customs-related keywords detected",
                    )
                elif reason == "injection_detected":
                    logger.warning(f"[Security] Injection detected: {question[:80]}")
                    return IntentDetectionResult(
                        intent=WorkflowIntent.GENERAL,
                        confidence=0.0,
                        source_layer=IntentDetectionLayer.ERROR,
                        reasoning="Security check failed - potential injection detected",
                        is_in_scope=False,
                        scope_reason="Security violation",
                    )
        
        # Step 3: If in-scope, detect intent using two-layer system
        logger.debug(f"[Intent Detection] Processing in-scope question: {question[:80]}...")
        result = self.detect_intent(question)
        result.is_in_scope = True  # Mark as in-scope since we passed validation
        return result
    
    def detect_intent(self, question: str) -> IntentDetectionResult:
        """
        Two-layer intent detection (without scope check).
        
        NOTE: For the complete pipeline, use detect_intent_with_scope_check() instead!
        This method assumes the question has already been scope-checked.
        
        Algorithm:
          1. Try Layer 1 (MiniLM) - if available
             - Provides semantic understanding via embeddings
             - Fast (<100ms inference)
             - Returns confidence score (0.0-1.0 cosine similarity)
             - Falls back to Layer 2 if confidence < 0.75
          2. Try Layer 2 (Keyword/Rule-based) - always available
             - Layer 2a: Keyword exact match (confidence: 0.85)
             - Layer 2b: Regex pattern match (confidence: 0.80)
             - Layer 2c: Compound rules (confidence: 0.75)
             - Layer 2d: Final fallback (confidence: 0.50)
        
        Args:
            question: User question (should be scope-checked already)
            
        Returns:
            IntentDetectionResult with detected intent, confidence, and source layer
        """
        logger.debug(f"[Intent Detection] Processing: {question[:80]}...")
        
        # Layer 1: Try MiniLM if available
        if self.layer1_detector and self.layer1_detector.available:
            try:
                result = self.layer1_detector.detect(question)
                if result:
                    logger.info(f"✓ Layer 1 (MiniLM) success: {result}")
                    return result
            except Exception as e:
                logger.warning(f"Layer 1 failed: {e}")
        
        # Layer 2: Fallback to keyword/rule detection
        logger.debug("Falling back to Layer 2 (Keyword/Rule-based detection)")
        result = self.layer2_detector.detect(question)
        logger.info(f"✓ Layer 2 (Keyword/Rule) result: {result}")
        return result
    
    def select_workflow(self, intent: WorkflowIntent) -> WorkflowSequence:
        """
        Select workflow sequence based on detected intent.
        
        Args:
            intent: Detected intent
            
        Returns:
            WorkflowSequence with service routing
        """
        return self.workflows.get(intent, self.workflows[WorkflowIntent.GENERAL])
    
    def get_workflow_description(self, intent: WorkflowIntent) -> str:
        """
        Get human-readable workflow description.
        
        Args:
            intent: Detected intent
            
        Returns:
            Description string
        """
        workflow = self.select_workflow(intent)
        return workflow.description
    
    def detect_currency(self, question: str) -> Tuple[Optional[str], float]:
        """
        Detect currency using MiniLM semantic matching.
        
        Uses semantic embeddings to identify currency mentions in the question.
        Returns currency code (USD, KHR, EUR, etc.) and confidence score.
        
        Args:
            question: User question
            
        Returns:
            (currency_code, confidence) where currency_code is e.g. "USD", "KHR", "EUR"
            or (None, 0.0) if detection fails
            
        Example:
            >>> executor = WorkflowExecutor()
            >>> currency, conf = executor.detect_currency("Calculate tax for $500 from China")
            >>> print(f"Currency: {currency}, Confidence: {conf:.2f}")
            Currency: USD, Confidence: 0.87
        """
        if not self.layer1_detector or not hasattr(self.layer1_detector, 'detect_currency'):
            logger.debug("MiniLM currency detection not available")
            return None, 0.0
        
        try:
            currency, confidence = self.layer1_detector.detect_currency(question)
            return currency, confidence
        except Exception as e:
            logger.warning(f"Currency detection failed: {e}")
            return None, 0.0
    
    def _init_workflows(self) -> Dict[WorkflowIntent, WorkflowSequence]:
        """Initialize workflow sequences for each intent."""
        return {
            WorkflowIntent.CALCULATION: WorkflowSequence(
                intent=WorkflowIntent.CALCULATION,
                primary_service="calculator",
                secondary_services=[],
                fallback_service="retrieval",
                description="Route to Calculator service for duty/tax calculation"
            ),
            WorkflowIntent.HS_CODE_LOOKUP: WorkflowSequence(
                intent=WorkflowIntent.HS_CODE_LOOKUP,
                primary_service="retrieval",
                secondary_services=["calculator"],
                fallback_service="retrieval",
                description="Route to Retrieval service for HS code classification"
            ),
            WorkflowIntent.TRADE_QUERY: WorkflowSequence(
                intent=WorkflowIntent.TRADE_QUERY,
                primary_service="trade_data",
                secondary_services=[],
                fallback_service="retrieval",
                description="Route to Trade Data service for trade statistics"
            ),
            WorkflowIntent.DEFINITION: WorkflowSequence(
                intent=WorkflowIntent.DEFINITION,
                primary_service="retrieval",
                secondary_services=[],
                fallback_service="retrieval",
                description="Route to Retrieval service for definitions/information"
            ),
            WorkflowIntent.POLICY_QUERY: WorkflowSequence(
                intent=WorkflowIntent.POLICY_QUERY,
                primary_service="retrieval",
                secondary_services=[],
                fallback_service="retrieval",
                description="Route to Retrieval service for policy/procedure information"
            ),
            WorkflowIntent.GENERAL: WorkflowSequence(
                intent=WorkflowIntent.GENERAL,
                primary_service="retrieval",
                secondary_services=[],
                fallback_service="retrieval",
                description="Route to Retrieval service (fallback)"
            ),
        }


# ============================================================================
# Utility Functions
# ============================================================================

def create_executor() -> WorkflowExecutor:
    """
    Factory function to create a WorkflowExecutor.
    Respects LLM_INTENT_DETECTION_ENABLED environment variable.
    
    Returns:
        WorkflowExecutor instance
    """
    use_llm = os.getenv("LLM_INTENT_DETECTION_ENABLED", "true").lower() == "true"
    return WorkflowExecutor(use_llm=use_llm)


# ============================================================================
# Example Usage & Testing
# ============================================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    
    # Initialize executor
    executor = create_executor()
    
    # Test queries
    test_queries = [
        "Calculate the duty tax for importing $500 CIF laptop from China classified as HS 8471.30",
        "What is the HS code for cotton fabric?",
        "What is the trade volume between Cambodia and Vietnam?",
        "What does ATIGA mean in customs?",
        "What is the procedure for importing goods into Cambodia?",
        "How much tax will I pay?",
    ]
    
    print("\n" + "="*80)
    print("TWO-LAYER INTENT DETECTION TEST (with MiniLM Layer 1)")
    print("="*80)
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 80)
        
        # Detect intent
        result = executor.detect_intent(query)
        print(f"Result: {result}")
        
        # Select workflow
        workflow = executor.select_workflow(result.intent)
        print(f"Workflow: {workflow.primary_service} (primary) → {workflow.fallback_service} (fallback)")
        print(f"Description: {workflow.description}")
        
        # Detect currency if available
        if result.intent in [WorkflowIntent.CALCULATION, WorkflowIntent.TRADE_QUERY]:
            currency, conf = executor.detect_currency(query)
            if currency:
                print(f"Currency: {currency} (confidence: {conf:.3f})")
    
    # Test currency detection specifically
    print("\n" + "="*80)
    print("CURRENCY DETECTION TEST")
    print("="*80)
    
    currency_test_queries = [
        "Calculate tax for $500 from China",
        "How much in EUR?",
        "50,000 KHR goods",
        "1000 baht import",
        "Convert to USD",
    ]
    
    for query in currency_test_queries:
        print(f"\nQuery: {query}")
        currency, conf = executor.detect_currency(query)
        if currency:
            print(f"  → {currency} (confidence: {conf:.3f})")
        else:
            print(f"  → No currency detected (confidence: {conf:.3f})")
    
    print("\n" + "="*80)
