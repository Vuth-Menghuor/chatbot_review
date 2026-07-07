"""
HS Classification Helper Module
Implements sophisticated HS code classification logic with safety gates.
Ported from gemini_orchestrator_e2e.py test harness.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Phase 1:  Query Normalization & Eligibility

# Filler patterns to remove from user queries
FILLER_PATTERNS = [
    r"^what is the hs code for\s*",
    r"^what hs code do i use for\s*",
    r"^what hs code\s+(?:is|applies to|should i use)\s+for\s*",
    r"^please tell me the hs code for\s*",
    r"^i need the hs code for\s*",
    r"^hs code for\s*",
    r"\s*hs code\s*$",
]


def cleanup_query(user_input: str) -> str:
    """
    Strips common filler phrases (like "what is the hs code for...") to 
    leave only the raw product description.
    """
    result = user_input.strip()
    for pattern in FILLER_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE).strip()
    return result

# Phase 2: (Ask-Back Verification)
def detect_simple_product_category(query: str) -> str:
    """
    Detect product category from query for discriminator validation.
    Includes common vehicle brands, models, and product types.
    
    Returns: "vehicle", "food", "textile", or "other"
    """
    q = query.lower()
    
    # Vehicle keywords: generic types, brands, and popular models
    vehicle_keywords = [
        # Generic types
        "car", "truck", "van", "bus", "train", "hearse", "vehicle", 
        "motorcycle", "boat", "ship", "aircraft", "airplane", "jeep",
        # Popular brands
        "ford", "toyota", "honda", "nissan", "bmw", "mercedes", "audi",
        "volkswagen", "hyundai", "kia", "mazda", "subaru", "suzuki",
        "tesla", "chevrolet", "gmc", "dodge", "jeep", "lexus", "infiniti",
        "acura", "cadillac", "ram", "chevrolet", "buick",
        # Popular models
        "raptor", "f-150", "f150", "silverado", "sierra", "tacoma",
        "ranger", "colorado", "altima", "civic", "accord", "camry",
        "corolla", "rav4", "cr-v", "crv", "pilot", "odyssey",
        "pathfinder", "rogue", "murano", "qashqai", "juke",
        "model s", "model 3", "model x", "model y", "cybertruck",
        "mustang", "bronco", "ranger", "focus", "fusion",
        "a4", "a6", "a8", "q5", "q7", "q8",
        "3-series", "5-series", "7-series", "x3", "x5", "x7",
        "c-class", "e-class", "s-class", "glc", "gle", "gls",
    ]
    if any(x in q for x in vehicle_keywords):
        return "vehicle"
    
    if any(x in q for x in ["prepared", "preserved", "frozen", "fresh", "salted", "fish", "tuna", "salmon", "chicken", "meat", "rice", "food", "agricultural", "livestock"]):
        return "food"
    
    if any(x in q for x in ["womens", "mens", "girls", "boys", "trousers", "dress", "textile", "fabric"]):
        return "textile"
    
    return "other"


def has_critical_discriminators(query: str, product_category: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if the query contains the attributes required for classification (e.g., verifying if a vehicle query mentions engine size in cc/kW, 
    or if textiles specify knitted/woven). If missing, it tells the orchestrator to trigger a clarification question.
    """
    q = query.lower()
    
    # Vehicles require engine type AND engine size
    if product_category == "vehicle":
        has_engine_type = any(x in q for x in ["petrol", "diesel", "electric", "hybrid", "ev", "battery"])
        has_engine_size = any(x in q for x in ["engine", "cc", "kw", "power", "gvwr", "gvw", "ton"])
        
        if not has_engine_type:
            return False, "vehicle_engine"
        if not has_engine_size:
            return False, "vehicle_size"
    
    # Prepared/preserved food requires preservation method
    if product_category == "food" and ("prepared" in q or "preserved" in q):
        has_preservation = any(x in q for x in ["fresh", "frozen", "airtight", "salted", "dried", "smoked"])
        if not has_preservation:
            return False, "food_preservation"
    
    # Textiles require construction type AND fiber
    if product_category == "textile":
        has_construction = any(x in q for x in ["knitted", "woven", "crocheted"])
        has_fiber = any(x in q for x in ["wool", "synthetic", "cotton", "artificial", "animal hair"])
        
        if not has_construction:
            return False, "textile_construction"
        if not has_fiber:
            return False, "textile_fiber"
    
    return True, None

