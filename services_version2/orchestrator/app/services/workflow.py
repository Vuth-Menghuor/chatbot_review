"""
Core Workflow Module - Orchestrator service
Handles workflow coordination, sequencing, and fallback policies
Uses LLM-based intent detection (with keyword fallback)
"""

import logging
import re
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

# Import LLM intent detector (optional - will fallback to keyword if unavailable)
try:
    from ..ai.shims.intent_service import OrchestratorIntentService, IntentServiceConfig
    from ..ai import get_llm_first_layer_service as get_intent_service
    LLM_INTENT_DETECTION_AVAILABLE = True
except ImportError:
    logger.warning("LLM intent detector not available, will use keyword-based detection")
    LLM_INTENT_DETECTION_AVAILABLE = False

# Currency detector: no standalone currency_service module exists;
# currency detection is handled by pattern matching and llm_service fallback.
LLM_CURRENCY_DETECTION_AVAILABLE = False

from ..core.config import WorkflowIntent


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CLARIFICATION_REQUIRED = "clarification_required"


@dataclass
class WorkflowContext:
    """
    Context for a single workflow execution.
    Tracks state, results, and metadata across service calls.
    """
    request_id: str
    question: str
    session_id: Optional[str] = None
    _intent: Optional[WorkflowIntent] = None
    status: WorkflowStatus = WorkflowStatus.PENDING
    
    # Input rewriting (context-aware input processing)
    original_input: Optional[str] = None
    rewritten_input: Optional[str] = None
    rewrite_metadata: Optional[Dict[str, Any]] = None
    session_context: Optional[Any] = None  # SessionContext from input_rewriter
    cleaned_input: Optional[str] = None  # Query after filler pattern removal
    
    # Clarification state
    clarification_locked_intent: Optional[WorkflowIntent] = None  # Intent locked from clarification resolution
    skip_intent_detection: bool = False  # When True, use locked intent instead of detecting
    clarification_confidence: float = 0.0  # Confidence score for locked intent (0.0 to 1.0)
    
    # Results from service calls
    retrieval_result: Optional[Dict[str, Any]] = None
    calculation_result: Optional[Dict[str, Any]] = None
    trade_query_result: Optional[Dict[str, Any]] = None
    small_talk_result: Optional[Dict[str, Any]] = None
    
    # Currency extraction (for calculation workflows)
    detected_currency: Optional[str] = None
    currency_confidence: float = 0.0
    
    # Metadata
    start_time: float = None
    end_time: float = None
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = None  # Additional metadata like hs_validation
    
    # Error tracking
    errors: List[str] = None
    clarifications: List[str] = None

    @property
    def intent(self) -> Optional[WorkflowIntent]:
        if hasattr(self, "_intent") and self.metadata and self.metadata.get("_safety_gate_postponed"):
            import inspect
            frame = inspect.currentframe().f_back
            caller_name = frame.f_code.co_name if frame else "unknown"
            if caller_name not in ["process_query", "_process_query_core", "_apply_intent_safety_gate", "detect_intent_with_confidence"]:
                logger.warning(
                    f"🚨 [WARNING] context.intent read while safety gate is postponed! "
                    f"Caller: {caller_name}. Value is provisional."
                )
        return self._intent

    @intent.setter
    def intent(self, value: Optional[WorkflowIntent]):
        self._intent = value
    
    def __post_init__(self):
        """Initialize default values."""
        if self.start_time is None:
            self.start_time = time.time()
        if self.errors is None:
            self.errors = []
        if self.clarifications is None:
            self.clarifications = []
        if self.metadata is None:
            self.metadata = {}
    
    def add_error(self, error: str):
        """Add error message."""
        self.errors.append(error)
        logger.error(f"[{self.request_id}] {error}")
    
    def add_clarification(self, clarification: str):
        """Add clarification needed."""
        self.clarifications.append(clarification)
        logger.info(f"[{self.request_id}] Clarification: {clarification}")
    
    def set_result(self, result_type: str, result: Dict[str, Any]):
        """
        Set result for a service call.
        
        Args:
            result_type: Type of result (retrieval, calculation, trade_query, small_talk)
            result: The result dictionary
        """
        if result_type == "retrieval":
            self.retrieval_result = result
        elif result_type == "calculation":
            self.calculation_result = result
        elif result_type == "trade_query":
            self.trade_query_result = result
        elif result_type == "small_talk":
            self.small_talk_result = result

    def get_result(self, result_type: str) -> Optional[Dict[str, Any]]:
        """Get result for a service call."""
        if result_type == "retrieval":
            return self.retrieval_result
        elif result_type == "calculation":
            return self.calculation_result
        elif result_type == "trade_query":
            return self.trade_query_result
        elif result_type == "small_talk":
            return self.small_talk_result
        return None
    
    def finalize(self):
        """Mark workflow as completed and calculate latency."""
        self.end_time = time.time()
        self.latency_ms = (self.end_time - self.start_time) * 1000
        
        if not self.errors and self.status == WorkflowStatus.PENDING:
            self.status = WorkflowStatus.COMPLETED


