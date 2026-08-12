from app.services.chat_response_normalizer import normalize_chat_response


def clarification_blocks(response):
    return [block for block in response.message.content if block.type == "clarification"]


def normalize(clarifications):
    return normalize_chat_response({
        "intent": "general",
        "answer": "I need a little more information.",
        "clarifications": clarifications,
    })


def test_empty_clarification_list_does_not_create_block():
    response = normalize([])

    assert clarification_blocks(response) == []


def test_string_clarification_creates_stable_block():
    response = normalize("What product are you importing?")

    blocks = clarification_blocks(response)

    assert len(blocks) == 1
    assert blocks[0].title == "More information is needed"
    assert blocks[0].questions == ["What product are you importing?"]
    assert response.clarifications == ["What product are you importing?"]


def test_list_of_clarification_strings_creates_stable_block():
    response = normalize([
        "What product are you importing?",
        "Which country is the product coming from?",
    ])

    blocks = clarification_blocks(response)

    assert blocks[0].title == "More information is needed"
    assert blocks[0].questions == [
        "What product are you importing?",
        "Which country is the product coming from?",
    ]
    assert response.clarifications == [
        "What product are you importing?",
        "Which country is the product coming from?",
    ]


def test_general_clarifying_questions_without_answer_render_clarification_not_markdown_only():
    response = normalize_chat_response({
        "request_id": "req-general-clarify",
        "session_id": "session-general-clarify",
        "intent": "general",
        "status": "completed",
        "clarifying_questions": [
            "Are you asking about import or export?",
        ],
    })

    assert response.service == "general"
    assert response.response.content == ""
    assert [block.type for block in response.message.content] == ["clarification"]
    assert response.message.content[0].title == "More information is needed"
    assert response.message.content[0].questions == [
        "Are you asking about import or export?",
    ]
    assert response.clarifications == [
        "Are you asking about import or export?",
    ]


def test_structured_clarification_objects_are_normalized():
    response = normalize([
        {"question": "What product are you importing?"},
        {"message": "Which country is the product coming from?"},
        {"detail": "Is this for import or export?"},
    ])

    assert clarification_blocks(response)[0].questions == [
        "What product are you importing?",
        "Which country is the product coming from?",
        "Is this for import or export?",
    ]


def test_structured_clarification_wrapper_is_normalized():
    response = normalize({
        "questions": [
            {"question": "What product are you importing?"},
            "Which country is the product coming from?",
        ]
    })

    assert clarification_blocks(response)[0].questions == [
        "What product are you importing?",
        "Which country is the product coming from?",
    ]


def test_malformed_clarification_data_does_not_create_block():
    response = normalize({"unexpected": {"nested": object()}})

    assert clarification_blocks(response) == []
