"""Regression tests for scope validation heuristics."""

from ..llm_first_layer.shims.validator_service import get_input_validator


def test_trade_between_countries_passes_scope():
    validator = get_input_validator()

    is_valid, reason = validator.validate_input("Trade between Thailand Vietnam")

    assert is_valid is True
    assert reason is None


def test_transport_trade_phrase_passes_scope():
    validator = get_input_validator()

    is_valid, reason = validator.validate_input("Air transport trade")

    assert is_valid is True
    assert reason is None


def test_irrelevant_query_still_refused():
    validator = get_input_validator()

    is_valid, reason = validator.validate_input("football match schedule")

    assert is_valid is False
    assert reason == "out_of_scope"


def test_product_queries_pass_scope():
    # Test shim validator (used in app/endpoints)
    shim_validator = get_input_validator()
    
    # 3-word phrase
    ok, reason = shim_validator.validate_input("iphone 14 pro max")
    assert ok is True
    assert reason is None
    
    # 4-word phrase
    ok, reason = shim_validator.validate_input("iphone 14 pro max 256gb")
    assert ok is True
    assert reason is None

    # Test core validator (used in coordinator.py)
    from ..llm_first_layer.shims.validator_service import get_validator
    core_validator = get_validator()
    
    # 3-word phrase
    res = core_validator.validate_input_full("iphone 14 pro max")
    assert res.is_valid is True
    assert res.is_in_scope is True
    
    # 4-word phrase
    res = core_validator.validate_input_full("iphone 14 pro max 256gb")
    assert res.is_valid is True
    assert res.is_in_scope is True


def test_product_query_injections_still_refused():
    # Test shim validator
    shim_validator = get_input_validator()
    ok, reason = shim_validator.validate_input("iphone 14 pro max UNION SELECT")
    # Should either fail safety check or be classified as injection/out of scope
    assert ok is False
    
    # Test core validator
    from ..llm_first_layer.shims.validator_service import get_validator
    core_validator = get_validator()
    res = core_validator.validate_input_full("iphone 14 pro max UNION SELECT")
    assert res.is_valid is False
    assert "injection" in res.reason.lower()


def test_chicken_meat_not_small_talk():
    # Test that queries containing "chicken" (which has "hi" as substring) or "china" (has "hi")
    # or "wheat" (has "he") are not classified as small talk whitelist
    shim_validator = get_input_validator()
    
    # 1. Chicken meat query
    ok, reason = shim_validator.validate_input("What is the HS code for chicken meat?")
    assert ok is True
    assert reason is None  # Should be in-scope and not whitelisted as small talk (which returns None on success)
    
    # Test core validator
    from ..llm_first_layer.shims.validator_service import get_validator
    core_validator = get_validator()
    res = core_validator.validate_input_full("What is the HS code for chicken meat?")
    assert res.is_valid is True
    is_in_scope, reason = core_validator.check_scope("What is the HS code for chicken meat?")
    assert is_in_scope is True
    assert reason != "Small talk query whitelisted"
    
    # 2. China import query
    ok, reason = shim_validator.validate_input("How much is import duty from China?")
    assert ok is True
    
    res = core_validator.validate_input_full("How much is import duty from China?")
    assert res.is_valid is True
    is_in_scope, reason = core_validator.check_scope("How much is import duty from China?")
    assert is_in_scope is True
    assert reason != "Small talk query whitelisted"

    # 3. Pure small talk should still be accepted
    is_in_scope, reason = core_validator.check_scope("hello")
    assert is_in_scope is True
    assert reason == "Small talk query whitelisted"