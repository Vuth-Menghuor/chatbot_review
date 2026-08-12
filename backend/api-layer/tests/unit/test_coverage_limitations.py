from app.services.chat_response_normalizer import normalize_chat_response


def coverage_blocks(response):
    return [block for block in response.message.content if block.type == "coverage"]


def test_partial_answer_creates_information_limitation_block_from_limitations_without_changing_answer():
    answer = "Import requirements vary by product."

    response = normalize_chat_response({
        "intent": "general",
        "answer": answer,
        "coverage": "partial",
        "limitations": ["The exact requirements depend on the product and HS code."],
    })

    blocks = coverage_blocks(response)

    assert response.coverage == "partial"
    assert response.response.coverage == "partial"
    assert response.response.content == answer
    assert response.message.content[0].text == answer
    assert blocks[0].title == "Information limitation"
    assert blocks[0].tone == "warning"
    assert blocks[0].items == ["The exact requirements depend on the product and HS code."]
    assert blocks[0].note is None


def test_unknown_coverage_without_limitation_does_not_show_warning():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "General customs answer.",
        "coverage": "unknown",
    })

    assert response.coverage == "unknown"
    assert coverage_blocks(response) == []


def test_limitations_are_normalized_from_missing_data_and_warnings():
    missing_data_response = normalize_chat_response({
        "intent": "general",
        "answer": "General answer.",
        "coverage": "partial",
        "missing_data": [{"message": "The product HS code was not provided."}],
    })
    warning_response = normalize_chat_response({
        "intent": "general",
        "answer": "General answer.",
        "coverage": "partial",
        "warnings": ["The exact requirements may vary by checkpoint."],
    })

    assert missing_data_response.response.limitations[0].message == "The product HS code was not provided."
    assert coverage_blocks(missing_data_response)[0].items == ["The product HS code was not provided."]
    assert warning_response.response.limitations[0].message == "The exact requirements may vary by checkpoint."
    assert coverage_blocks(warning_response)[0].items == ["The exact requirements may vary by checkpoint."]


def test_coverage_is_not_inferred_from_answer_length():
    long_answer = "Long answer. " * 200

    response = normalize_chat_response({
        "intent": "general",
        "answer": long_answer,
    })

    assert response.coverage == "unknown"
    assert response.response.coverage == "unknown"
    assert coverage_blocks(response) == []
