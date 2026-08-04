import re
from typing import Any

from app.schemas.normalized_chat import Citation
from app.services.normalizers.calculator.formatting import is_calculator_markdown_text, scalar_to_cell


# Extract source lines from legacy calculator text into the existing citation schema.
def calculator_source_citations(content: str, *, start_index: int = 1) -> list[Citation]:
    from app.services.normalizers.calculator.legacy import parse_calculator_text_sections

    if not is_calculator_markdown_text(content):
        return []

    sections = parse_calculator_text_sections(content)
    citations: list[Citation] = []
    for section_name in ("REFERENCES & CITATIONS", "DATA SOURCES"):
        for line in sections.get(section_name, []):
            cleaned = line.strip().lstrip("*+").strip()
            if not cleaned:
                continue
            citations.append(calculator_source_citation(cleaned, start_index + len(citations)))
    return citations


# Convert one legacy calculator source line into a Citation object.
def calculator_source_citation(value: str, index: int) -> Citation:
    url_match = re.search(r"https?://\S+", value)
    document_match = re.search(r"\(([^)]+)\)\s*$", value)
    source_id_match = re.search(r"\(ID:\s*([^)]+)\)", value, flags=re.IGNORECASE)
    effective_match = re.search(r"\bEffective:\s*([^|]+)", value, flags=re.IGNORECASE)
    if source_id_match or url_match:
        title = clean_reference_title(value)
        source_detail = source_id_match.group(1).strip() if source_id_match else ""
        document_id = source_detail or None
    else:
        title, _, source_detail = value.partition(":")
        title = title.strip() or f"Source {index}"
        source_detail = source_detail.strip() or value
        document_id = document_match.group(1).strip() if document_match else None

    source_detail = source_detail.strip() or value

    return Citation(
        id=f"calculator-source-{index}",
        label=f"Source {index}",
        title=title,
        snippet=value,
        url=url_match.group(0).rstrip(".,)") if url_match else None,
        citation_id=source_id_match.group(1).strip() if source_id_match else None,
        document_id=document_id,
        retrieval_method=source_detail.split(" ", 1)[0].strip() or "Calculator",
        metadata={"effective_date": effective_match.group(1).strip().rstrip(".,)") if effective_match else None},
    )


# Convert structured calculator references into lightweight frontend reference items.
def reference_item_from_value(value: Any, index: int) -> dict[str, str | int | float | bool | None]:
    if isinstance(value, dict):
        item = {
            "id": scalar_to_cell(value.get("id") or value.get("doc_id") or index),
            "title": clean_reference_title(
                scalar_to_cell(value.get("title") or value.get("source") or value.get("doc_id") or f"Reference {index}")
                or f"Reference {index}"
            ),
            "url": scalar_to_cell(value.get("url") or value.get("source_url")),
            "effective_date": scalar_to_cell(value.get("effective_start_date")),
            "source_id": scalar_to_cell(value.get("source_id") or value.get("doc_id") or value.get("id")),
        }
        return item
    text = str(value)
    url_match = re.search(r"https?://\S+", text)
    source_id_match = re.search(r"\(ID:\s*([^)]+)\)", text, flags=re.IGNORECASE)
    effective_match = re.search(r"\bEffective:\s*([^|]+)", text, flags=re.IGNORECASE)
    return {
        "id": index,
        "title": clean_reference_title(text),
        "url": url_match.group(0).rstrip(".,)") if url_match else None,
        "effective_date": effective_match.group(1).strip().rstrip(".,)") if effective_match else None,
        "source_id": source_id_match.group(1).strip() if source_id_match else None,
    }


# Deduplicate reference items exactly as the previous monolithic calculator module did.
def dedupe_reference_items(
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


# Strip IDs, URLs, and effective-date suffixes from source titles for cleaner display.
def clean_reference_title(value: str) -> str:
    title = re.sub(r"^\s*\[\d+\]\s*", "", value).strip()
    title = re.sub(r"\s*\|\s*https?://\S+.*$", "", title).strip()
    title = re.sub(r"\s*https?://\S+\s*$", "", title).strip()
    title = re.sub(r"\s*\(ID:\s*[^)]+\)", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s*\|\s*Effective:\s*.*$", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s+-\s+", " — ", title)
    return title or value
