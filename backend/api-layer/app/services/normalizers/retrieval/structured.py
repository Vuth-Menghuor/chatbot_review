from typing import Any

from app.schemas.normalized_chat import ChatContentBlock, ReferencesBlock
from app.services.normalizers.retrieval.citations import normalize_retrieval_document_references


# Find retrieval data in direct-service or orchestrator payload shapes.
def first_structured_retrieval_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("retrieval_result", "retrieval_data"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value

    result = payload.get("result")
    if isinstance(result, dict):
        nested = result.get("result")
        if isinstance(nested, dict) and is_retrieval_result(nested):
            return nested
        if is_retrieval_result(result):
            return result

    if is_retrieval_result(payload):
        return payload

    return None


# Detect retrieval structure from source/document keys instead of answer text.
def is_retrieval_result(value: dict[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "documents",
            "chunks",
            "sources",
            "retrieved_documents",
            "retrieval_results",
        )
    )


# Add only retrieval-specific source/reference blocks; markdown, coverage, and citations stay on shared paths.
def normalize_structured_retrieval_blocks(payload: dict[str, Any]) -> list[ChatContentBlock]:
    result = first_structured_retrieval_result(payload)
    if not result:
        return []

    references = normalize_retrieval_document_references(
        result.get("documents")
        or result.get("retrieved_documents")
        or result.get("chunks")
        or result.get("sources")
        or result.get("retrieval_results")
    )
    if not references:
        return []

    return [ReferencesBlock(title="References", items=references)]
