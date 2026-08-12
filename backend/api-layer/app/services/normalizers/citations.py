from __future__ import annotations

import re
from uuid import UUID
from typing import Any

from app.schemas.normalized_chat import Citation


# Citation normalization is shared across retrieval/general responses and calculator citations.
# Keeping it separate avoids mixing source parsing with response block construction.

PUBLIC_CITATION_METADATA_KEYS = {
    "document_title",
    "filename",
    "file_name",
    "page",
    "page_number",
    "section",
    "heading",
    "language",
    "published_at",
    "effective_date",
}


def normalize_citations(value: Any) -> list[Citation]:
    if not isinstance(value, list):
        return []

    citations: list[Citation] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            title = item.strip()
            if title:
                citations.append(Citation(id=str(index), label=f"Source {index}", title=title))
            continue
        if not isinstance(item, dict):
            continue

        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        public_metadata = public_citation_metadata(metadata)
        explicit_citation_id = first_scalar_value(item, "citation_id", "citationId")
        document_id = first_scalar_value(
            item,
            "document_id",
            "documentId",
            "doc_id",
            "docId",
            "source_id",
            "sourceId",
        ) or first_scalar_value(
            metadata,
            "document_id",
            "documentId",
            "doc_id",
            "docId",
            "source_id",
            "sourceId",
        )
        citation_id = (
            first_scalar_value(
                item,
                "id",
                "doc_id",
                "docId",
                "document_id",
                "documentId",
                "citation_id",
                "citationId",
                "source_id",
                "sourceId",
            )
            or first_scalar_value(
                metadata,
                "id",
                "doc_id",
                "docId",
                "document_id",
                "documentId",
                "citation_id",
                "citationId",
                "source_id",
                "sourceId",
            )
            or index
        )
        filename = item.get("filename") or metadata.get("filename") or metadata.get("file_name")
        chunk_index = item.get("chunk_index") or item.get("chunk_idx") or metadata.get("chunk_index") or metadata.get("chunk_idx")
        snippet = item.get("snippet") or item.get("content") or item.get("description")
        title = citation_title(item, metadata, snippet)
        citations.append(
            Citation(
                id=str(citation_id),
                marker=index,
                citation_id=str(explicit_citation_id) if explicit_citation_id else None,
                label=item.get("label") or f"Source {index}",
                title=title,
                snippet=snippet,
                url=item.get("url") or item.get("source_url"),
                score=coerce_float(item.get("score")),
                document_id=str(document_id) if document_id else None,
                filename=str(filename) if filename else None,
                chunk_index=coerce_int(chunk_index),
                retrieval_method=item.get("retrieval_method") or item.get("retrievalMethod") or metadata.get("retrieval_method"),
                metadata=public_metadata,
            )
        )
    return citations


def dedupe_citations(citations: list[Citation]) -> list[Citation]:
    deduped: list[Citation] = []
    seen: set[str] = set()
    for citation in citations:
        key = citation_dedupe_key(citation)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    for index, citation in enumerate(deduped, start=1):
        citation.marker = index
        citation.label = citation.label or f"Source {index}"
    return deduped


def citation_dedupe_key(citation: Citation) -> str:
    if citation.url:
        return f"url:{citation.url.strip().lower()}"
    if citation.document_id:
        chunk = citation.chunk_index if citation.chunk_index is not None else ""
        return f"document:{citation.document_id.strip().lower()}:{chunk}"
    if citation.citation_id:
        return f"citation:{citation.citation_id.strip().lower()}"
    return f"title-snippet:{(citation.title or '').strip().lower()}:{(citation.snippet or '').strip().lower()}"


def first_scalar_value(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (str, int, float, bool)):
            return value
    return None


def public_citation_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    public_metadata: dict[str, Any] = {}
    for key, value in metadata.items():
        normalized_key = str(key)
        if normalized_key.lower() not in PUBLIC_CITATION_METADATA_KEYS:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            public_metadata[normalized_key] = value
    return public_metadata


def citation_title(item: dict[str, Any], metadata: dict[str, Any], snippet: Any) -> str:
    for value in (
        item.get("title"),
        metadata.get("document_title"),
        metadata.get("filename"),
        item.get("filename"),
    ):
        title = clean_title_value(value)
        if title:
            return title
    return citation_title_from_snippet(snippet) or "Customs reference"


def clean_title_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    title = value.strip()
    if not title or is_uuid_like(title):
        return None
    return title


def is_uuid_like(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def citation_title_from_snippet(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    heading = first_markdown_heading(value)
    if heading:
        return clean_citation_title(heading)

    table_title = table_citation_title(value)
    if table_title:
        return table_title

    return None


def first_markdown_heading(value: str) -> str | None:
    for line in value.splitlines():
        match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
        if match:
            return match.group(1)
    return None


def table_citation_title(value: str) -> str | None:
    lowered = value.lower()
    if "|" not in value:
        return None
    if "type of declaration" in lowered or "sad" in lowered or "field label" in lowered:
        return "SAD Import Declaration Requirements"
    return "Table Reference"


def clean_citation_title(value: str) -> str:
    title = re.sub(r"^\s*(appendix|annex)\s+[a-z0-9]+\.?\s*", "", value, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" .:-")
    title = title.replace("The Law and Regulation relating to", "Laws and Regulations Relating to")
    return title[:120] if title else value.strip()[:120]


def coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
