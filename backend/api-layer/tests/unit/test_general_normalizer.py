from app.services.chat_response_normalizer import normalize_chat_response, normalizer_registry


def test_general_normalizer_handles_intent_answer_payload_without_changing_answer():
    answer = "Customs valuation is the process of determining the value of imported goods."

    response = normalize_chat_response({
        "intent": "general",
        "answer": answer,
        "suggestion": [
            "How do I classify my goods?",
            "How is customs duty calculated?",
        ],
        "citations": [{"id": "doc-1", "title": "Customs Guide"}],
        "clarifications": ["Which country are you importing into?"],
        "latency_ms": 125,
        "language": "en",
        "status": "success",
    })

    assert response.api_version == "1.0"
    assert response.service == "general"
    assert response.status == "completed"
    assert response.language == "en"
    assert response.response.content == answer
    assert response.message.content[0].type == "markdown"
    assert response.message.content[0].text == answer
    assert response.suggestions == [
        "How do I classify my goods?",
        "How is customs duty calculated?",
    ]
    assert response.citations[0].title == "Customs Guide"
    assert response.metrics["latency_ms"] == 125


def test_general_response_content_is_exact_fallback_and_message_blocks_are_visual_source():
    answer = "Original service answer\n\nKeep this text exactly as returned."

    response = normalize_chat_response({
        "request_id": "req-general-contract",
        "session_id": "session-general-contract",
        "intent": "general",
        "status": "completed",
        "answer": answer,
        "suggestions": ["What documents are needed?"],
    })

    assert response.api_version == "1.0"
    assert response.request_id == "req-general-contract"
    assert response.session_id == "session-general-contract"
    assert response.status == "completed"
    assert response.service == "general"
    assert response.intent == "general"
    assert response.response.type == "markdown"
    assert response.response.content == answer
    assert response.response.limitations == []
    assert response.message.role == "assistant"
    assert [block.type for block in response.message.content] == ["markdown", "suggestions"]
    assert response.message.content[0].text == answer
    assert response.citations == []
    assert response.suggestions == ["What documents are needed?"]
    assert response.clarifications == []
    assert response.errors == []
    assert response.metrics == {}


def test_general_normalizer_handles_service_message_payload_without_changing_message():
    message = "You can ask general customs questions here."

    response = normalize_chat_response({
        "service": "general",
        "message": message,
        "followups": ["What documents are required?"],
    })

    assert response.service == "general"
    assert response.response.content == message
    assert response.message.content[0].text == message
    assert response.suggestions == ["What documents are required?"]


def test_general_normalizer_handles_singular_suggestion_alias():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "Here is the answer.",
        "suggestion": ["How do I classify my goods?"],
    })

    assert response.service == "general"
    assert response.suggestions == ["How do I classify my goods?"]


def test_general_normalizer_maps_failed_payload_to_safe_public_error():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "The request could not be completed.",
        "status": "failed",
        "errors": ["Traceback: upstream timeout at http://general-service.internal using secret"],
    })

    assert response.service == "general"
    assert response.status == "failed"
    assert response.errors[0].code == "GENERAL_TIMEOUT"
    assert response.errors[0].message == "The general service timed out."
    assert [block.message for block in response.message.content if block.type == "error"] == [
        "The general service timed out."
    ]
    public_text = f"{response.errors[0].message} {response.message.content[-1].message}"
    assert "Traceback" not in public_text
    assert "general-service.internal" not in public_text
    assert "secret" not in public_text


def test_registry_uses_fallback_for_unknown_payloads():
    assert normalizer_registry.normalize({"unexpected": object()}) == "unknown"


def test_general_success_contract_preserves_answer_and_stable_block_order_without_duplicates():
    answer = "Original service answer with (Document 1) kept exactly."

    response = normalize_chat_response({
        "intent": "general",
        "answer": answer,
        "suggestions": ["Ask about import documents", "Calculate import tax"],
        "clarifications": ["Are you asking about import or export?"],
        "limitations": ["Some requested information was not available."],
        "citations": [
            {"document_id": "doc-1", "title": "Customs Guide"},
            "GDCE Public Notice",
            "GDCE Public Notice",
        ],
    })

    assert response.response.content == answer
    assert [block.type for block in response.message.content] == [
        "markdown",
        "clarification",
        "suggestions",
        "coverage",
    ]
    assert response.message.content[0].text == answer
    assert len([block for block in response.message.content if block.type == "markdown"]) == 1
    assert len([block for block in response.message.content if block.type == "suggestions"]) == 1
    assert response.message.content[2].items == response.suggestions
    assert [citation.title for citation in response.citations] == ["Customs Guide", "GDCE Public Notice"]
    assert "references" not in [block.type for block in response.message.content]


def test_general_plain_text_fallback_uses_string_message_without_changing_value():
    response = normalize_chat_response({
        "service": "general",
        "message": "Plain text message from General service.",
    })

    assert response.response.content == "Plain text message from General service."
    assert [block.type for block in response.message.content] == ["markdown"]
    assert response.message.content[0].text == "Plain text message from General service."


def test_general_answer_is_inserted_before_explicit_suggestions_only_blocks():
    answer = "A dog is a domesticated mammal."
    response = normalize_chat_response({
        "intent": "general",
        "answer": answer,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "suggestions",
                    "items": [
                        "How do I classify my goods?",
                        "How is customs duty calculated?",
                    ],
                },
            ],
        },
    })

    assert response.response.content == answer
    assert [block.type for block in response.message.content] == ["markdown", "suggestions"]
    assert response.message.content[0].text == answer
    assert response.message.content[1].items == [
        "How do I classify my goods?",
        "How is customs duty calculated?",
    ]


def test_general_empty_answer_returns_safe_markdown_fallback():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "",
        "status": "completed",
    })

    assert response.response.content == ""
    assert [block.type for block in response.message.content] == ["markdown"]
    assert response.message.content[0].text == ""


def test_general_malformed_response_does_not_crash_and_uses_safe_visual_blocks():
    response = normalize_chat_response({
        "service": "general",
        "answer": {"unexpected": object()},
        "suggestions": ["Try asking a customs question"],
    })

    assert response.service == "general"
    assert response.response.content == ""
    assert [block.type for block in response.message.content] == ["suggestions"]
    assert response.message.content[0].items == ["Try asking a customs question"]


def test_general_unknown_extra_fields_do_not_change_service_values():
    answer = "Services-team answer must remain unchanged."

    response = normalize_chat_response({
        "intent": "general",
        "answer": answer,
        "unknown_extra": {"nested": "value"},
        "metadata": {"unexpected": "debug-only"},
        "latency_ms": 99,
    })

    assert response.response.content == answer
    assert response.message.content[0].text == answer
    assert response.metrics["latency_ms"] == 99
