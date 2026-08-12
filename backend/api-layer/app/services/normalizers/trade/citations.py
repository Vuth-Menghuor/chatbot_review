from typing import Any

from app.services.normalizers.tables import scalar_to_cell


# Convert structured trade citations into frontend reference items without changing the global Citation schema.
def normalize_trade_references(value: Any) -> list[dict[str, str | int | float | bool | None]]:
    if not isinstance(value, list):
        return []

    references = [trade_reference_item(item, index) for index, item in enumerate(value, start=1)]
    return dedupe_trade_references(references)


# Normalize one trade reference item from dict or text form.
def trade_reference_item(value: Any, index: int) -> dict[str, str | int | float | bool | None]:
    if isinstance(value, dict):
        return {
            "id": scalar_to_cell(value.get("id") or value.get("source_id") or value.get("doc_id") or index),
            "title": scalar_to_cell(value.get("title") or value.get("source") or value.get("dataset") or f"Reference {index}"),
            "url": scalar_to_cell(value.get("url") or value.get("source_url")),
            "dataset": scalar_to_cell(value.get("dataset")),
            "period": scalar_to_cell(value.get("period")),
            "chunk_index": scalar_to_cell(value.get("chunk_index") or value.get("chunk_idx")),
            "source_id": scalar_to_cell(value.get("source_id") or value.get("doc_id") or value.get("id")),
        }

    return {
        "id": index,
        "title": str(value),
        "url": None,
        "dataset": None,
        "period": None,
        "chunk_index": None,
        "source_id": None,
    }


# Remove duplicate trade references using the same stable identifiers users see in source payloads.
def dedupe_trade_references(
    items: list[dict[str, str | int | float | bool | None]],
) -> list[dict[str, str | int | float | bool | None]]:
    deduped: list[dict[str, str | int | float | bool | None]] = []
    seen_keys: set[str] = set()
    for item in items:
        key = trade_reference_dedupe_key(item)
        if key and key in seen_keys:
            continue
        if key:
            seen_keys.add(key)
        item["id"] = len(deduped) + 1
        deduped.append(item)
    return deduped


def trade_reference_dedupe_key(item: dict[str, str | int | float | bool | None]) -> str:
    url = normalized_reference_value(item.get("url"))
    if url:
        return f"url:{url}"

    source_id = normalized_reference_value(item.get("source_id"))
    if source_id:
        chunk_index = normalized_reference_value(item.get("chunk_index"))
        return f"source:{source_id}:{chunk_index}"

    dataset = normalized_reference_value(item.get("dataset"))
    period = normalized_reference_value(item.get("period"))
    chunk_index = normalized_reference_value(item.get("chunk_index"))
    if dataset or period or chunk_index:
        return f"metadata:{dataset}:{period}:{chunk_index}"

    title = normalized_reference_value(item.get("title"))
    if title:
        return f"title:{title}"

    return ""


def normalized_reference_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
