from app.services.chat_response_normalizer import normalize_chat_response


def normalize(citations: list[object]):
    return normalize_chat_response({
        "intent": "general",
        "answer": "Citation contract answer.",
        "citations": citations,
    }).citations


def block_types(response):
    return [block.type for block in response.message.content]


def test_citations_use_stable_frontend_shape_and_supported_id_fields():
    citations = normalize([
        {
            "doc_id": "1021",
            "metadata": {"document_title": "Conditions for Import or Export"},
            "snippet": "Useful customs reference.",
            "score": "0.9788",
        },
        {
            "citation_id": "cite-2",
            "document_id": "doc-2",
            "filename": "declaration-guide.pdf",
            "snippet": "Declaration guidance.",
        },
        {
            "source_id": "source-3",
            "title": "Source ID Customs Reference",
            "snippet": "Source ID guidance.",
        },
        {
            "citation_id": "cite-4",
            "title": "Citation ID Customs Reference",
            "snippet": "Citation ID guidance.",
        },
        {
            "id": "explicit-5",
            "title": "Explicit ID Customs Reference",
            "snippet": "Explicit ID guidance.",
        },
    ])

    assert citations[0].id == "1021"
    assert citations[0].marker == 1
    assert citations[0].label == "Source 1"
    assert citations[0].title == "Conditions for Import or Export"
    assert citations[0].score == 0.9788
    assert citations[0].document_id == "1021"
    assert citations[0].metadata == {"document_title": "Conditions for Import or Export"}
    assert citations[1].id == "doc-2"
    assert citations[1].citation_id == "cite-2"
    assert citations[1].document_id == "doc-2"
    assert citations[2].id == "source-3"
    assert citations[2].document_id == "source-3"
    assert citations[2].title == "Source ID Customs Reference"
    assert citations[3].id == "cite-4"
    assert citations[3].citation_id == "cite-4"
    assert citations[3].document_id is None
    assert citations[4].id == "explicit-5"
    assert citations[4].document_id is None


def test_citation_title_fallback_order_avoids_uuid_titles():
    citations = normalize([
        {
            "id": "5f18a715-1470-42d1-b455-29f93abc7bb5",
            "title": "5f18a715-1470-42d1-b455-29f93abc7bb5",
            "metadata": {"filename": "customs-reference.pdf"},
            "snippet": "# Conditions for Import or Export\n\nSnippet text.",
        },
        {
            "document_id": "doc-no-title",
            "snippet": "Plain text without a heading.",
        },
    ])

    assert citations[0].id == "5f18a715-1470-42d1-b455-29f93abc7bb5"
    assert citations[0].title == "customs-reference.pdf"
    assert citations[1].title == "Customs reference"


def test_citation_title_uses_safe_fallback_order():
    citations = normalize([
        {
            "document_id": "doc-title",
            "title": "Explicit Title",
            "metadata": {
                "document_title": "Metadata Document Title",
                "filename": "metadata-file.pdf",
            },
            "filename": "top-level-file.pdf",
            "snippet": "# Snippet Heading\n\nSnippet text.",
        },
        {
            "document_id": "doc-metadata-title",
            "metadata": {
                "document_title": "Metadata Document Title",
                "filename": "metadata-file.pdf",
            },
            "filename": "top-level-file.pdf",
            "snippet": "# Snippet Heading\n\nSnippet text.",
        },
        {
            "document_id": "doc-metadata-filename",
            "metadata": {"filename": "metadata-file.pdf"},
            "filename": "top-level-file.pdf",
            "snippet": "# Snippet Heading\n\nSnippet text.",
        },
        {
            "document_id": "doc-filename",
            "filename": "top-level-file.pdf",
            "snippet": "# Snippet Heading\n\nSnippet text.",
        },
        {
            "document_id": "doc-heading",
            "snippet": "# Snippet Heading\n\nSnippet text.",
        },
    ])

    assert [citation.title for citation in citations] == [
        "Explicit Title",
        "Metadata Document Title",
        "metadata-file.pdf",
        "top-level-file.pdf",
        "Snippet Heading",
    ]