class WorkflowExecutor:
    """
    Manages workflow execution and coordination.
    Implements sequencing, fallback policies, and service orchestration.
    Uses LLM-based intent detection with keyword fallback.
    """
    
    def __init__(self, policy_engine=None, use_llm_intent: bool = True, llm_intent_timeout: int = 60, llm_service: Optional[Any] = None):
        """
        Initialize workflow executor.
        
        Args:
            policy_engine: Policy engine for intent detection and rules
            use_llm_intent: Whether to use LLM for intent detection (vs keyword matching)
            llm_intent_timeout: Timeout for LLM intent detection in seconds
            llm_service: Optional provider-neutral LLM abstraction layer
        """
        self.policy_engine = policy_engine
        self.llm_service = llm_service
        self.use_llm_intent = use_llm_intent and LLM_INTENT_DETECTION_AVAILABLE
        
        # Initialize LLM detector if enabled
        if self.use_llm_intent:
            try:
                self.llm_detector = get_intent_service(IntentServiceConfig(timeout=llm_intent_timeout))
                logger.info(f"LLM-based intent detection enabled (timeout: {llm_intent_timeout}s)")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM detector: {e}, falling back to keyword detection")
                self.use_llm_intent = False
                self.llm_detector = None
        else:
            self.llm_detector = None
            logger.info("Keyword-based intent detection enabled")
        
    def detect_intent_with_confidence(self, question: str) -> Tuple[WorkflowIntent, float]:
        """
        Detect intent and return (intent, confidence).

        LLM/MiniLM path returns the model confidence directly.
        Keyword fallback returns a deterministic confidence tier:
          - keyword exact match  → 0.85
          - pattern match        → 0.80
          - compound rule        → 0.75
          - ultimate fallback    → 0.50
        """
        # LLM facade path
        if self.llm_service and hasattr(self.llm_service, "classify_intent"):
            try:
                intent_raw, confidence, reasoning = self.llm_service.classify_intent(question)
                intent_value = getattr(intent_raw, "value", intent_raw)
                try:
                    intent = WorkflowIntent(str(intent_value))
                except ValueError:
                    intent = WorkflowIntent.UNCLASSIFIED
                logger.info(f"[Intent+Conf] LLM facade: {intent.value} conf={confidence:.2f}")
                return intent, confidence
            except Exception as e:
                logger.warning(f"LLM facade failed, falling back: {e}")

        # Native LLM detector path
        if self.use_llm_intent and self.llm_detector:
            try:
                intent, confidence, reasoning = self.llm_detector.detect_intent(question)
                logger.info(f"[Intent+Conf] LLM: {intent.value} conf={confidence:.2f}")
                return intent, confidence
            except Exception as e:
                logger.warning(f"LLM detection failed, falling back: {e}")

        # Keyword fallback — assign confidence tiers
        intent = self._keyword_based_intent_detection(question)
        q_lower = question.lower()
        import re as _re
        # Heuristic confidence from keyword density
        kw_maps = {
            WorkflowIntent.CALCULATION:   ["calculate", "compute", "how much", "duty", "tax"],
            WorkflowIntent.HS_CODE_LOOKUP: ["hs code", "classify", "code for", "tariff code"],
            WorkflowIntent.TRADE_QUERY:   ["trade", "export", "import", "shipping"],
            WorkflowIntent.GENERAL:       ["procedure", "regulation", "requirement", "compliance", "what is", "define", "meaning", "explain"],
        }
        hits = sum(1 for kw in kw_maps.get(intent, []) if kw in q_lower)
        confidence = min(0.85, 0.55 + hits * 0.06)
        logger.debug(f"[Intent+Conf] Keyword: {intent.value} conf={confidence:.2f} (hits={hits})")
        return intent, confidence

    def detect_currency(self, question: str, confidence_threshold: float = 0.6) -> Tuple[Optional[str], float]:
        """
        Detect currency with strict priority:
        1. Regex/keyword detection
        2. LLM detection via currency_detector
        3. Country mention -> currency mapping
        4. Default KHR

        Args:
            question: User question (string)
            confidence_threshold: Minimum confidence score (0.0-1.0)

        Returns:
            (currency_code, confidence)
        """

        # 1) Pattern-based detection (existing)
        pattern_currency, pattern_confidence = self._pattern_based_currency_detection(question, confidence_threshold)
        if pattern_currency != "KHR" or pattern_confidence > 0.0:
            logger.info(f"[Currency Detection] Pattern matched: {pattern_currency} (confidence: {pattern_confidence:.3f})")
            return pattern_currency, pattern_confidence

        # 2) LLM-based detection through provider-neutral llm_service
        if self.llm_service and hasattr(self.llm_service, "detect_currency"):
            try:
                detected_currency, confidence, reasoning = self.llm_service.detect_currency(question)
                if detected_currency and confidence >= confidence_threshold:
                    logger.info(
                        f"[Currency Detection] LLM service detected: {detected_currency} "
                        f"(confidence: {confidence:.3f})"
                    )
                    return detected_currency, confidence
                else:
                    logger.debug(
                        f"[Currency Detection] LLM service low-confidence or no result: "
                        f"{detected_currency} ({confidence:.3f})"
                    )
            except Exception as e:
                logger.warning(f"[Currency Detection] LLM service currency detection failed: {e}")

        # 2B) Try dedicated currency detector (preferred over intent detector)
        if hasattr(self, "currency_detector") and self.currency_detector and self.currency_detector.is_available():
            try:
                detected_currency, confidence, reasoning = self.currency_detector.detect_currency(question)
                if detected_currency and confidence >= confidence_threshold:
                    logger.info(
                        f"[Currency Detection] Currency detector detected: {detected_currency} "
                        f"(confidence: {confidence:.3f})"
                    )
                    return detected_currency, confidence
            except Exception as e:
                logger.warning(f"[Currency Detection] Currency detector failed: {e}")

        # 3) If LLM couldn't decide, check for a country mention and map to currency
        country_currency, country_conf = self._detect_country_from_text(question)
        if country_currency:
            logger.info(f"[Currency Detection] Country-based fallback: {country_currency} (confidence: {country_conf:.2f})")
            return country_currency, country_conf

        # 4) Nothing matched — default to KHR
        logger.debug("[Currency Detection] No currency detected, defaulting to KHR")
        return "KHR", 0.0
    
    def _pattern_based_currency_detection(self, question: str, confidence_threshold: float = 0.6) -> Tuple[Optional[str], float]:
        """
        Fallback pattern-based currency detection (using regex/keywords).
        
        Args:
            question: User question
            confidence_threshold: Minimum confidence score
            
        Returns:
            (currency_code, confidence) - defaults to 'KHR' if not found
        """
        import re
        
        q_lower = (question or "").replace("Â¥", "¥").replace("ï¿¥", "¥").lower()
        logger.debug(f"[Currency Detection] Pattern-based checking for question: '{q_lower}'") 
        
        # Define currency patterns with confidence scores
        # Vehicka-branch improved patterns use negative lookbehind/lookahead for better matching
        patterns = {
            "USD": [r'\$\s*\d', r'\d\s*\$', r'(?<![a-z])usd\b', r'(?<![a-z])dollar', r'(?<![a-z])greenback', r'(?<![a-z])bucks?\b'],
            "KHR": [r'៛', r'(?<![a-z])khr\b', r'(?<![a-z])khm\b', r'(?<![a-z])riel\b', r'(?<![a-z])khmerian\b'],
            "EUR": [r'€\s*\d', r'\d\s*€', r'(?<![a-z])eur\b', r'(?<![a-z])euro\b'],
            "THB": [r'(?<![a-z])thb\b', r'(?<![a-z])baht\b'],
            "CNY": [r'¥\s*\d', r'\d\s*¥', r'(?<![a-z])cny\b', r'(?<![a-z])yuan\b', r'(?<![a-z])rmb\b'],
            "VND": [r'(?<![a-z])vnd\b', r'(?<![a-z])dong\b'],
            "GBP": [r'£\s*\d', r'\d\s*£', r'(?<![a-z])gbp\b', r'(?<![a-z])pound\b'],
            "JPY": [r'¥\s*\d', r'\d\s*¥', r'(?<![a-z])jpy\b', r'(?<![a-z])yen\b'],
            "SGD": [r'(?<![a-z])sgd\b'],
            "MYR": [r'(?<![a-z])myr\b', r'(?<![a-z])ringgit\b'],
            "IDR": [r'(?<![a-z])idr\b', r'(?<![a-z])rupiah\b'],
            "AUD": [r'(?<![a-z])aud\b'],
            "CAD": [r'(?<![a-z])cad\b'],
            "KRW": [r'₩\s*\d', r'\d\s*₩', r'(?<![a-z])krw\b', r'(?<![a-z])won\b'],
            "HKD": [r'(?<![a-z])hkd\b'],
            "TWD": [r'(?<![a-z])twd\b'],
            "NZD": [r'(?<![a-z])nzd\b'],
            "CHF": [r'(?<![a-z])chf\b', r'(?<![a-z])franc\b'],
            "INR": [r'(?<![a-z])inr\b', r'(?<![a-z])rupee\b'],
            "RUB": [r'₽', r'(?<![a-z])rub\b', r'(?<![a-z])ruble\b'],
            "AED": [r'(?<![a-z])aed\b', r'(?<![a-z])dirham\b'],
            "BRL": [r'(?<![a-z])brl\b', r'(?<![a-z])real\b'],
        }
        
        # Check each currency pattern
        for currency, pattern_list in patterns.items():
            for pattern in pattern_list:
                logger.debug(f"[Currency Detection] Testing pattern '{pattern}' for currency '{currency}'")
                if re.search(pattern, q_lower, re.IGNORECASE):
                    confidence = 0.75 if pattern_list.index(pattern) == 0 else 0.65  # Higher confidence for more specific patterns
                    logger.debug(f"[Currency Detection] Pattern matched: {currency} (confidence: {confidence:.2f})")
                    return currency, confidence
        
        # If no pattern matched, return default KHR
        logger.debug(f"[Currency Detection] No currency pattern matched, defaulting to KHR")
        return "KHR", 0.0
    
    def _detect_country_from_text(self, question: str) -> Tuple[Optional[str], float]:
        """
        Simple country -> currency mapping by keyword match.
        Returns (currency_code, confidence) or (None, 0.0).
        """
        import re

        q_lower = question.lower()

        COUNTRY_TO_CURRENCY = {
            "cambodia": "KHR",
            "khmer": "KHR",
            "cambodian": "KHR",
            "laos": "LAK",
            "vietnam": "VND",
            "vietnamese": "VND",
            "thailand": "THB",
            "thai": "THB",
            "china": "CNY",
            "chinese": "CNY",
            "united states": "USD",
            "united states of america": "USD",
            "usa": "USD",
            "america": "USD",
            "united kingdom": "GBP",
            "uk": "GBP",
            "great britain": "GBP",
            "france": "EUR",
            "germany": "EUR",
            "europe": "EUR",
        }

        for country_keyword, curr in COUNTRY_TO_CURRENCY.items():
            if re.search(r"\b" + re.escape(country_keyword) + r"\b", q_lower):
                # Conservative confidence for country-derived inference
                return curr, 0.65

        return None, 0.0
    
    def cleanup_query(self, user_input: str) -> str:
        """Remove filler phrases from user query. Delegates to hs_classifier."""
        from .hs_classifier import cleanup_query as _cleanup_query
        return _cleanup_query(user_input)

    def _keyword_based_intent_detection(self, question: str) -> WorkflowIntent:
        """
        Fallback keyword-based intent detection with enhanced safety gates.

        Priority order:
        1. Combined product/HS/CIF + calculation signal → CALCULATION
        2. Explicit HS code numeric pattern → HS_CODE_LOOKUP
        3. Service/fee question safety gate → GENERAL
        4. Explicit HS classification markers → HS_CODE_LOOKUP
        5. Policy/compliance/procedural keywords → GENERAL
        6. Trade statistics keywords → TRADE_QUERY
        7. Definition/explanation keywords → GENERAL
        8. Calculation keywords → CALCULATION
        9. Product phrase heuristic → HS_CODE_LOOKUP
        10. Policy engine fallback
        """
        q_lower = question.lower()

        # PRIORITY 0: Combined signal — product + calculation/exemption/FTA/export
        # If user mentions a product AND any tax/cost/exemption/FTA/export keyword,
        # force calculation intent before the priority ladder kicks in.
        combined_calc_markers = [
            "calculate", "compute", "how much", "what.*cost", "what.*duty",
            "what.*tax", "tax for", "duty for", "dues", "taxes", "import tax",
            "how much.*import", "how much.*duty", "how much.*tax",
            "import.*cost", "import.*tax", "import.*duty", "tariff rate",
            "export tax",
            "qip", "qualified investment",
            "sez", "special economic zone",
            "diplomatic", "embassy", "consulate",
            "ngo", "unicef", "humanitarian", "relief", "donation",
            "university", "school", "educational", "education",
            "hospital", "medical", "health", "donated",
            "passenger", "luggage", "personal effects",
            "cif", "declared value", "dv ",
        ]
        product_markers = [
            "laptop", "phone", "computer", "electronics", "car", "vehicle",
            "truck", "motorcycle", "bus", "rubber", "rice", "grain", "sugar",
            "oil", "fish", "meat", "beef", "pork", "chicken", "poultry",
            "textile", "fabric", "cloth", "cotton", "silk", "wool", "plastic",
            "metal", "chemical", "machinery", "equipment", "pipe", "tube",
            "cable", "medicine", "pharmaceutical", "food", "fruit", "vegetable",
            "cigarette", "tobacco", "alcohol", "whisky", "spirits", "wine",
            "beer", "container", "bag", "footwear", "shoe", "garment",
            "clothing", "apparel", "fertilizer", "petroleum", "gasoline",
            "diesel", "fuel", "medical", "supplies", "material", "microscope",
            "machinery", "electronics", "device", "machine",
        ]
        has_calc_marker = any(
            (bool(re.search(kw, q_lower)) if ".*" in kw else kw in q_lower)
            for kw in combined_calc_markers
        )
        has_product = any(p in q_lower for p in product_markers)
        has_hs_code = bool(re.search(r"(?<!\d)\d{4}(?:[\.\-/\s]?\d{2}){0,2}(?!\d)", q_lower))
        has_cif_value = bool(re.search(r'\d{1,3}(?:,\d{3})*(?:\.\d+)?', q_lower)) and any(k in q_lower for k in ["cif", "value", "worth", "cost", "price"])
        if has_calc_marker and (has_product or has_hs_code or has_cif_value):
            is_just_rate_lookup = any(phrase in q_lower for phrase in ["duty rate", "tax rate", "tariff rate", "duty rates", "tax rates", "tariff rates"])
            is_explicit_calc = any(kw in q_lower for kw in ["calculate", "compute"]) or has_cif_value
            if not is_just_rate_lookup or is_explicit_calc:
                logger.debug(f"Intent detection: CALCULATION (combined product/HS/CIF + calc/exemption/FTA/export signal)")
                return WorkflowIntent.CALCULATION

        # PRIORITY 1: Explicit HS code pattern (e.g., "0102.29.11")
        if re.search(r"(?<!\d)\d{4}(?:[\.\-/\s]?\d{2}){0,2}(?!\d)", q_lower):
            logger.debug(f"Intent detection: HS_CODE_LOOKUP (numeric code pattern)")
            return WorkflowIntent.HS_CODE_LOOKUP

        # PRIORITY 2: Non-HS service/fee markers (SAFETY GATE)
        # These should never be routed to HS endpoint, but calculation intent overrides this.
        non_hs_service_markers = [
            "scanning fee", "scan fee", "service fee", "handling fee",
            "storage fee", "inspection fee", "port fee", "terminal fee",
            "fee", "charge", "charges", "cost", "price", "how much"
        ]
        if any(m in q_lower for m in non_hs_service_markers):
            if not has_calc_marker:
                logger.debug(f"Intent detection: GENERAL (service/fee question, safety gate)")
                return WorkflowIntent.GENERAL
            logger.debug(f"Intent detection: CALCULATION (fee marker overridden by calc signal)")
            return WorkflowIntent.CALCULATION

        # PRIORITY 3: Explicit HS classification markers
        # But first, check if they are asking to define "HS code" itself
        if any(pat in q_lower for pat in ["what is an hs code", "what is hs code", "what is hscode", "define hs code", "define hscode", "explain hs code", "explain hscode", "what are hs codes"]):
            logger.debug(f"Intent detection: GENERAL (defining HS code itself)")
            return WorkflowIntent.GENERAL

        hs_markers = [
            "hs code", "hs-code", "hscode",
            "ahtn", "ahtn code",
            "tariff code", "harmonized code", "harmonized system",
            "tariff number", "hs number",
            "classify", "classification", "code for",
        ]
        if any(m in q_lower for m in hs_markers):
            logger.debug(f"Intent detection: HS_CODE_LOOKUP (explicit HS marker)")
            return WorkflowIntent.HS_CODE_LOOKUP

        # PRIORITY 4: Policy/compliance keywords
        # PRIORITY 4B: Policy composite phrases — must be checked BEFORE bare "what is" keywords
        # so "what is the procedure" routes to POLICY_QUERY, not DEFINITION.
        policy_composite_phrases = [
            "what is the procedure", "what are the procedures",
            "what is the process", "what are the steps",
            "what is the requirement", "what are the requirements",
            "what do i need to", "how do i", "how to import",
            "how to export", "how to declare", "how to register",
            "how to apply", "how to obtain", "what documents",
            "what permits", "procedure for", "requirements for",
            "process for",
        ]
        if any(phrase in q_lower for phrase in policy_composite_phrases):
            logger.debug(f"Intent detection: GENERAL (policy composite phrase)")
            return WorkflowIntent.GENERAL

        policy_keywords = [
            "requirements", "requirement", "procedure", "regulation", "policy",
            "compliance", "permit", "rules of origin"
        ]
        if any(kw in q_lower for kw in policy_keywords):
            logger.debug(f"Intent detection: GENERAL (policy keyword)")
            return WorkflowIntent.GENERAL

        # PRIORITY 4.5: Trade query keywords (moved before Definition/Calculation to handle overlaps like "what is trade data")
        trade_keywords = [
            "trade data", "trade statistics", "trade statistic",
            "trade volume", "trade flow", "trade flows", "trade trend",
            "bilateral trade", "trade between",
            "export data", "export statistics", "export statistic",
            "export volume", "top export",
            "import data", "import statistics", "import statistic",
            "import volume", "import trend",
            "shipping data", "cargo data", "freight data",
        ]
        if any(kw in q_lower for kw in trade_keywords):
            logger.debug(f"Intent detection: TRADE_QUERY (trade keyword)")
            return WorkflowIntent.TRADE_QUERY

        # PRIORITY 5: Definition keywords — only reached when no policy/trade signal matched above
        definition_keywords = [
            "define", "definition of", "what is", "meaning of", "what does", "explain",
        ]
        if any(kw in q_lower for kw in definition_keywords):
            # Override definition if calc signal is present (e.g., "what is the duty for...")
            if has_calc_marker:
                logger.debug(f"Intent detection: CALCULATION (definition marker overridden by calc signal)")
                return WorkflowIntent.CALCULATION
            logger.debug(f"Intent detection: GENERAL (definition keyword)")
            return WorkflowIntent.GENERAL

        # PRIORITY 6: Calculation keywords (SECONDARY to HS)
        calculation_keywords = [
            # Core verbs
            "calculate", "compute",
            # Duty / tax phrases (specific to avoid false-positives)
            "how much duty", "how much tax", "how much vat",
            "import duty", "import tax", "export duty", "export tax",
            "customs duty", "customs tax", "tariff rate", "duty rate", "tax rate",
            "vat rate", "duty for", "tax for", "dues",
            # Value / shipment phrases
            "cif value", "fob value", "declared value", "consignment value",
            "shipment value", "cif:", "fob:",
            # Exemptions / preferential rates
            "duty exemption", "tax exemption", "duty-free", "tax-free",
            "preferential rate", "fta rate", "atiga rate", "acfta rate", "rcep rate",
            # Special entity exemptions
            "qip", "qualified investment",
            "sez", "special economic zone",
            "diplomatic", "embassy",
            "ngo", "unicef", "humanitarian", "relief",
            "university", "school", "educational",
            "hospital", "medical", "donated",
            "passenger", "luggage",
        ]
        if any(kw in q_lower for kw in calculation_keywords):
            logger.debug(f"Intent detection: CALCULATION (calculation keyword)")
            return WorkflowIntent.CALCULATION
        
        # PRIORITY 8: Product phrase heuristic (short noun phrase → HS lookup)
        from .hs_classifier import is_hs_lookup_eligible, cleanup_query
        if is_hs_lookup_eligible(question, cleanup_query(question)):
            logger.debug("Intent detection: HS_CODE_LOOKUP (product phrase heuristic via hs_lookup_eligible)")
            return WorkflowIntent.HS_CODE_LOOKUP
        
        # PRIORITY 9: Use policy engine if available
        if self.policy_engine:
            try:
                intent_str = self.policy_engine.detect_intent_policy_based(question)
                logger.debug(f"Intent detection: {intent_str} (policy engine)")
                return WorkflowIntent(intent_str)
            except Exception as e:
                logger.warning(f"Policy engine intent detection failed: {e}")
        
        logger.debug(f"Intent detection: UNCLASSIFIED (fallback)")
        return WorkflowIntent.UNCLASSIFIED
    
    def get_workflow_sequence(self, intent: WorkflowIntent) -> List[str]:
        """
        Get the service sequence for the detected intent.
        
        Args:
            intent: Detected workflow intent
            
        Returns:
            List of service calls to execute in order
        """
        intent_sequences = {
            WorkflowIntent.CALCULATION: ["calculator"],
            WorkflowIntent.TRADE_QUERY: ["trade_data"],
            WorkflowIntent.GENERAL: ["retrieval"],
            WorkflowIntent.UNCLASSIFIED: ["retrieval"],
        }
        
        return intent_sequences.get(intent, ["retrieval"])
    

