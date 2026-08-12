import ast
from pathlib import Path

from app.core.config import Settings
from app.services.chat_debug import can_include_chat_response_debug
from app.services.chat_response_normalizer import normalize_chat_response


DEBUG_PAYLOAD = {
    "intent": "general",
    "answer": "Debug contract answer.",
    "answer_source": "gemini_llm",
    "latency_ms": 42,
    "semantic_count": 3,
    "metadata": {
        "language": "en",
        "nlu_unified_result": {"intent": "general"},
        "service_query": "internal rewritten query",
        "service_latencies_s": {"general": 1.2},
        "api_key": "cb_secret",
        "raw_token": "token-value",
        "complete_internal_prompt": "full internal prompt",
        "nested": {
            "safe": "kept",
            "password": "not-kept",
            "internal_url": "http://internal.service.local",
        },
    },
}


def test_debug_is_not_included_by_default():
    response = normalize_chat_response(DEBUG_PAYLOAD)

    assert response.debug is None
    assert "debug" not in response.model_dump(mode="json", exclude_none=True)


def test_debug_can_be_included_explicitly():
    response = normalize_chat_response(DEBUG_PAYLOAD, include_debug=True)

    assert response.debug is not None
    assert response.debug.answer_source == "gemini_llm"
    assert response.debug.latency_ms == 42
    assert response.debug.semantic_count == 3


def test_debug_metadata_omits_sensitive_internal_fields():
    response = normalize_chat_response(DEBUG_PAYLOAD, include_debug=True)

    assert response.debug is not None
    metadata = response.debug.metadata

    assert metadata["language"] == "en"
    assert metadata["nested"] == {"safe": "kept"}
    assert "nlu_unified_result" not in metadata
    assert "service_query" not in metadata
    assert "service_latencies_s" not in metadata
    assert "api_key" not in metadata
    assert "raw_token" not in metadata
    assert "complete_internal_prompt" not in metadata


def test_trade_internal_metadata_is_not_public_and_is_sanitized_in_debug():
    payload = {
        "intent": "trade_query",
        "answer": "Trade answer.",
        "metadata": {
            "language": "en",
            "dal_source_url": "http://dal.internal/query",
            "query_params": {"partner": "Vietnam"},
            "filters": {"year": 2024},
            "internal_dimensions": ["partner_country", "flow"],
            "execution_plan": {"scan": "trade_records"},
            "raw_count_diagnostics": {"before_limit": 5000},
            "provider_details": {"name": "internal-provider"},
            "sql": "select * from trade_records",
            "sql_query": "select value_usd from trade_records",
            "routing_metadata": {"service": "trade_data"},
            "nested": {
                "safe": "kept",
                "query_plan": {"steps": ["scan"]},
                "sql_params": {"year": 2024},
            },
        },
    }

    public_response = normalize_chat_response(payload)
    debug_response = normalize_chat_response(payload, include_debug=True)

    assert "metadata" not in public_response.model_dump(mode="json", exclude_none=True)
    assert public_response.debug is None
    assert debug_response.debug is not None
    metadata = debug_response.debug.metadata
    assert metadata == {
        "language": "en",
        "nested": {"safe": "kept"},
    }
    debug_json = debug_response.model_dump(mode="json")
    assert "dal.internal" not in str(debug_json)
    assert "trade_records" not in str(debug_json)
    assert "internal-provider" not in str(debug_json)
    assert "partner_country" not in str(debug_json)


def test_chat_response_debug_flag_defaults_to_false(monkeypatch):
    monkeypatch.delenv("ENABLE_CHAT_RESPONSE_DEBUG", raising=False)

    assert Settings(_env_file=None).enable_chat_response_debug is False


def test_chat_response_debug_flag_reads_environment_variable(monkeypatch):
    monkeypatch.setenv("ENABLE_CHAT_RESPONSE_DEBUG", "true")

    assert Settings(_env_file=None).enable_chat_response_debug is True


def test_debug_flag_false_development_returns_no_debug():
    assert can_include_chat_response_debug(
        enable_debug=False,
        environment="development",
        role="user",
    ) is False


def test_debug_flag_true_development_returns_debug():
    assert can_include_chat_response_debug(
        enable_debug=True,
        environment="development",
        role="user",
    ) is True


def test_debug_flag_true_production_normal_user_returns_no_debug():
    assert can_include_chat_response_debug(
        enable_debug=True,
        environment="production",
        role="user",
    ) is False


def test_debug_flag_true_production_administrator_returns_debug():
    assert can_include_chat_response_debug(
        enable_debug=True,
        environment="production",
        role="administrator",
    ) is True


def test_chat_routes_do_not_expose_unrestricted_debug_query_parameter():
    chat_endpoint_path = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints" / "chat.py"
    tree = ast.parse(chat_endpoint_path.read_text())
    route_functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name in {"send_chat", "stream_chat"}
    }

    for route_function in route_functions.values():
        arg_names = [arg.arg for arg in route_function.args.args]
        assert "debug" not in arg_names
        assert "include_debug" not in arg_names