# Phase 3: Parsing Helpers
def extract_hs_code(doc: Dict[str, Any]) -> Optional[str]:
    """ Parses potential HS code matches out of unstructured document metadata fields."""
    if not isinstance(doc, dict):
        return None
    
    metadata = doc.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    
    return (
        doc.get("hs_code") 
        or metadata.get("hs_code") 
        or metadata.get("hscode") 
        or metadata.get("tariff_code")
    )

# Phase 4: Downstream Validation & Conflict Detection
def validate_hs_response(query: str, retrieval_payload: Dict[str, Any]) -> Tuple[str, Optional[str], List[str], str]:
    """
    Validates that the HS code retrieval result makes semantic sense.
    Detects not-found, ambiguous (multi-chapter), and inconsistent (query-mismatch) cases.
    
    Returns:
        Tuple of (status, primary_code, candidates, message)
        - status: One of ["success", "ambiguous", "inconsistent", "not_found"]
        - primary_code: The top-ranked HS code (or None if not found)
        - candidates: List of alternative HS codes from top 5 documents
        - message: Human-readable explanation of the result
    """
    # EXTRACT documents from retrieval response
    docs = retrieval_payload.get("documents", []) if isinstance(retrieval_payload, dict) else []
    
    if not docs:
        return "not_found", None, [], "No HS candidates returned from retrieval service."
    
    # EXTRACT codes from documents
    # primary = top-ranked document's HS code (most confident match)
    primary = extract_hs_code(docs[0])
    
    # candidates = HS codes from top 5 documents (ranked by relevance)
    # Filter out None/empty values (docs without parsable codes)
    candidates = [extract_hs_code(d) for d in docs[:5]]
    candidates = [c for c in candidates if c]
    
    # VALIDATE primary code exists: If top result has no parsable code, retrieval failed despite returning documents
    if not primary:
        return "not_found", None, candidates, "Top document does not include a parsable HS code."
    
    # CHECK for ambiguity (multiple HS chapters)
    # HS code structure: 6 digits, grouped by 2-digit chapters (01-99)
    # If candidates span 3+ chapters, the query is ambiguous (could match multiple product categories)
    chapter_set = {
        c[:2] 
        for c in candidates 
        if len(c) >= 2 
    }
    
    if len(chapter_set) > 2:
        # Too many chapters = ambiguous result.e.g. Query "motorcycle part" matched chapters: {'12', '84', '87'} (textiles, machinery, vehicles)
        return "ambiguous", primary, candidates, f"Top candidates span multiple chapters: {sorted(chapter_set)}"
    
    q = query.lower()
    
    # If query mentions vehicle types...
    if any(x in q for x in ["car", "truck", "bus", "van", "vehicle", "motorcycle"]):
        # ...the result MUST be chapter 87 (vehicles)
        # If not, there's a semantic mismatch (retrieval found wrong thing)
        if not primary.startswith("87"):
            # Example: Query = "motorcycle" but primary = "5904" (textile articles)
            return "inconsistent", primary, candidates, f"Expected vehicle chapter 87xx, but got {primary}."
    
    return "success", primary, candidates, "Validated retrieval result."


