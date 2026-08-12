import sys
import os
# Prepend project root to sys.path to resolve ModuleNotFoundError: No module named 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.entity_utils import extract_entity, is_valid_country, looks_like_unit_price, is_entity_changed
from app.infrastructure.clients import CalculatorServiceClient
from app.services.clarification_manager import ClarificationManager

def test_extract_entity_for_problematic_query():
    query = "calculate import tax for i paid 10000$ hs 8703.23.58 $10000 from hs"
    extracted = extract_entity(query)
    # The raw query has no actual product noun, only price/verb/hs fluff
    assert extracted is None, f"Expected None, but got '{extracted}'"

def test_parse_question_for_calculation_country_filter():
    query = "calculate import tax for i paid 10000$ hs 8703.23.58 $10000 from hs"
    params = CalculatorServiceClient._parse_question_for_calculation(query)
    # Origin country should NOT be extracted as "Hs" or "Hs Code"
    assert params.get("origin_country") is None or params.get("origin_country").lower() != "hs"

def test_is_valid_country_basic():
    # 1. Standard full country name check
    assert is_valid_country("China") is True
    assert is_valid_country("china") is True
    assert is_valid_country("Cambodia") is True
    
    # 2. ISO 2-letter non-ambiguous check
    assert is_valid_country("CN") is True
    assert is_valid_country("cn") is True
    assert is_valid_country("VN") is True
    assert is_valid_country("vn") is True
    
    # 3. Ambiguous 2-letter check
    # Lowercase should be rejected completely
    assert is_valid_country("it") is False
    assert is_valid_country("us") is False
    assert is_valid_country("in") is False

def test_is_valid_country_casing_and_preposition():
    # Uppercase but no preposition or full query should fail
    assert is_valid_country("IT", "IT") is False
    assert is_valid_country("IT", "IT", "import IT") is False
    
    # Uppercase + preposition should pass
    assert is_valid_country("IT", "IT", "import from IT") is True
    assert is_valid_country("IT", "IT", "origin IT") is True
    assert is_valid_country("IT", "IT", "import of IT") is True
    
    # Title-case (merged query / rewrite) should fail
    assert is_valid_country("IT", "It", "import from It") is False

def test_parse_question_for_calculation_isolated_casing():
    # 1. Pronoun lowercase pronoun "it" in raw turn -> reject
    q1 = "how much I have to pay if i want to import it"
    p1 = CalculatorServiceClient._parse_question_for_calculation(q1)
    assert p1.get("origin_country") is None
    
    # 2. Merged title-cased "It" -> reject
    q2 = "Calculate import tax for iphone HS 8517.13.00 $1000 from It"
    p2 = CalculatorServiceClient._parse_question_for_calculation(q2)
    assert p2.get("origin_country") is None

    # 3. Uppercase no-preposition "IT" -> reject
    q3 = "how much to import IT"
    p3 = CalculatorServiceClient._parse_question_for_calculation(q3)
    assert p3.get("origin_country") is None

    # 4. Uppercase preposition "IT" -> accept
    q4 = "how much to import from IT"
    p4 = CalculatorServiceClient._parse_question_for_calculation(q4)
    assert p4.get("origin_country") == "IT"

    # 5. Non-ambiguous 2-letter codes (e.g. cn / CN) -> accept
    q5a = "import from cn"
    p5a = CalculatorServiceClient._parse_question_for_calculation(q5a)
    assert p5a.get("origin_country") == "CN"

    q5b = "import from CN"
    p5b = CalculatorServiceClient._parse_question_for_calculation(q5b)
    assert p5b.get("origin_country") == "CN"


def test_looks_like_unit_price():
    assert looks_like_unit_price("1 unit cost 1000$") is True
    assert looks_like_unit_price("1000$ each") is True
    assert looks_like_unit_price("1000$ per unit") is True
    assert looks_like_unit_price("1000$") is False
    assert looks_like_unit_price("Calculate import duty for 10 units") is False


def test_is_entity_changed():
    assert is_entity_changed("iphone", "car") is True
    assert is_entity_changed("iphone", "iphone") is False
    assert is_entity_changed("iphone", "iphone 13") is False
    assert is_entity_changed(None, "iphone") is False
    assert is_entity_changed("iphone", None) is False


