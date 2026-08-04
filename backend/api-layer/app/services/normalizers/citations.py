from __future__ import annotations

import re
from typing import Any

from app.schemas.normalized_chat import Citation


# Citation normalization is shared across retrieval/general responses and calculator citations.
# Keeping it separate avoids mixing source parsing with response block construction.


def normalize_citations(value: Any) -> list[Citation]:
    if not isinstance(value, list):
        return []

    citations: list[Citation] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            citations.append(Citation(id=str(index), label=f"Source {index}", title=item))
            continue
        if not isinstance(item, dict):
            continue

        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        citation_id = (
            item.get("id")
            or item.get("citation_id")
            or item.get("doc_id")
            or item.get("source_id")
            or item.get("reference_id")
            or item.get("document_id")
            or index
        )
        document_id = item.get("document_id") or item.get("documentId") or metadata.get("document_id") or metadata.get("doc_id")
        filename = item.get("filename") or metadata.get("filename") or metadata.get("file_name")
        chunk_index = item.get("chunk_index") or item.get("chunk_idx") or metadata.get("chunk_index") or metadata.get("chunk_idx")
        snippet = item.get("snippet") or item.get("content") or item.get("description")
        title = (
            item.get("title")
            or item.get("source")
            or item.get("section_title")
            or metadata.get("title")
            or metadata.get("source")
            or citation_title_from_snippet(snippet)
            or generated_citation_title(document_id, filename)
            or generated_citation_title(item.get("doc_id") or citation_id, None)
        )
        citations.append(
            Citation(
                id=str(citation_id),
                citation_id=str(citation_id),
                label=item.get("label") or f"Source {index}",
                title=title,
                snippet=snippet,
                url=item.get("url") or item.get("source_url"),
                score=coerce_float(item.get("score")),
                document_id=str(document_id) if document_id else None,
                filename=str(filename) if filename else None,
                chunk_index=coerce_int(chunk_index),
                retrieval_method=item.get("retrieval_method") or item.get("retrievalMethod") or metadata.get("retrieval_method"),
                metadata=metadata,
            )
        )
    return citations


def dedupe_citations(citations: list[Citation]) -> list[Citation]:
    deduped: list[Citation] = []
    seen: set[str] = set()
    for citation in citations:
        key = (
            (citation.url or "").strip().lower()
            or (citation.document_id or "").strip().lower()
            or (citation.title or "").strip().lower()
        )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped


def generated_citation_title(document_id: Any, filename: Any) -> str | None:
    if document_id:
        return f"Document {document_id}"
    if filename:
        return str(filename)
    return None


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
