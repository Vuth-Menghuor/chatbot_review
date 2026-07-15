from typing import Any
from uuid import uuid4

from app.schemas.normalized_chat import (
    ChartBlock,
    ChatContentBlock,
    ChatTableColumn,
    Citation,
    ClarificationBlock,
    ErrorBlock,
    MarkdownBlock,
    NormalizedAssistantMessage,
    NormalizedChatDebug,
    NormalizedChatResponse,
    TableBlock,
)


def normalize_chat_response(raw: Any, *, chat: Any | None = None, include_debug: bool = False) -> NormalizedChatResponse:
    payload = raw if isinstance(raw, dict) else {"answer": str(raw or "")}
    request_id = str(payload.get("request_id") or payload.get("requestId") or uuid4())
    session_id = str(payload.get("session_id") or payload.get("sessionId") or getattr(chat, "id", "") or request_id)
    status = normalize_status(payload.get("status"))
    intent = str(payload.get("intent") or payload.get("route") or "general")

    blocks = build_content_blocks(payload)
    citations = normalize_citations(payload.get("citations") or payload.get("references") or [])
    suggestions = normalize_string_list(payload.get("suggestions"))

    debug = build_debug_info(payload) if include_debug else None

    return NormalizedChatResponse(
        request_id=request_id,
        session_id=session_id,
        status=status,
        intent=intent,
        message=NormalizedAssistantMessage(content=blocks),
        citations=citations,
        suggestions=suggestions,
        debug=debug,
    )


def build_debug_info(payload: dict[str, Any]) -> NormalizedChatDebug:
    return NormalizedChatDebug(
        latency_ms=coerce_float(
            payload.get("latency_ms")
            or payload.get("latencyMs")
            or get_nested(payload, "meta", "latency_ms")
            or get_nested(payload, "metadata", "latency_ms")
        ),
        confidence=normalize_confidence(
            payload.get("confidence")
            or payload.get("candidate_confidence")
            or get_nested(payload, "metadata", "candidate_confidence")
        ),
        answer_source=payload.get("answer_source") or payload.get("source") or get_nested(payload, "metadata", "answer_source"),
        metadata=collect_debug_metadata(payload),
    )


def collect_debug_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    debug_metadata: dict[str, Any] = {}

    for key in ("metadata", "meta"):
        value = payload.get(key)
        if isinstance(value, dict):
            debug_metadata[key] = value

    for key in (
        "candidate_confidence",
        "collection_used",
        "semantic_count",
        "structured_count",
        "total_count",
        "query_strategy",
        "answer_source",
        "api_called",
        "language",
        "required_parameters",
        "missing_parameters",
    ):
        if key in payload:
            debug_metadata[key] = payload[key]

    return debug_metadata


def build_content_blocks(payload: dict[str, Any]) -> list[ChatContentBlock]:
    blocks: list[ChatContentBlock] = []

    answer = first_text(payload, "answer", "final_answer", "message", "content", "human_readable", "summary")
    if answer:
        blocks.append(MarkdownBlock(text=answer))

    for table_value in iter_table_values(payload):
        table_block = normalize_table(table_value)
        if table_block:
            blocks.append(table_block)

    chart_block = normalize_chart(payload.get("visualization"))
    if chart_block:
        blocks.append(chart_block)

    summary_block = normalize_summary_metrics(payload.get("summary_metrics"))
    if summary_block:
        blocks.append(summary_block)

    documents_block = normalize_documents_table(payload.get("documents"))
    if documents_block:
        blocks.append(documents_block)

    line_items_block = normalize_line_items_table(payload.get("line_items"))
    if line_items_block:
        blocks.append(line_items_block)

    clarifications = (
        payload.get("clarifications")
        or payload.get("clarifying_questions")
        or payload.get("clarification_questions")
    )
    clarification_block = normalize_clarification_block(clarifications)
    if clarification_block:
        blocks.append(clarification_block)

    errors = normalize_errors(payload.get("errors") or payload.get("error"))
    if errors:
        blocks.extend(ErrorBlock(message=message) for message in errors)
    elif normalize_status(payload.get("status")) == "failed":
        blocks.append(ErrorBlock(message=first_text(payload, "error", "detail") or "Request failed"))

    if not blocks:
        blocks.append(MarkdownBlock(text=""))

    return blocks


def normalize_status(value: Any) -> str:
    status = str(value or "completed").lower()
    if status in {"completed", "success", "ok", "done"}:
        return "completed"
    if status in {"processing", "pending", "running", "streaming"}:
        return "processing"
    if status in {"failed", "error", "invalid_query"}:
        return "failed"
    return "completed"


def normalize_confidence(value: Any) -> str | None:
    if value is None:
        return None
    confidence = str(value).lower()
    if confidence in {"high", "medium", "low"}:
        return confidence
    if confidence in {"med", "moderate"}:
        return "medium"
    return None


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

        citation_id = (
            item.get("id")
            or item.get("doc_id")
            or item.get("source_id")
            or item.get("reference_id")
            or item.get("document_id")
            or index
        )
        citations.append(
            Citation(
                id=str(citation_id),
                label=item.get("label") or f"Source {index}",
                title=item.get("title") or item.get("source") or item.get("section_title") or item.get("doc_id"),
                snippet=item.get("snippet") or item.get("content") or item.get("description"),
                url=item.get("url") or item.get("source_url"),
                score=coerce_float(item.get("score")),
            )
        )
    return citations