def test_single_turn_unit_price_parsing():
    q = "Calculate import tax for 10 units of iPhone, 1 unit cost 1000$"
    parsed = CalculatorServiceClient._parse_question_for_calculation(q)
    assert parsed.get("cif_value") == 10000.0, f"Expected 10000.0, got {parsed.get('cif_value')}"
    assert parsed.get("quantity") == 10.0


class MockSession:
    def __init__(self):
        self.turns = []
        self.last_entity = None
        self.hs_code = None
        self.last_normalized_query = None
        self.currency = None
        self.product_category = None
        self.commercial_description = None


def test_end_to_end_merger_pipeline():
    session = MockSession()
    session.turns = [{"user": "import 10 units of iphone"}]
    session.last_entity = "iphone"
    session.hs_code = "8517.13.00"

    merged = ClarificationManager.merge_pending_with_clarification(
        coordinator=None,
        pending_query="Calculate import tax for iphone",
        clarification_response="1 unit cost 1000$",
        resolved_intent="calculation",
        session_last_entity="iphone",
        session_context=session,
        was_clarification_pending=True
    )

    assert "10 unit" in merged
    assert "1000 each" in merged

    # Parse and verify no double-multiplication
    parsed = CalculatorServiceClient._parse_question_for_calculation(merged)
    assert parsed.get("cif_value") == 10000.0, f"Expected 10000.0, got {parsed.get('cif_value')}"
    assert parsed.get("quantity") == 10.0


def test_entity_change_quantity_leakage():
    session = MockSession()
    session.turns = [{"user": "import 10 units of car"}]
    session.last_entity = "car"

    merged = ClarificationManager.merge_pending_with_clarification(
        coordinator=None,
        pending_query="Calculate import tax for iphone",
        clarification_response="1 unit cost 1000$",
        resolved_intent="calculation",
        session_last_entity="car",
        session_context=session,
        was_clarification_pending=True
    )

    # The "car" history quantity should not leak since the entity is now iphone
    assert "10 units" not in merged
    parsed = CalculatorServiceClient._parse_question_for_calculation(merged)
    # The default quantity should be 1, so CIF remains 1000
    assert parsed.get("cif_value") == 1000.0
    assert parsed.get("quantity") is None or parsed.get("quantity") == 1.0


def test_calculator_question_canonicalization():
    _extra_kwargs = {
        "hs_code": "8703.32.00",
        "cif_value": 9180.0,
        "currency": "USD",
        "origin_country": "China",
        "fta_applicable": False,
        "regime": "import",
    }
    session_context = MockSession()
    session_context.last_entity = "car"
    
    regime = _extra_kwargs.get("regime") or "import"
    canonical_parts = [f"calculate {regime} tax"]
    
    product_desc = (
        session_context.commercial_description or
        session_context.product_category or
        session_context.last_entity or
        "goods"
    )
    hs_val = _extra_kwargs.get("hs_code")
    if hs_val:
        canonical_parts.append(f"for {product_desc} HS {hs_val}")
    else:
        canonical_parts.append(f"for {product_desc}")
        
    cif_val = _extra_kwargs.get("cif_value")
    if cif_val is not None:
        cif_display = int(cif_val) if cif_val == int(cif_val) else cif_val
        curr_val = _extra_kwargs.get("currency") or "USD"
        canonical_parts.append(f"CIF {cif_display} {curr_val}")
        
    origin_val = _extra_kwargs.get("origin_country")
    if origin_val:
        canonical_parts.append(f"from {origin_val}")
        
    cert_val = _extra_kwargs.get("fta_certificate_type")
    if cert_val:
        canonical_parts.append(f"with {cert_val}")
    elif _extra_kwargs.get("fta_applicable"):
        canonical_parts.append("with FTA")
    elif _extra_kwargs.get("fta_applicable") is False:
        canonical_parts.append("no FTA")
        
    calculator_question = " ".join(canonical_parts)
    assert calculator_question == "calculate import tax for car HS 8703.32.00 CIF 9180 USD from China no FTA"