def detect_hs_semantic_conflict(query: str, retrieval_payload: Dict[str, Any], hs_code: Optional[str]) -> Optional[str]:
    """
    Detects semantic mismatches between user's query and the selected HS code.
    Prevents false positives (e.g., classifying "women's shoes" as "men's shoes").
    """
    if not hs_code:
        return None
    
    # Find the document matching the selected HS code
    docs = retrieval_payload.get("documents", []) if isinstance(retrieval_payload, dict) else []
    description = ""
    
    for doc in docs:
        if extract_hs_code(doc) == hs_code:
            # Extract description from metadata or fallback to document content
            metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
            description = str(metadata.get("description") or doc.get("content") or "").lower()
            break
    
    # If code not found in docs or no description, can't validate
    if not description:
        return None
    
    q = (query or "").lower()
    
    # Guardrail 1: GENDER MISMATCH
    # Query mentions women/girls but code describes men/boys (or vice versa)
    # Example: Query="women's clothing" but HS code=620320 (men's trousers)
    if any(t in q for t in ["women", "girls"]) and any(t in description for t in ["men", "boys"]):
        return "Selected candidate conflicts with gender qualifier in query."
    
    # Guardrail 2: CHEMICAL NAME MISMATCH
    # User specified a chemical but code is for a different chemical
    # Example: Query="acetic acid" but code=280720 (nitric acid)
    chemical_tokens = ["acetic", "nitric", "sulphuric", "sulfuric", "hydrochloric", "phosphoric"]
    q_chems = [t for t in chemical_tokens if t in q]  
    d_chems = [t for t in chemical_tokens if t in description]   
    
    if q_chems and d_chems and not any(t in description for t in q_chems):
        return "Selected candidate conflicts with requested chemical name in query."

    return None


def validate_selected_code(query: str, selected_code: Optional[str], candidates: List[str]) -> Tuple[str, str]:
    """
    Validates that the selected HS code is valid and consistent.
    Checks: code exists, is in candidates, candidates aren't ambiguous, semantic match.
    
    Returns:
        (status, message) where status in ["not_found", "inconsistent", "ambiguous", "success"]
    """
    
    if not selected_code:
        return "not_found", "No selected HS code to validate."
    
    # Selected code must come from retrieval results (sanity check against arbitrary input)
    if selected_code not in candidates:
        return "inconsistent", "Selected code is not in retrieval candidate list."
    
    # CANDIDATE AMBIGUITY
    # If top 5 candidates span 3+ HS chapters, the whole result set is ambiguous
    # Example: candidates = ["1201", "8432", "8704"] (3 different chapters)
    # This means retrieval couldn't narrow down to one product category
    chapter_set = {c[:2] for c in candidates if len(c) >= 2}  # Extract 2-digit chapters
    if len(chapter_set) > 2:
        return "ambiguous", f"Top candidates span multiple chapters: {sorted(chapter_set)}"
    
    # SEMANTIC CONSISTENCY (vehicle query check)
    # If query mentions vehicles, the selected code MUST be chapter 87xx
    # Example: Query="motorcycle" but selected_code="5904" (textiles) = inconsistent
    q = query.lower()
    if any(x in q for x in ["car", "truck", "bus", "van", "vehicle", "motorcycle"]):
        if not selected_code.startswith("87"):
            return "inconsistent", f"Expected vehicle chapter 87xx, but got {selected_code}."
    
    return "success", "Validated selected HS code."


