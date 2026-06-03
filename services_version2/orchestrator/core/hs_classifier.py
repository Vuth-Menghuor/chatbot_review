"""
HS Classification Helper Module
Implements sophisticated HS code classification logic with safety gates.
Ported from gemini_orchestrator_e2e.py test harness.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)


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
    Remove common filler phrases from query to focus on product description.
    
    Args:
        user_input: Raw user query
        
    Returns:
        Cleaned query focused on product details
    """
    result = user_input.strip()
    for pattern in FILLER_PATTERNS:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE).strip()
    return result


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
    
    if any(x in q for x in ["prepared", "preserved", "frozen", "fresh", "salted", "fish", "tuna", "salmon"]):
        return "food"
    
    if any(x in q for x in ["womens", "mens", "girls", "boys", "trousers", "dress", "textile", "fabric"]):
        return "textile"
    
    return "other"


def has_critical_discriminators(query: str, product_category: str) -> Tuple[bool, Optional[str]]:
    """
    Validate if query has sufficient discriminators for HS classification.
    
    Returns:
        (is_valid, missing_field_name)
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


def extract_hs_code(doc: Dict[str, Any]) -> Optional[str]:
    """Extract HS code from retrieval document."""
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


def validate_hs_response(query: str, retrieval_payload: Dict[str, Any]) -> Tuple[str, Optional[str], List[str], str]:
    """
    Validate retrieval response for HS classification.
    
    Returns:
        (status, primary_code, candidates, message)
        where status in ["success", "ambiguous", "inconsistent", "not_found"]
    """
    docs = retrieval_payload.get("documents", []) if isinstance(retrieval_payload, dict) else []
    
    if not docs:
        return "not_found", None, [], "No HS candidates returned from retrieval service."
    
    # Extract primary code
    primary = extract_hs_code(docs[0])
    candidates = [extract_hs_code(d) for d in docs[:5]]
    candidates = [c for c in candidates if c]
    
    if not primary:
        return "not_found", None, candidates, "Top document does not include a parsable HS code."
    
    # Check for ambiguity: too many chapters in top candidates
    chapter_set = {c[:2] for c in candidates if len(c) >= 2}
    if len(chapter_set) > 2:
        return "ambiguous", primary, candidates, f"Top candidates span multiple chapters: {sorted(chapter_set)}"
    
    # Check for semantic inconsistency: vehicle query but non-87xx code
    q = query.lower()
    if any(x in q for x in ["car", "truck", "bus", "van", "vehicle", "motorcycle"]) and not primary.startswith("87"):
        return "inconsistent", primary, candidates, f"Expected vehicle chapter 87xx, but got {primary}."
    
    return "success", primary, candidates, "Validated retrieval result."


def detect_hs_semantic_conflict(query: str, retrieval_payload: Dict[str, Any], hs_code: Optional[str]) -> Optional[str]:
    """
    Detect semantic conflicts between query and selected HS code.
    
    Returns: Conflict message or None if no conflict
    """
    if not hs_code:
        return None
    
    # Extract description for selected code
    docs = retrieval_payload.get("documents", []) if isinstance(retrieval_payload, dict) else []
    description = ""
    
    for doc in docs:
        if extract_hs_code(doc) == hs_code:
            metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
            description = str(metadata.get("description") or doc.get("content") or "").lower()
            break
    
    if not description:
        return None
    
    q = (query or "").lower()
    
    # Guardrail 1: Gendered textile mismatch
    if any(t in q for t in ["women", "girls"]) and any(t in description for t in ["men", "boys"]):
        return "Selected candidate conflicts with gender qualifier in query."
    
    # Guardrail 2: Chemical name mismatch
    chemical_tokens = ["acetic", "nitric", "sulphuric", "sulfuric", "hydrochloric", "phosphoric"]
    q_chems = [t for t in chemical_tokens if t in q]
    d_chems = [t for t in chemical_tokens if t in description]
    
    if q_chems and d_chems and not any(t in description for t in q_chems):
        return "Selected candidate conflicts with requested chemical name in query."
    
    return None


def validate_selected_code(query: str, selected_code: Optional[str], candidates: List[str]) -> Tuple[str, str]:
    """
    Validate a selected HS code against candidates.
    
    Returns:
        (status, message)
    """
    if not selected_code:
        return "not_found", "No selected HS code to validate."
    
    if selected_code not in candidates:
        return "inconsistent", "Selected code is not in retrieval candidate list."
    
    # Check for chapter ambiguity
    chapter_set = {c[:2] for c in candidates if len(c) >= 2}
    if len(chapter_set) > 2:
        return "ambiguous", f"Top candidates span multiple chapters: {sorted(chapter_set)}"
    
    # Check for vehicle semantic consistency
    q = query.lower()
    if any(x in q for x in ["car", "truck", "bus", "van", "vehicle", "motorcycle"]) and not selected_code.startswith("87"):
        return "inconsistent", f"Expected vehicle chapter 87xx, but got {selected_code}."
    
    return "success", "Validated selected HS code."


def build_hs_candidates(retrieval_payload: Dict[str, Any], top_n: int = 10) -> List[Dict[str, Any]]:
    """
    Build structured candidate list from retrieval documents.
    
    Returns:
        List of candidates with rank, hs_code, description, score
    """
    docs = retrieval_payload.get("documents", []) if isinstance(retrieval_payload, dict) else []
    candidates: List[Dict[str, Any]] = []
    seen = set()
    
    for idx, doc in enumerate(docs[:top_n], start=1):
        code = extract_hs_code(doc)
        if not code or code in seen:
            continue
        
        seen.add(code)
        metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
        description = (
            metadata.get("description")
            or doc.get("content")
            or metadata.get("title")
            or ""
        )
        
        candidates.append({
            "rank": idx,
            "hs_code": code,
            "description": str(description).strip(),
            "score": float(doc.get("score", 0.0) or 0.0),
        })
    
    return candidates


def format_possible_answers_section(possible_answers: List[Dict[str, Any]]) -> str:
    """
    Format possible HS code matches as human-readable section.
    """
    if not possible_answers:
        return ""
    
    lines = ["Possible HS code matches:"]
    for idx, candidate in enumerate(possible_answers, start=1):
        code = str(candidate.get("hs_code") or "").strip()
        description = str(candidate.get("description") or "").strip()
        score = candidate.get("score", 0.0)
        score_str = f" (score={score:.2f})" if score else ""
        
        if description:
            lines.append(f"  {idx}. {code} - {description}{score_str}")
        else:
            lines.append(f"  {idx}. {code}{score_str}")
    
    return "\n".join(lines)


def is_hs_lookup_eligible(user_query: str, cleaned_query: str) -> bool:
    """
    Determine if query is eligible for HS code lookup.
    Safety gate to prevent non-HS queries from being routed to HS endpoint.
    """
    q = (user_query or "").lower()
    c = (cleaned_query or "").lower()
    
    # Explicit HS code in query
    # Note: avoid matching 4-digit years (e.g., 2024). Require either
    # - at least 6 contiguous digits (common in full HS codes), or
    # - a 4-digit segment followed by separators and at least one 2+ digit segment
    # Examples matched: 840110, 8401.10, 8401-10-00
    if re.search(r"(?<!\d)(?:\d{6,}|\d{4}(?:[\.\-/]\d{2,}){1,2})(?!\d)", q):
        return True
    
    # Explicit HS markers
    explicit_hs_markers = ["hs code", "tariff code", "hscode", "ahtn", "classification", "classify"]
    if any(m in q for m in explicit_hs_markers):
        return True

    # Also accept common phrasing that omits the word "code".
    if re.search(r"\bhs\b", q) and re.search(r"\b(for|of|about|on)\b", q):
        return True
    
    # Service/fee questions should NOT be HS lookups
    service_or_fee_markers = [
        "scanning fee", "scan fee", "service fee", "handling fee",
        "storage fee", "inspection fee", "port fee", "terminal fee",
        "fee", "charge", "cost", "price", "how much"
    ]
    if any(m in q for m in service_or_fee_markers):
        return False
    
    # Product phrase heuristic
    # "what about X" / "how about X" are valid product follow-ups and must NOT be blocked
    # even though they start with "what" / "how".
    followup_product_phrase = bool(
        re.match(r"^(what|how)\s+about\s+\w", q)
    )

    question_starters = ["why", "when", "where", "who", "tell me", "explain"]
    # Also exclude open "what is", "what are", "how does", "how is" — but NOT "what about"/"how about"
    open_question = bool(
        re.match(r"^(what\s+(is|are|does|do|did|was|were)|how\s+(is|are|does|do|did|was|can|could|much|many))\b", q)
    )
    looks_like_phrase = (
        bool(c)
        and len(c.split()) <= 12
        and (
            followup_product_phrase
            or (
                not any(q.startswith(s) for s in question_starters)
                and not open_question
            )
        )
    )

    # Keep the original strict categories first.
    if looks_like_phrase and detect_simple_product_category(c) != "other":
        return True

    # Broaden eligibility for common product nouns that are outside vehicle/food/textile buckets.
    # This prevents false downgrades like "live horse" -> policy_query.
    livestock_or_product_tokens = [
        "live", "horse", "horses", "ass", "asses", "mule", "mules", "hinny", "hinnies",
        "animal", "animals", "cattle", "bovine", "cow", "beef", "swine", "pig", "goat", "sheep",
        "poultry", "chicken", "duck", "turkey", "fish", "shrimp", "crab", "lobster",
        "grain", "wheat", "corn", "rice", "barley", "soy", "cotton", "rubber", "timber",
    ]
    if looks_like_phrase and any(token in c for token in livestock_or_product_tokens):
        return True

    # Generic short-product fallback: allow concise noun phrases to reach HS lookup.
    # This keeps simple queries like "train", "motor", or "boat" from being
    # misrouted to policy/definition paths just because they do not match a bucket above.
    tokens = re.findall(r"[a-z0-9]+", c)
    blocked_tokens = {
        "hello", "hi", "hey", "thanks", "please", "weather", "time", "date",
        "football", "soccer", "movie", "music", "recipe", "cook", "joke",
        "politics", "war", "crime", "hack", "hacking", "investment", "stock",
        "what", "how", "why", "when", "where", "who", "which", "can", "could",
        "should", "is", "are", "do", "does",
    }
    if looks_like_phrase and 1 <= len(tokens) <= 4 and not any(token in blocked_tokens for token in tokens):
        if all(len(token) >= 2 for token in tokens):
            return True

    return False