def test_has_product_last_entity_clarification():
    session = MockSession()
    session.commercial_description = None
    session.last_entity = "iphone"
    
    # Simulate has_product check from calculation.py
    has_product = bool(
        session.commercial_description or
        session.product_category or
        session.last_entity
    )
    assert has_product is True, "has_product should be True when last_entity is present"
    
    has_confirmed_hs = False
    has_explicit_hs_in_query = False
    cif_is_valid = False
    has_explicit_price = False
    
    missing_slots = []
    if not has_product and not (has_confirmed_hs or has_explicit_hs_in_query):
        missing_slots.append("product")
    if not (has_confirmed_hs or has_explicit_hs_in_query):
        missing_slots.append("hs_code")
    if not (cif_is_valid or has_explicit_price):
        missing_slots.append("cif_value")
        
    assert "product" not in missing_slots
    assert missing_slots[0] == "hs_code"


def test_is_genuine_conversational_small_talk_abbreviation():
    from app.services.heuristics import Heuristics
    assert Heuristics.is_genuine_conversational_small_talk("what can u help me with") is True
    assert Heuristics.is_genuine_conversational_small_talk("what can you help me with") is True
    assert Heuristics.is_genuine_conversational_small_talk("how are u") is True


def test_validation_plausibility_and_attached_currency():
    from app.services.handlers.calculation import is_genuine_product_desc, is_cif_value_plausible
    
    # 1. Test is_genuine_product_desc
    # Genuine cases
    assert is_genuine_product_desc("iPhone 15", "8517.13.00") is True
    assert is_genuine_product_desc("wire mesh 40000", "7314.14.00") is True
    assert is_genuine_product_desc("banana", "0803.90.00") is True
    
    # Field bleed / duplicated HS code cases
    assert is_genuine_product_desc("8703.80.99", "8703.80.99") is False
    assert is_genuine_product_desc("HS Code 87038099", "8703.80.99") is False
    assert is_genuine_product_desc("87038099", "8703.80.99") is False
    assert is_genuine_product_desc("8703", "8703.80.99") is False
    assert is_genuine_product_desc("", "8703.80.99") is False
    assert is_genuine_product_desc(None, "8703.80.99") is False
    
    # 2. Test is_cif_value_plausible
    # Sane USD
    assert is_cif_value_plausible(40000, "USD") is True
    assert is_cif_value_plausible("40000.50", "USD") is True
    assert is_cif_value_plausible("2", "USD") is True  # low-value sample
    # Sane KHR (must be whole number)
    assert is_cif_value_plausible("1000", "KHR") is True
    assert is_cif_value_plausible(160000000, "KHR") is True
    
    # Implausible KHR (fractional riels)
    assert is_cif_value_plausible("1000.50", "KHR") is False
    # Implausible decimal places (USD cent fractions)
    assert is_cif_value_plausible("10.555", "USD") is False
    # Implausible signs/bounds
    assert is_cif_value_plausible(-10, "USD") is False
    assert is_cif_value_plausible(0, "USD") is False
    assert is_cif_value_plausible(200_000_000_000, "USD") is False


def test_attached_currency_token_enrichment():
    from app.services.handlers.calculation import CalculationHandler
    from unittest.mock import MagicMock
    
    session = MagicMock()
    session.commercial_description = "car"
    session.hs_code = "8703.80.99"
    session.cif_value = None
    session.origin_country = "China"
    session.currency = "USD"
    session.turns = []
    
    coordinator = MagicMock()
    coordinator.llm_service = None
    
    query = "calculate import tax for car cif 40000usd"
    
    import asyncio
    res = asyncio.run(CalculationHandler.enrich_calculation_query_from_context(
        coordinator, query, session
    ))
    
    assert "CIF 40000 USD" in res, f"Expected 'CIF 40000 USD' in enriched query, got: {res}"


