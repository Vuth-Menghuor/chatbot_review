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
            "source_id": scalar_to_cell(value.get("source_id") or value.get("doc_id") or value.get("id")),
        }

    return {
        "id": index,
        "title": str(value),
        "url": None,
        "dataset": None,
        "period": None,
        "source_id": None,
    }


# Remove duplicate trade references using the same stable identifiers users see in source payloads.
def dedupe_trade_references(
    items: list[dict[str, str | int | float | bool | None]],
) -> list[dict[str, str | int | float | bool | None]]:
    deduped: list[dict[str, str | int | float | bool | None]] = []
    seen_source_ids: set[str] = set()
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for item in items:
        source_id = str(item.get("source_id") or "").strip().lower()
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