def normalize_table(value: Any) -> TableBlock | None:
    if not isinstance(value, dict):
        return None

    rows = first_list(value, "rows", "data", "records", "items")
    columns = value.get("columns")
    normalized_columns: list[ChatTableColumn] = []

    if isinstance(columns, list):
        for column in columns:
            if isinstance(column, dict):
                key = str(column.get("key") or column.get("field") or column.get("name") or "")
                label = str(column.get("label") or column.get("title") or key)
            else:
                key = str(column)
                label = key
            if key:
                normalized_columns.append(ChatTableColumn(key=key, label=label))

    if not normalized_columns and rows and isinstance(rows[0], dict):
        normalized_columns = [ChatTableColumn(key=str(key), label=str(key).replace("_", " ").title()) for key in rows[0]]

    normalized_rows = [row for row in rows if isinstance(row, dict)]
    if not normalized_columns and not normalized_rows:
        return None

    return TableBlock(title=value.get("title") or value.get("name"), columns=normalized_columns, rows=normalized_rows)


def normalize_chart(value: Any) -> ChartBlock | None:
    if not isinstance(value, dict) or not value:
        return None
    return ChartBlock(title=value.get("title"), data=value)


def normalize_clarification_block(value: Any) -> ClarificationBlock | None:
    questions = normalize_string_list(value)
    if not questions:
        return None
    return ClarificationBlock(title="More information is needed", questions=questions)


def iter_table_values(payload: dict[str, Any]) -> list[Any]:
    values: list[Any] = []
    if "table" in payload:
        values.append(payload.get("table"))
    if isinstance(payload.get("tables"), list):
        values.extend(payload["tables"])
    if isinstance(payload.get("breakdown"), dict):
        rows = [{"component": key, "amount": value} for key, value in payload["breakdown"].items()]
        values.append({"title": "Calculation Breakdown", "rows": rows})
    return values


def normalize_summary_metrics(value: Any) -> TableBlock | None:
    if not isinstance(value, dict) or not value:
        return None
    rows = [{"metric": str(key).replace("_", " ").title(), "value": scalar_to_cell(item)} for key, item in value.items()]
    return TableBlock(
        title="Summary Metrics",
        columns=[
            ChatTableColumn(key="metric", label="Metric"),
            ChatTableColumn(key="value", label="Value"),
        ],
        rows=rows,
    )


def normalize_documents_table(value: Any) -> TableBlock | None:
    if not isinstance(value, list) or not value:
        return None

    rows: list[dict[str, str | int | float | bool | None]] = []
    for item in value[:10]:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        hs_code = metadata.get("hs_code") or metadata.get("code") or item.get("hs_code")
        description = metadata.get("description") or item.get("content") or item.get("description")
        row = {
            "hs_code": scalar_to_cell(hs_code),
            "description": scalar_to_cell(description),
            "score": scalar_to_cell(item.get("score")),
        }
        if any(value is not None for value in row.values()):
            rows.append(row)

    if not rows:
        return None

    return TableBlock(
        title="Possible HS Codes",
        columns=[
            ChatTableColumn(key="hs_code", label="HS Code"),
            ChatTableColumn(key="description", label="Description"),
            ChatTableColumn(key="score", label="Score"),
        ],
        rows=rows,
    )


def normalize_line_items_table(value: Any) -> TableBlock | None:
    if not isinstance(value, list) or not value:
        return None

    rows = []
    for item in value:
        if not isinstance(item, dict):
            continue
        rows.append({
            "name": scalar_to_cell(item.get("name") or item.get("tax_type")),
            "rate": scalar_to_cell(item.get("rate")),
            "base": scalar_to_cell(item.get("base")),
            "amount": scalar_to_cell(item.get("amount")),
            "currency": scalar_to_cell(item.get("currency")),
        })

    if not rows:
        return None

    return TableBlock(
        title="Tax Line Items",
        columns=[
            ChatTableColumn(key="name", label="Name"),
            ChatTableColumn(key="rate", label="Rate"),
            ChatTableColumn(key="base", label="Base"),
            ChatTableColumn(key="amount", label="Amount"),
            ChatTableColumn(key="currency", label="Currency"),
        ],
        rows=rows,
    )


def normalize_errors(value: Any) -> list[str]:
    if isinstance(value, dict):
        message = value.get("message") or value.get("detail") or value.get("code")
        return [str(message)] if message else []
    return normalize_string_list(value)


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        normalized = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("message") or item.get("detail") or item.get("question")
            else:
                text = item
            if str(text).strip():
                normalized.append(str(text))
        return normalized
    return []


def first_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def get_nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def first_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def scalar_to_cell(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
