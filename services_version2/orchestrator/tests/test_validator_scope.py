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
    from ..core.validators import get_validator
    core_validator = get_validator()
    
    # 3-word phrase
    res = core_validator.validate_input("iphone 14 pro max")
    assert res.is_valid is True
    assert res.is_in_scope is True
    
    # 4-word phrase
    res = core_validator.validate_input("iphone 14 pro max 256gb")
    assert res.is_valid is True
    assert res.is_in_scope is True


def test_product_query_injections_still_refused():
    # Test shim validator
    shim_validator = get_input_validator()
    ok, reason = shim_validator.validate_input("iphone 14 pro max UNION SELECT")
    # Should either fail safety check or be classified as injection/out of scope
    assert ok is False
    
    # Test core validator
    from ..core.validators import get_validator
    core_validator = get_validator()
    res = core_validator.validate_input("iphone 14 pro max UNION SELECT")
    assert res.is_valid is False
    assert "injection" in res.reason.lower()