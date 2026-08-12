from app.services.chat_response_normalizer import normalize_chat_response


EXPECTED_SUGGESTIONS = [
    "How do I classify my goods?",
    "How is customs duty calculated?",
]


def normalize(payload: dict):
    return normalize_chat_response({"intent": "general", "answer": "Here is the answer.", **payload})


def suggestion_block_items(response):
    for block in response.message.content:
        if block.type == "suggestions":
            return block.items
    return []


def suggestion_blocks(response):
    return [block for block in response.message.content if block.type == "suggestions"]


def test_accepts_singular_suggestion_list():
    response = normalize({"suggestion": EXPECTED_SUGGESTIONS})

    assert response.api_version == "1.0"
    assert response.suggestions == EXPECTED_SUGGESTIONS
    assert suggestion_block_items(response) == EXPECTED_SUGGESTIONS
    assert suggestion_blocks(response)[0].title == "Suggested follow-ups"


def test_accepts_plural_suggestions_list():
    response = normalize({"suggestions": EXPECTED_SUGGESTIONS})

    assert response.suggestions == EXPECTED_SUGGESTIONS
    assert suggestion_block_items(response) == EXPECTED_SUGGESTIONS
    assert len(suggestion_blocks(response)) == 1
    assert suggestion_blocks(response)[0].items == response.suggestions
    assert suggestion_blocks(response)[0].title == "Suggested follow-ups"


def test_missing_suggestions_returns_empty_contract_field():
    response = normalize({})

    assert response.suggestions == []
    assert suggestion_block_items(response) == []


def test_invalid_suggestions_return_empty_contract_field():
    response = normalize({"suggestions": {"question": "How do I classify my goods?"}})

    assert response.suggestions == []
    assert suggestion_block_items(response) == []


def test_empty_suggestion_strings_are_removed():
    response = normalize({"suggestion": ["", "  ", "How do I classify my goods?"]})

    assert response.suggestions == ["How do I classify my goods?"]
    assert suggestion_block_items(response) == ["How do I classify my goods?"]


def test_duplicate_suggestions_are_removed():
    response = normalize({
        "suggestion": [
            "How do I classify my goods?",
            "How do I classify my goods?",
            "  How is customs duty calculated?  ",
        ]
    })

    assert response.suggestions == EXPECTED_SUGGESTIONS
    assert suggestion_block_items(response) == EXPECTED_SUGGESTIONS


def test_accepts_follow_up_questions_list():
    response = normalize({"follow_up_questions": EXPECTED_SUGGESTIONS})

    assert response.suggestions == EXPECTED_SUGGESTIONS
    assert suggestion_block_items(response) == EXPECTED_SUGGESTIONS


def test_accepts_followups_list():
    response = normalize({"followups": EXPECTED_SUGGESTIONS})

    assert response.suggestions == EXPECTED_SUGGESTIONS
    assert suggestion_block_items(response) == EXPECTED_SUGGESTIONS


def test_explicit_general_suggestions_block_preserves_top_level_suggestions_without_duplication():
    response = normalize_chat_response({
        "intent": "general",
        "answer": "Here is the answer.",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "markdown", "text": "Here is the answer."},
                {
                    "type": "suggestions",
                    "title": "Suggested follow-ups",
                    "items": [
                        "Ask about import documents",
                        "Calculate import tax",
                    ],
                },
            ],
        },
        "suggestions": [
            "Ask about import documents",
            "Calculate import tax",
        ],
    })

    assert response.suggestions == [
        "Ask about import documents",
        "Calculate import tax",
    ]
    assert len(suggestion_blocks(response)) == 1
    assert suggestion_blocks(response)[0].title == "Suggested follow-ups"
    assert suggestion_blocks(response)[0].items == response.suggestions