class RetryPolicy:
    """
    Retry policy for service calls.
    Implements exponential backoff and circuit breaker patterns.
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff_ms: int = 100,
        max_backoff_ms: int = 5000
    ):
        """
        Initialize retry policy.
        
        Args:
            max_retries: Maximum number of retries
            initial_backoff_ms: Initial backoff in milliseconds
            max_backoff_ms: Maximum backoff in milliseconds
        """
        self.max_retries = max_retries
        self.initial_backoff_ms = initial_backoff_ms
        self.max_backoff_ms = max_backoff_ms
    
    def get_backoff_ms(self, attempt: int) -> int:
        """
        Calculate backoff duration for attempt number.
        Uses exponential backoff with jitter.
        
        Args:
            attempt: Attempt number (0-indexed)
            
        Returns:
            Backoff duration in milliseconds
        """
        import random
        
        backoff = min(
            self.initial_backoff_ms * (2 ** attempt),
            self.max_backoff_ms
        )
        # Add jitter to prevent thundering herd
        jitter = random.uniform(0, backoff * 0.1)
        return int(backoff + jitter)
    
    def should_retry(self, attempt: int, exception: Exception) -> bool:
        """
        Determine if request should be retried.
        
        Args:
            attempt: Current attempt number
            exception: Exception that occurred
            
        Returns:
            True if should retry
        """
        if attempt >= self.max_retries:
            return False
        
        # Retry on connection errors, timeouts
        retriable_errors = (
            ConnectionError,
            TimeoutError,
            OSError,
        )
        
        return isinstance(exception, retriable_errors)


class FallbackPolicy:
    """
    Fallback policy for service calls.
    Defines fallback behavior when primary service fails.
    """
    
    def __init__(self):
        """Initialize fallback policy."""
        self.fallback_map = {
            WorkflowIntent.CALCULATION: WorkflowIntent.GENERAL,
            WorkflowIntent.TRADE_QUERY: WorkflowIntent.GENERAL,
        }
    
    def get_fallback_intent(self, intent: WorkflowIntent) -> Optional[WorkflowIntent]:
        """
        Get fallback intent for the given intent.
        
        Args:
            intent: Original intent
            
        Returns:
            Fallback intent or None if no fallback available
        """
        return self.fallback_map.get(intent)
