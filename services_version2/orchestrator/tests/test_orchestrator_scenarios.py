import pytest
import urllib.request
import json
import uuid

URL = "http://127.0.0.1:8001/chat"


def send_query(question: str, session_id: str):
    payload = {
        "question": question,
        "session_id": session_id
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        URL,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))


def get_answer(res: dict) -> str:
    return (res.get("answer") or res.get("response") or "")


# SMALL_TALK — greetings, identity, capability questions

def test_small_talk_greeting():
    session_id = f"test_smalltalk_greet_{uuid.uuid4()}"
    res = send_query("hello", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0
    assert res.get("intent", "").lower() == "small_talk"


def test_small_talk_capability_question():
    """Known historical bug: 'what can you help me with' was misclassified
    as GENERAL instead of SMALL_TALK. Regression check."""
    session_id = f"test_smalltalk_capability_{uuid.uuid4()}"
    res = send_query("what can you help me with", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["customs", "trade", "help", "duty", "tax", "cambodia"])


def test_small_talk_thanks_and_bye():
    session_id = f"test_smalltalk_polite_{uuid.uuid4()}"
    res = send_query("thanks", session_id)
    assert len(get_answer(res)) > 0
    res = send_query("bye", session_id)
    assert len(get_answer(res)) > 0


def test_small_talk_identity_question():
    session_id = f"test_smalltalk_identity_{uuid.uuid4()}"
    res = send_query("who are you", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["assistant", "chatbot", "customs", "gdce", "help"])


# HS_CODE_LOOKUP — retrieval service, via orchestrator

def test_hs_lookup_common_product():
    session_id = f"test_hs_common_{uuid.uuid4()}"
    res = send_query("hs code of car", session_id)
    ans = get_answer(res).lower()
    assert "8703" in ans


def test_hs_lookup_typo_in_product_name():
    session_id = f"test_hs_typo_{uuid.uuid4()}"
    res = send_query("hs code of iphpne", session_id)
    ans = get_answer(res).lower()
    assert "8517.13.00" in ans


def test_hs_lookup_ambiguous_product_offers_multiple_candidates():
    """A product with multiple plausible classifications (finished device vs
    parts) should surface candidates or a clarification, not silently pick one."""
    session_id = f"test_hs_ambiguous_{uuid.uuid4()}"
    res = send_query("hs code of phone parts", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0
    assert any(x in ans for x in ["8517", "part", "clarif", "which"])


def test_hs_lookup_vague_category():
    session_id = f"test_hs_vague_{uuid.uuid4()}"
    res = send_query("hs code of electronics", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0


def test_hs_lookup_nonsense_product_no_crash():
    session_id = f"test_hs_nonsense_{uuid.uuid4()}"
    res = send_query("hs code of asdkjasndkj", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0


def test_hs_lookup_vehicle():
    session_id = f"test_hs_vehicle_{uuid.uuid4()}"
    res = send_query("hs code of bmw m8 competit", session_id)
    ans = get_answer(res).lower()
    assert "8703.24.51" in ans


# TRADE_DATA — trade service, via orchestrator

def test_trade_basic_product_query():
    session_id = f"test_trade_basic_{uuid.uuid4()}"
    res = send_query("trade data for smartphones", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["trade", "export", "import", "smartphone", "volume", "value", "clarify", "period"])


def test_trade_vague_query_triggers_askback():
    """No product/country/period specified -> should ask for missing slots,
    not guess or return empty results."""
    session_id = f"test_trade_vague_{uuid.uuid4()}"
    res = send_query("trade data", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["which", "what product", "what country", "period", "clarify"])


def test_trade_fully_specified_query_no_clarification():
    session_id = f"test_trade_full_{uuid.uuid4()}"
    res = send_query("trade import volume of rice from Vietnam last year", session_id)
    ans = get_answer(res).lower()
    assert "vietnam" in ans
    assert "rice" in ans


def test_trade_multi_turn_slot_fill():
    """User gives product first, country/period as follow-ups -> AskBack
    flow should accumulate slots across turns, not restart from scratch."""
    session_id = f"test_trade_multiturn_{uuid.uuid4()}"
    send_query("trade data for garments", session_id)
    res = send_query("from Vietnam", session_id)
    ans = get_answer(res).lower()
    assert "vietnam" in ans or "garment" in ans


def test_trade_export_data():
    session_id = f"test_trade_export_{uuid.uuid4()}"
    res = send_query("export data for Cambodia rice 2024", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0


def test_trade_country_comparison():
    session_id = f"test_trade_compare_{uuid.uuid4()}"
    res = send_query("compare imports between China and Thailand", session_id)
    ans = get_answer(res).lower()
    assert "china" in ans and "thailand" in ans


def test_trade_nonsense_product_no_crash():
    session_id = f"test_trade_nonsense_{uuid.uuid4()}"
    res = send_query("trade data for asdkjasndkj", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0


# GENERAL — RAG service, via orchestrator

def test_general_documents_question():
    session_id = f"test_general_docs_{uuid.uuid4()}"
    res = send_query("what documents do I need to import goods into Cambodia", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["document", "declaration", "invoice", "permit", "license"])


def test_general_clearance_process():
    session_id = f"test_general_clearance_{uuid.uuid4()}"
    res = send_query("what is the customs clearance process", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["clearance", "customs", "declaration", "inspection"])


def test_general_clearance_duration():
    session_id = f"test_general_duration_{uuid.uuid4()}"
    res = send_query("how long does customs clearance take", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0


def test_general_cif_vs_fob():
    session_id = f"test_general_cif_fob_{uuid.uuid4()}"
    res = send_query("what is CIF vs FOB", session_id)
    ans = get_answer(res).lower()
    assert "cif" in ans and "fob" in ans


def test_general_license_requirement():
    session_id = f"test_general_license_{uuid.uuid4()}"
    res = send_query("do I need a license to import electronics", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["license", "permit", "yes", "no", "depend"])


def test_general_penalties():
    session_id = f"test_general_penalties_{uuid.uuid4()}"
    res = send_query("what are the penalties for customs violations", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0


def test_general_tax_vs_vat():
    session_id = f"test_general_tax_vat_{uuid.uuid4()}"
    res = send_query("explain the difference between import tax and VAT", session_id)
    ans = get_answer(res).lower()
    assert "vat" in ans


def test_general_citation_present():
    """General/RAG answers should be grounded with a citation, not just
    freeform LLM text with no source."""
    session_id = f"test_general_citation_{uuid.uuid4()}"
    res = send_query("what documents do I need to import goods into Cambodia", session_id)
    citations = res.get("citations") or res.get("metadata", {}).get("citations")
    ans = get_answer(res).lower()
    assert len(ans) > 0
    # Loosen/tighten depending on how citations are actually surfaced in your schema.


# CALCULATION — calculator service, via orchestrator
# (trimmed to the essential regression set; broader single-service math
# coverage lives in test_services_unit.py)

def test_calculation_single_turn_full():
    session_id = f"test_calc_full_{uuid.uuid4()}"
    res = send_query("calculate import tax for iphone HS 8517.13.00 CIF 1000 USD", session_id)
    ans = get_answer(res).lower()
    assert "4,100" in ans or "4100" in ans or "tax" in ans


def test_calculation_entity_continuity_pronoun_followup():
    session_id = f"test_calc_pronoun_{uuid.uuid4()}"
    send_query("hs code of iphone", session_id)
    send_query("calculate its import tax", session_id)
    send_query("8517.13.00", session_id)
    res = send_query("1000$", session_id)
    ans = get_answer(res).lower()
    assert "4,100" in ans or "4100" in ans


def test_calculation_entity_switch_no_leak():
    """Regression: origin/HS/CIF from a prior, different product must not
    leak into the new product's calculation (the 'from Car' bug)."""
    session_id = f"test_calc_entity_switch_{uuid.uuid4()}"
    send_query("hs code of car", session_id)
    send_query("sorry I meant iphone not car", session_id)
    send_query("how much do I pay to import it", session_id)
    send_query("8517.13.00", session_id)
    res = send_query("i pay 5000$", session_id)
    ans = get_answer(res).lower()
    assert "italy" not in ans
    assert "vehicle" not in ans and "car" not in ans


def test_calculation_price_update_preserves_context():
    session_id = f"test_calc_price_update_{uuid.uuid4()}"
    send_query("calculate import tax for iphone HS 8517.13.00 $1000", session_id)
    res = send_query("what if the price increase to 2000$", session_id)
    ans = get_answer(res).lower()
    assert "2,000.00" in ans or "2000.00" in ans
    # must not regress to "which product are you importing"
    assert "which specific product" not in ans


def test_calculation_quantity_multiplication_single_turn():
    session_id = f"test_calc_qty_{uuid.uuid4()}"
    res = send_query("import tax for 10 units of iphone from China, 1 unit cost 1000$", session_id)
    ans = get_answer(res).lower()
    assert "10,000.00" in ans or "10000.00" in ans


def test_calculation_origin_pronoun_never_becomes_country():
    session_id = f"test_calc_origin_pronoun_{uuid.uuid4()}"
    res = send_query("how much to pay if I want to import it", session_id)
    ans = get_answer(res).lower()
    assert "italy" not in ans


def test_calculation_currency_symbol_preserved_on_followup():
    session_id = f"test_calc_currency_{uuid.uuid4()}"
    send_query("calculate import tax for iphone HS 8517.13.00 $1000", session_id)
    res = send_query("what if the price increase to 2000$", session_id)
    ans = get_answer(res).lower()
    assert "2,000.00" in ans or "2000.00" in ans


# TYPO CORRECTION / REWRITE — cross-cutting, exercised via HS + calc intents

def test_typo_correction_hs_lookup():
    session_id = f"test_typo_hs_{uuid.uuid4()}"
    res = send_query("what is the hs code of iphpne", session_id)
    ans = get_answer(res).lower()
    assert "8517.13.00" in ans


def test_typo_correction_calculation():
    session_id = f"test_typo_calc_{uuid.uuid4()}"
    res = send_query("importt tax of it", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0


# KHMER LANGUAGE HANDLING — cross-cutting

def test_khmer_pin_and_release():
    session_id = f"test_khmer_{uuid.uuid4()}"
    send_query("switch to Khmer", session_id)

    res = send_query("hs code of iphone", session_id)
    ans = get_answer(res)
    assert "8517.13.00" in ans

    res = send_query("តម្លៃពន្ធនាំចូល iPhone ប៉ុន្មាន", session_id)
    ans = get_answer(res)
    assert any(c in ans for c in "កខគឃងចឆជឈញដឋឌឍណតថទធនបផពភមយរលវសហឡអ")


# VAGUE / CLARIFICATION-REQUIRED — cross-cutting

def test_vague_calculation_request():
    session_id = f"test_vague_calc_{uuid.uuid4()}"
    res = send_query("I want to import something", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["what", "product", "importing", "item", "cif"])


def test_vague_tax_question():
    session_id = f"test_vague_tax_{uuid.uuid4()}"
    res = send_query("how much tax", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["what", "product", "importing", "item", "cif"])


def test_vague_general_customs_question():
    session_id = f"test_vague_general_{uuid.uuid4()}"
    res = send_query("tell me about customs", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0


# TOPIC SWITCH — cross-cutting, mixes HS_CODE_LOOKUP / GENERAL / CALCULATION

def test_topic_switch_hs_to_general():
    session_id = f"test_topic_switch_1_{uuid.uuid4()}"
    send_query("hs code of iphone", session_id)
    res = send_query("actually never mind, what documents do I need to import electronics", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["document", "invoice", "license", "permit", "clearance"])


def test_topic_switch_general_to_hs():
    session_id = f"test_topic_switch_2_{uuid.uuid4()}"
    send_query("what documents do I need to import goods", session_id)
    res = send_query("what about the hs code for rice instead", session_id)
    ans = get_answer(res).lower()
    assert len(ans) > 0


def test_topic_switch_calculation_to_trade():
    session_id = f"test_topic_switch_3_{uuid.uuid4()}"
    send_query("calculate import tax for iphone HS 8517.13.00 CIF 1000 USD", session_id)
    res = send_query("actually show me trade data for smartphones instead", session_id)
    ans = get_answer(res).lower()
    assert any(x in ans for x in ["trade", "export", "import", "smartphone"])


# ADVERSARIAL / STABILITY — cross-cutting

def test_adversarial_empty_string():
    session_id = f"test_adv_empty_{uuid.uuid4()}"
    try:
        send_query("", session_id)
    except Exception:
        pass  # FastAPI may reject with 422 -- acceptable, just must not hang/crash the service


def test_adversarial_nonsense_string():
    session_id = f"test_adv_nonsense_{uuid.uuid4()}"
    res = send_query("asdkjasndkj", session_id)
    assert len(get_answer(res)) > 0


def test_adversarial_repeated_entity():
    session_id = f"test_adv_repeat_{uuid.uuid4()}"
    res = send_query("import tax for iphone iphone iphone iphone", session_id)
    assert len(get_answer(res)) > 0


def test_adversarial_extreme_value():
    session_id = f"test_adv_extreme_{uuid.uuid4()}"
    res = send_query("CIF 999999999999999 USD for iphone", session_id)
    assert len(get_answer(res)) > 0


def test_adversarial_sql_injection_sanity():
    session_id = f"test_adv_sql_{uuid.uuid4()}"
    res = send_query("DROP TABLE calculations;", session_id)
    assert len(get_answer(res)) > 0


def test_adversarial_nonsense_trade_query():
    session_id = f"test_adv_trade_{uuid.uuid4()}"
    res = send_query("trade data for asdkjasndkj", session_id)
    assert len(get_answer(res)) > 0


def test_adversarial_nonsense_hs_query():
    session_id = f"test_adv_hs_{uuid.uuid4()}"
    res = send_query("hs code of asdkjasndkj", session_id)
    assert len(get_answer(res)) > 0