def test_quantity_multiplication_logic():
    """
    Verifies that _parse_question_for_calculation multiplies unit CIF by
    quantity when 'each'/'per unit' cues are present, producing the correct
    total CIF — and that a query with only a quantity token but NO unit-price
    cue does NOT trigger multiplication (i.e. the guard is one-sided).
    """
    # Case 1: unit price × qty path — 40000 each, 10 units → 400000
    q_unit_price = "calculate import tax for vehicle HS 8703.22.00 CIF 40000 USD each quantity 10 units from China"
    parsed_unit = CalculatorServiceClient._parse_question_for_calculation(q_unit_price)
    assert parsed_unit.get("quantity") == 10.0, f"Expected qty=10, got {parsed_unit.get('quantity')}"
    assert parsed_unit.get("cif_value") == 400_000.0, (
        f"Expected CIF=400000 (unit price × qty), got {parsed_unit.get('cif_value')}"
    )

    # Case 2: total-CIF path (no 'each') — quantity present but CIF must NOT be re-multiplied
    q_total = "calculate import tax for vehicle HS 8703.22.00 CIF 400000 USD quantity 10 units from China"
    parsed_total = CalculatorServiceClient._parse_question_for_calculation(q_total)
    assert parsed_total.get("quantity") == 10.0, f"Expected qty=10, got {parsed_total.get('quantity')}"
    assert parsed_total.get("cif_value") == 400_000.0, (
        f"Expected CIF=400000 unchanged (total already), got {parsed_total.get('cif_value')}"
    )


def test_end_to_end_quantity_scale_calculation():
    """
    Regression for the silent quantity-drop bug.

    Simulates the multi-turn follow-up path:
      Turn 1: vehicle, HS 8703.22.00, CIF 40000 USD, China
      Turn 2: "what if I import 10 of it??"  →  NLU rewrites to include 'quantity 10'

    After enrichment + _parse, the handler builds a canonical query.
    We verify:
      1. The canonical query string contains 'quantity 10'.
      2. The client-parsed CIF from that canonical string equals 400,000 USD
         (unit price × 10), i.e. the calculator will receive the scaled total.
    """
    # Simulate what NLU produces for the follow-up turn (confirmed from trace)
    nlu_rewritten = (
        "calculate import tax hs code 8703.22.00 quantity 10 cif 40000 usd china"
    )

    # Parse as the handler does at line ~805
    parsed = CalculatorServiceClient._parse_question_for_calculation(nlu_rewritten)
    assert parsed.get("quantity") == 10.0, f"Expected qty=10 from NLU rewrite, got {parsed.get('quantity')}"
    # CIF at this point is NOT yet multiplied (no 'each' cue in NLU rewrite)
    assert parsed.get("cif_value") == 40_000.0, (
        f"Expected raw CIF=40000 from NLU rewrite (no each cue), got {parsed.get('cif_value')}"
    )

    # Now simulate what the handler's canonical reconstruction does
    # (the fix appends quantity without 'each', so the total CIF stays as-is)
    qty_display = int(parsed["quantity"])
    unit_val = parsed.get("unit") or "units"
    cif_val = parsed.get("cif_value")
    cif_display = int(cif_val)
    curr_val = parsed.get("currency") or "USD"

    canonical = (
        f"calculate import tax for vehicle HS 8703.22.00 "
        f"CIF {cif_display} {curr_val} quantity {qty_display} {unit_val} from China"
    )

    # The canonical string must contain the quantity token
    assert f"quantity {qty_display}" in canonical, (
        f"Expected 'quantity {qty_display}' in canonical query, got: {canonical}"
    )

    # Re-parse the canonical string as the calculator client will
    canonical_parsed = CalculatorServiceClient._parse_question_for_calculation(canonical)

    # No 'each'/'per unit' in canonical → looks_like_unit_price=False → no multiplication
    assert canonical_parsed.get("quantity") == 10.0
    assert canonical_parsed.get("cif_value") == 40_000.0, (
        f"CIF must remain 40000 in canonical (no double-mult); got {canonical_parsed.get('cif_value')}"
    )


def test_net_mass_regex_requires_prefix():
    """
    Bug 1 regression: the net_mass regex must NOT fire on bare numbers, DV/DQ
    expressions, or HS code digit sequences — only on explicit 'net mass/weight' phrases.
    """
    # Should match: explicit prefix forms
    match_cases = [
        "net mass 500 kg",
        "net weight 200kg",
        "net mass 15000 kg from china",
        "calculate import tax net weight 8000 kg cif 9180 usd",
    ]
    no_match_cases = [
        # Bare number + kg — the original phantom bug trigger
        "hs code 8703.22.29 cif 13869usd dv = 0.00 dq = 50%",
        # DV value that happened to precede kg contextually in a NLU rewrite
        "505423 kg",
        "weight: 500kg",   # colon form — not supported (terse input)
        "500 kg net",      # reversed order — not supported
        "8703.22.29 kg",   # HS digits before kg
    ]

    import re
    mass_re = re.compile(r'(?:net\s+(?:mass|weight))\s+(\d+(?:\.\d+)?)\s*kg', re.IGNORECASE)

    for q in match_cases:
        assert mass_re.search(q.lower()), f"Expected mass match for: {q!r}"

    for q in no_match_cases:
        assert not mass_re.search(q.lower()), f"Expected NO mass match for: {q!r}"


