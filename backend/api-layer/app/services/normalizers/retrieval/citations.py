from typing import Any

from app.services.normalizers.tables import scalar_to_cell


# Convert retrieval document/chunk payloads into lightweight reference block items.
def normalize_retrieval_document_references(value: Any) -> list[dict[str, str | int | float | bool | None]]:
    if not isinstance(value, list):
        return []

    items = [retrieval_reference_item(item, index) for index, item in enumerate(value, start=1)]
    items = [item for item in items if has_reference_identity(item)]
    return dedupe_retrieval_references(items)


# Normalize one retrieval document or source item from dict or text form.
def retrieval_reference_item(value: Any, index: int) -> dict[str, str | int | float | bool | None]:
    if isinstance(value, dict):
        metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
        title = (
            value.get("title")
            or value.get("source")
            or value.get("filename")
            or metadata.get("title")
            or metadata.get("source")
            or metadata.get("filename")
            or metadata.get("file_name")
            or value.get("document_id")
            or value.get("doc_id")
            or f"Reference {index}"
        )
        return {
            "id": scalar_to_cell(value.get("id") or value.get("document_id") or value.get("doc_id") or index),
            "title": scalar_to_cell(title),
            "url": scalar_to_cell(value.get("url") or value.get("source_url") or metadata.get("url") or metadata.get("source_url")),
            "snippet": scalar_to_cell(value.get("snippet") or value.get("content") or value.get("text")),
            "score": scalar_to_cell(value.get("score")),
            "document_id": scalar_to_cell(value.get("document_id") or value.get("doc_id") or metadata.get("document_id") or metadata.get("doc_id")),
            "filename": scalar_to_cell(value.get("filename") or metadata.get("filename") or metadata.get("file_name")),
            "chunk_index": scalar_to_cell(value.get("chunk_index") or value.get("chunk_idx") or metadata.get("chunk_index") or metadata.get("chunk_idx")),
            "source_id": scalar_to_cell(value.get("source_id") or value.get("document_id") or value.get("doc_id") or value.get("id")),
        }

    text = str(value).strip()
    return {
        "id": index,
        "title": text or f"Reference {index}",
        "url": None,
        "snippet": text or None,
        "score": None,
        "document_id": None,
        "filename": None,
        "chunk_index": None,
        "source_id": None,
    }


# Keep empty/malformed source items out of reference blocks.
def has_reference_identity(item: dict[str, str | int | float | bool | None]) -> bool:
    return any(item.get(key) for key in ("title", "url", "snippet", "document_id", "filename", "source_id"))


# Deduplicate retrieval references by stable source identifiers.
def dedupe_retrieval_references(
    items: list[dict[str, str | int | float | bool | None]],
) -> list[dict[str, str | int | float | bool | None]]:
    deduped: list[dict[str, str | int | float | bool | None]] = []
    seen_source_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for item in items:
        source_id = str(item.get("source_id") or item.get("document_id") or "").strip().lower()
        url = str(item.get("url") or "").strip().lower()
        title = str(item.get("title") or "").strip().lower()
        if (source_id and source_id in seen_source_ids) or (url and url in seen_urls) or (title and title in seen_titles):
            continue
        if source_id:
            seen_source_ids.add(source_id)
        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
        item["id"] = len(deduped) + 1
        deduped.append(item)
    return deduped