def test_citations_dedupe_by_url_first():
    citations = normalize([
        {"id": "doc-1", "url": "https://example.test/reference", "snippet": "A"},
        {"id": "doc-2", "url": "https://example.test/reference", "snippet": "B"},
    ])

    assert len(citations) == 1
    assert citations[0].id == "doc-1"


def test_citations_dedupe_by_document_id_but_keep_different_chunks():
    citations = normalize([
        {"document_id": "1021", "chunk_index": 1, "title": "Same Title", "snippet": "Chunk one."},
        {"document_id": "1021", "chunk_index": 1, "title": "Same Title", "snippet": "Chunk one duplicate."},
        {"document_id": "1021", "chunk_index": 2, "title": "Same Title", "snippet": "Chunk two."},
    ])

    assert len(citations) == 2
    assert [citation.marker for citation in citations] == [1, 2]
    assert [citation.chunk_index for citation in citations] == [1, 2]


def test_citations_do_not_dedupe_different_snippets_with_same_title_without_ids():
    citations = normalize([
        {"title": "Same Title", "snippet": "First useful chunk."},
        {"title": "Same Title", "snippet": "Second useful chunk."},
        {"title": "Same Title", "snippet": "First useful chunk."},
    ])

    assert len(citations) == 2
    assert [citation.label for citation in citations] == ["Source 1", "Source 2"]
    assert [citation.snippet for citation in citations] == ["First useful chunk.", "Second useful chunk."]


def test_answer_document_markers_are_preserved_without_rewriting_links():
    answer = "You can import the goods if the required documents are complete (Document 1). Review restrictions separately (Document 4)."

    response = normalize_chat_response({
        "intent": "general",
        "answer": answer,
        "citations": [
            {"document_id": "1021", "title": "Conditions for Import or Export"},
            {"document_id": "2044", "title": "Restricted Goods"},
        ],
    })

    assert response.response.content == answer
    assert response.message.content[0].text == answer
    assert "(Document 1)" in response.message.content[0].text
    assert "](Document 1)" not in response.message.content[0].text
    assert response.citations[0].marker == 1


def test_general_string_citations_normalize_top_level_without_references_block_or_inline_rewrite():
    answer = "Follow the import document checklist exactly as provided by the service (Document 1)."

    response = normalize_chat_response({
        "intent": "general",
        "answer": answer,
        "citations": ["Customs Tariff 2022"],
    })

    assert response.response.content == answer
    assert response.message.content[0].text == answer
    assert block_types(response) == ["markdown"]
    assert "references" not in block_types(response)
    assert len(response.citations) == 1
    assert response.citations[0].title == "Customs Tariff 2022"
    assert response.citations[0].label == "Source 1"
    assert "(Document 1)" in response.message.content[0].text


def test_empty_string_citations_are_ignored():
    citations = normalize(["", "   ", "GDCE Public Guidance"])

    assert len(citations) == 1
    assert citations[0].title == "GDCE Public Guidance"


def test_malformed_citation_values_are_ignored_or_safely_defaulted():
    citations = normalize([
        None,
        123,
        "",
        {"document_id": {"bad": "value"}, "metadata": "not-a-dict"},
        {"document_id": "4769", "title": "Customs reference"},
        {"doc_id": "4770", "snippet": "# Cotton Fabric Guidance\n\nUseful source text."},
    ])

    assert len(citations) == 3
    assert citations[0].title == "Customs reference"
    assert citations[0].document_id is None
    assert citations[1].document_id == "4769"
    assert citations[1].title == "Customs reference"
    assert citations[2].document_id == "4770"
    assert citations[2].title == "Cotton Fabric Guidance"


def test_citation_metadata_exposes_only_public_safe_fields():
    citations = normalize([
        {
            "document_id": "4769",
            "title": "Customs reference",
            "metadata": {
                "document_title": "Customs reference",
                "filename": "customs.pdf",
                "page": 4,
                "rewritten_query": "internal expanded query",
                "retrieval_strategy": "hybrid_debug",
                "service_route": "retrieval",
                "provider": "internal-provider",
                "validation": {"debug": True},
                "internal_url": "http://retrieval.internal/query",
                "api_key": "secret",
                "stack_trace": "Traceback...",
            },
        },
    ])

    assert citations[0].metadata == {
        "document_title": "Customs reference",
        "filename": "customs.pdf",
        "page": 4,
    }