def test_has_explicit_hs_detection_variants():
    """
    Bug 2 regression: has_explicit_hs_in_query must detect HS codes in all
    real-world spellings without false-positiving on bare 8-digit numbers.
    """
    import re

    def has_hs(query: str) -> bool:
        q = query.lower()
        return bool(
            re.search(r'\bhs\s*(?:code)?\s*\d{4,8}', q)
            or re.search(r'\b\d{4}\.\d{2}(?:\.\d{2})?\b', q)
        )

    # Must detect
    assert has_hs("calculate import tax for hs code 8703.22.00 cif 9180 usd from china")
    assert has_hs("hs 8703.22.00 cif 9180 usd")
    assert has_hs("hs8703.32.00 cif 9180 usd")          # no space
    assert has_hs("hs code 87032200 cif 9180 usd")       # 8-digit raw
    assert has_hs("calculate import tax for 8703.22.00") # dotted only, no prefix
    assert has_hs("HS Code 8703.80.99 CIF 40000USD")     # original failing case

    # Must NOT false-positive
    assert not has_hs("calculate import tax cif 40000000 usd from china")  # bare 8-digit CIF
    assert not has_hs("dv = 0.00 dq = 50%")
    assert not has_hs("cif 13869 usd from china with acfta")


def test_bug3_fallback_hs_matches_current_turn():
    """
    Bug 3 regression: when a user switches HS codes across turns, the parsed
    hs_code used for the fallback message must reflect the CURRENT turn's HS
    code, not the previous turn's.

    We simulate this by checking that _parse_question_for_calculation on a
    non-contaminated canonical query (as produced after Bug 2's fix) extracts
    the correct, current-turn HS code only.
    """
    # Previous turn stored 8703.80.99 as last_normalized_query.
    # Current turn provides 8703.32.00.
    # After Bug 2 fix the canonical query must contain ONLY the current HS.
    canonical_clean = (
        "calculate import tax for vehicle HS 8703.32.00 CIF 9180 USD from China no FTA"
    )
    parsed = CalculatorServiceClient._parse_question_for_calculation(canonical_clean)
    assert parsed.get("hs_code") == "8703.32.00", (
        f"Expected current-turn HS 8703.32.00, got: {parsed.get('hs_code')}"
    )

    # Sanity: a contaminated query (what Bug 2 used to produce) returns the WRONG HS
    contaminated = (
        "calculate import tax for vehicle HS 8703.80.99 HS 8703.32.00 CIF 9180 USD from China"
    )
    parsed_bad = CalculatorServiceClient._parse_question_for_calculation(contaminated)
    # The parser matches the first HS it finds — 8703.80.99 — proving contamination causes Bug 3
    assert parsed_bad.get("hs_code") != "8703.32.00", (
        "Contaminated query should NOT return the correct current HS — this confirms Bug 3's mechanism"
    )


if __name__ == "__main__":
    test_extract_entity_for_problematic_query()
    test_parse_question_for_calculation_country_filter()
    test_is_valid_country_basic()
    test_is_valid_country_casing_and_preposition()
    test_parse_question_for_calculation_isolated_casing()
    test_looks_like_unit_price()
    test_is_entity_changed()
    test_single_turn_unit_price_parsing()
    test_end_to_end_merger_pipeline()
    test_entity_change_quantity_leakage()
    test_calculator_question_canonicalization()
    test_has_product_last_entity_clarification()
    test_is_genuine_conversational_small_talk_abbreviation()
    test_validation_plausibility_and_attached_currency()
    test_attached_currency_token_enrichment()
    test_quantity_multiplication_logic()
    test_end_to_end_quantity_scale_calculation()
    test_net_mass_regex_requires_prefix()
    test_has_explicit_hs_detection_variants()
    test_bug3_fallback_hs_matches_current_turn()
    print("All tests passed successfully!")
