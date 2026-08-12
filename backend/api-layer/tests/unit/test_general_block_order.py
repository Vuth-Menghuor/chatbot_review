from app.services.chat_response_normalizer import normalize_chat_response


def block_types(response):
    return [block.type for block in response.message.content]


def test_successful_general_response_uses_stable_block_order():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "General answer.",
        "coverage": "partial",
        "limitations": ["The exact requirements depend on the product and HS code."],
        "clarifications": ["What product are you importing?"],
        "suggestions": ["How do I classify my goods?"],
    })

    assert block_types(response) == ["markdown", "clarification", "suggestions", "coverage"]
    assert response.message.content[0].text == "General answer."
    assert response.message.content[1].title == "More information is needed"
    assert response.message.content[2].title == "Suggested follow-ups"
    assert response.message.content[3].title == "Information limitation"


def test_general_success_blocks_use_supported_generic_types_in_recommended_order():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "General answer.",
        "limitations": ["The answer depends on the product."],
        "clarifications": ["Which product are you importing?"],
        "suggestions": ["What documents are needed?"],
        "citations": [{"document_id": "1021", "title": "Conditions for Import or Export"}],
    })

    assert block_types(response) == ["markdown", "clarification", "suggestions", "coverage"]
    assert set(block_types(response)).issubset({
        "markdown",
        "coverage",
        "clarification",
        "suggestions",
        "references",
        "error",
    })
    assert "references" not in block_types(response)
    assert len(response.citations) == 1


def test_general_explicit_message_content_blocks_have_priority_over_generated_blocks():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "Plain fallback answer.",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "markdown", "text": "Service-authored visual answer."},
                {"type": "suggestions", "items": ["Service-authored follow-up"]},
            ],
        },
        "clarifications": ["This should not be appended."],
        "suggestions": ["This should not be duplicated."],
        "limitations": ["This should not be appended."],
    })

    assert response.response.content == "Plain fallback answer."
    assert block_types(response) == ["markdown", "suggestions"]
    assert response.message.content[0].text == "Service-authored visual answer."
    assert response.message.content[1].items == ["Service-authored follow-up"]


def test_general_final_answer_is_used_as_plain_text_answer_source():
    response = normalize_chat_response({
        "intent": "general",
        "final_answer": "Final answer from the upstream service.",
        "suggestions": ["What documents are needed?"],
    })

    assert response.response.content == "Final answer from the upstream service."
    assert block_types(response) == ["markdown", "suggestions"]
    assert response.message.content[0].text == "Final answer from the upstream service."


def test_general_missing_answer_uses_clarification_before_suggestions_and_coverage():
    response = normalize_chat_response({
        "intent": "general",
        "clarifications": ["Which topic should I explain?"],
        "suggestions": ["Ask about import documents"],
        "limitations": ["The topic was not provided."],
    })

    assert block_types(response) == ["clarification", "suggestions", "coverage"]
    assert response.message.content[0].questions == ["Which topic should I explain?"]
    assert response.message.content[1].items == ["Ask about import documents"]
    assert response.message.content[2].items == ["The topic was not provided."]


def test_general_failed_payload_without_answer_returns_stable_error_block():
    response = normalize_chat_response({
        "intent": "general",
        "status": "failed",
    })

    assert response.status == "failed"
    assert block_types(response) == ["error"]
    assert response.errors[0].code == "INTERNAL_API_ERROR"
    assert response.message.content[0].message == "The request could not be completed."


def test_successful_general_response_without_optional_blocks_contains_markdown_only():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "General answer.",
        "coverage": "unknown",
        "citations": [{"document_id": "1021", "title": "Conditions for Import or Export"}],
    })

    assert block_types(response) == ["markdown"]
    assert len(response.citations) == 1


def test_general_response_keeps_citations_top_level_without_reference_block_duplication():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "General answer.",
        "citations": [
            {
                "document_id": "1021",
                "title": "Conditions for Import or Export",
                "snippet": "Reference snippet.",
            }
        ],
        "suggestion": ["What documents are required?"],
    })

    assert response.citations[0].title == "Conditions for Import or Export"
    assert "references" not in block_types(response)
    assert block_types(response) == ["markdown", "suggestions"]