def is_hs_lookup_eligible(user_query: str, cleaned_query: str) -> bool:
    """
    Safety gate that determines if a query should be routed to HS code lookup.
    Prevents non-product queries from reaching the HS endpoint (e.g., fees, definitions, policies).
    """
    q = (user_query or "").lower()
    c = (cleaned_query or "").lower()
    
    
    # CHECK 1: EXPLICIT HS CODE in query
    # Matches 6+ digit codes OR 4-digit.2-digit.2-digit patterns
    # Example: 840110, 8401.10, 8401-10-00
    # Guard: avoid matching 4-digit years (2024) by requiring 6+ digits OR dot/dash separators
    if re.search(r"(?<!\d)(?:\d{6,}|\d{4}(?:[\.\-/]\d{2,}){1,2})(?!\d)", q):
        return True
    
    # CHECK 2: EXPLICIT HS KEYWORDS
    explicit_hs_markers = ["hs code", "tariff code", "hscode", "ahtn", "classification", "classify"]
    if any(m in q for m in explicit_hs_markers):
        return True

    # CHECK 3: "HS" + preposition phrase: "HS for shoes", "HS of motorcycle", "HS about tea"
    if re.search(r"\bhs\b", q) and re.search(r"\b(for|of|about|on)\b", q):
        return True
    
    # CHECK 4: SERVICE/FEE QUESTIONS: "scanning fee", "how much is the storage charge"
    service_or_fee_markers = [
        "scanning fee", "scan fee", "service fee", "handling fee",
        "storage fee", "inspection fee", "port fee", "terminal fee",
        "fee", "charge", "cost", "price", "how much"
    ]
    if any(m in q for m in service_or_fee_markers):
        return False
    
    # CHECK 5a: FOLLOWUP PRODUCT PHRASES: "What about X?" or "How about X?" 
    # Example: "what about leather shoes" → eligible (product inquiry, not definition)
    followup_product_phrase = bool(
        re.match(r"^(what|how)\s+about\s+\w", q)
    )

    # CHECK 5b: OPEN QUESTION DETECTION: "What is HS code?" (definition) vs "What about HS code for motorcycles?" (product)
    # Blocks: "why", "when", "where", "explain"
    question_starters = ["why", "when", "where", "explain"]
    
    # Also blocks open "what is/are/does" but NOT "what about"/"how about"
    open_question = bool(
        re.match(r"^(what\s+(is|are|does|do|did|was|were)|how\s+(is|are|does|do|did|was|can|could|much|many))\b", q)
    )
    
    # Determine if query looks like a product phrase (not a definition/explanation)
    looks_like_phrase = (
        bool(c)
        and len(c.split()) <= 12 
        and (
            followup_product_phrase  # "what about X" is always valid
            or (
                not any(q.startswith(s) for s in question_starters)  # Not "why/when/where/who"
                and not open_question 
            )
        )
    )

    # CHECK 6: SIMPLE PRODUCT CATEGORY DETECTION: e.g., "vehicle/food/textile"
    if looks_like_phrase and detect_simple_product_category(c) != "other":
        return True

    # CHECK 7: LIVESTOCK/AGRICULTURAL/PRODUCT TOKENS: e.g., "live horse", "timber", "rubber", "grain"
    livestock_or_product_tokens = [
        "live", "horse", "horses", "ass", "asses", "mule", "mules", "hinny", "hinnies",
        "animal", "animals", "cattle", "bovine", "cow", "beef", "swine", "pig", "goat", "sheep",
        "poultry", "chicken", "duck", "turkey", "fish", "shrimp", "crab", "lobster",
        "grain", "wheat", "corn", "rice", "barley", "soy", "cotton", "rubber", "timber",
    ]
    if looks_like_phrase and any(token in c for token in livestock_or_product_tokens):
        return True

    # Prevents simple product names from being misrouted just because they don't match buckets above
    tokens = re.findall(r"[a-z0-9]+", c)
    
    # Blocked tokens: greetings, off-topic words, question words
    blocked_tokens = {
        "hello", "hi", "hey", "thanks", "please",  # Greetings
        "weather", "time", "date",                  # Off-topic
        "football", "soccer", "movie", "music",     # Entertainment
        "recipe", "cook", "joke",                   # Non-product
        "politics", "war", "crime",                 # Off-topic
        "hack", "hacking", "investment", "stock",   # Off-topic
        "what", "how", "why", "when", "where", "who", "which",  # Question words
        "can", "could", "should", "is", "are", "do", "does",    # Verbs/auxiliaries
    }
    
    if (looks_like_phrase 
        and 1 <= len(tokens) <= 4  
        and not any(token in blocked_tokens for token in tokens) 
        and all(len(token) >= 2 for token in tokens)):
        return True

    return False