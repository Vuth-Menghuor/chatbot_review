from typing import Any
from uuid import uuid4

from app.schemas.normalized_chat import (
    ChartBlock,
    ChatContentBlock,
    ChatTableColumn,
    Citation,
    ClarificationBlock,
    CoverageBlock,
    ErrorBlock,
    MarkdownBlock,
    NormalizedAssistantMessage,
    NormalizedChatDebug,
    NormalizedChatResponse,
    NormalizedResponseBody,
    ResponseLimitation,
    SuggestionsBlock,
    TableBlock,
)


def normalize_chat_response(raw: Any, *, chat: Any | None = None, include_debug: bool = False) -> NormalizedChatResponse:
    payload = raw if isinstance(raw, dict) else {"answer": str(raw or "")}
    request_id = str(payload.get("request_id") or payload.get("requestId") or uuid4())
    session_id = normalize_session_id(payload.get("session_id") or payload.get("sessionId"), chat=chat, fallback=request_id)
    status = normalize_status(payload.get("status"))
    intent = str(payload.get("intent") or payload.get("route") or "general")
    response_body = build_response_body(payload)
    assert_orchestrator_answer_unchanged(payload, response_body)
    coverage = response_body.coverage
    confidence = response_body.confidence

    blocks = build_content_blocks(payload, response_body=response_body)
    if status != "failed":
        assert_response_content_matches_first_markdown(response_body, blocks)
    citations = normalize_citations(payload.get("citations") or payload.get("references") or [])
    suggestions = normalize_string_list(payload.get("suggestions"))
    metrics = normalize_metrics(payload)

    debug = build_debug_info(payload) if include_debug else None

    return NormalizedChatResponse(
        request_id=request_id,
        session_id=session_id,
        chat_id=str(getattr(chat, "id", "")) if getattr(chat, "id", None) else None,
        project_id=str(getattr(chat, "project_id", "")) if getattr(chat, "project_id", None) else None,
        status=status,
        intent=intent,
        query=first_text(payload, "query", "question", "input"),
        language=first_text(payload, "language", "lang") or get_nested(payload, "metadata", "language"),
        coverage=coverage,
        confidence=confidence,
        response=response_body,
        message=NormalizedAssistantMessage(content=blocks),
        citations=citations,
        suggestions=suggestions,
        metrics=metrics,
        debug=debug,
    )


def build_debug_info(payload: dict[str, Any]) -> NormalizedChatDebug:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
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
        answer_source=payload.get("answer_source") or payload.get("source") or metadata.get("answer_source"),
        semantic_count=coerce_int(first_present(payload.get("semantic_count"), metadata.get("semantic_count"))),
        structured_count=coerce_int(first_present(payload.get("structured_count"), metadata.get("structured_count"))),
        total_count=coerce_int(first_present(payload.get("total_count"), metadata.get("total_count"))),
        query_strategy=first_present(payload.get("query_strategy"), metadata.get("query_strategy")),
        metadata=collect_debug_metadata(payload),
    )


def collect_debug_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    debug_metadata: dict[str, Any] = {}

    for key in ("metadata", "meta"):
        value = payload.get(key)
        if isinstance(value, dict):
            debug_metadata.update(value)

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


def build_response_body(payload: dict[str, Any]) -> NormalizedResponseBody:
    response_value = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    answer_value = payload.get("answer") if isinstance(payload.get("answer"), dict) else {}
    source = response_value or answer_value

    if isinstance(payload.get("answer"), str):
        summary = None
        content = payload["answer"]
    else:
        summary = first_text(source, "summary", "overview", "direct_answer") if isinstance(source, dict) else None
        content = (
            first_text(source, "content", "markdown", "text") if isinstance(source, dict) else None
        ) or first_text(payload, "answer", "final_answer", "message", "content", "human_readable", "summary") or summary or ""
    source_limitations = source.get("limitations") if isinstance(source, dict) else None
    source_missing = source.get("missing") if isinstance(source, dict) else None
    limitations = normalize_limitations(source_limitations or payload.get("limitations") or source_missing)
    coverage = normalize_coverage(
        (source.get("coverage") if isinstance(source, dict) else None)
        or payload.get("coverage")
        or payload.get("answer_coverage")
    )
    confidence = normalize_confidence(
        (source.get("confidence") if isinstance(source, dict) else None)
        or payload.get("confidence")
        or payload.get("candidate_confidence")
        or get_nested(payload, "metadata", "candidate_confidence")
    )

    return NormalizedResponseBody(
        type=get_response_type(payload),
        coverage=coverage,
        confidence=confidence,
        summary=summary,
        content=content,
        limitations=limitations,
    )


def assert_orchestrator_answer_unchanged(payload: dict[str, Any], response_body: NormalizedResponseBody) -> None:
    answer = payload.get("answer")
    if not isinstance(answer, str):
        return
    if response_body.content != answer:
        raise ValueError("Normalized content must match orchestrator answer")


def build_content_blocks(payload: dict[str, Any], *, response_body: NormalizedResponseBody) -> list[ChatContentBlock]:
    blocks: list[ChatContentBlock] = []

    if response_body.content:
        blocks.append(MarkdownBlock(text=response_body.content))

    found_items = normalize_response_items(payload, "found", "available", "known")
    if found_items:
        blocks.append(CoverageBlock(title="What was found", tone="info", items=found_items))

    limitation_messages = [limitation.message for limitation in response_body.limitations]
    missing_items = normalize_response_items(payload, "missing", "not_found", "unavailable")
    if limitation_messages or missing_items:
        blocks.append(
            CoverageBlock(
                title="Information limitation",
                tone="warning",
                items=limitation_messages or missing_items,
                note="The available sources do not provide a complete answer for every requested detail.",
            )
        )

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

    suggestions = normalize_string_list(payload.get("suggestions"))
    if suggestions:
        blocks.append(SuggestionsBlock(title="Suggested follow-ups", items=suggestions))

    if not blocks:
        blocks.append(MarkdownBlock(text=""))

    return blocks


def assert_response_content_matches_first_markdown(
    response_body: NormalizedResponseBody,
    blocks: list[ChatContentBlock],
) -> None:
    first_markdown = next((block for block in blocks if isinstance(block, MarkdownBlock)), None)
    if first_markdown is None:
        raise ValueError("Normalized message must include a markdown block for response content")
    if first_markdown.text != response_body.content:
        raise ValueError("Normalized message markdown text must match response content")


def normalize_status(value: Any) -> str:
    status = str(value or "completed").lower()
    if status in {"completed", "success", "ok", "done", "partial_answer", "partial"}:
        return "completed"
    if status in {"processing", "pending", "running", "streaming"}:
        return "processing"
    if status in {"failed", "error", "invalid_query"}:
        return "failed"
    return "completed"


def normalize_coverage(value: Any, *, limitations: list[ResponseLimitation] | None = None) -> str:
    coverage = str(value or "").lower()
    if coverage in {"complete", "full", "high"}:
        return "complete"
    if coverage in {"partial", "partial_answer", "limited", "incomplete"}:
        return "partial"
    return "unknown"


def get_response_type(payload: dict[str, Any]) -> str:
    if payload.get("table"):
        return "table"
    if payload.get("visualization"):
        return "chart"
    return "markdown"


def normalize_confidence(value: Any) -> str | None:
    if value is None:
        return None
    confidence = str(value).lower()
    if confidence in {"high", "medium", "low"}:
        return confidence
    if confidence in {"med", "moderate"}:
        return "medium"
    return None


def normalize_limitations(value: Any) -> list[ResponseLimitation]:
    limitations: list[ResponseLimitation] = []
    for index, item in enumerate(normalize_list_items(value), start=1):
        if isinstance(item, dict):
            message = item.get("message") or item.get("detail") or item.get("text")
            if message:
                limitations.append(ResponseLimitation(code=item.get("code") or f"LIMITATION_{index}", message=str(message)))
        elif str(item).strip():
            limitations.append(ResponseLimitation(message=str(item)))
    return limitations


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
    title = value.get("title")
    return ChartBlock(title=title, data=normalize_chart_data(value, title=title))


def normalize_chart_data(value: dict[str, Any], *, title: Any = None) -> dict[str, Any]:
    chart_type = normalize_chart_type(value.get("type") or value.get("chartType"))
    chart_title = title or value.get("title")

    labels = value.get("labels")
    datasets = value.get("datasets")
    if isinstance(labels, list) and isinstance(datasets, list):
        normalized_labels = [str(label) for label in labels]
        normalized_datasets = [dataset for dataset in datasets if isinstance(dataset, dict)]
        render_type = "bar" if chart_type == "line" and len(normalized_labels) < 2 else chart_type
        rows: list[dict[str, str | int | float | bool | None]] = []

        for index, label in enumerate(normalized_labels):
            row: dict[str, str | int | float | bool | None] = {"label": label}
            for dataset_index, dataset in enumerate(normalized_datasets):
                key = chart_series_key(dataset, dataset_index)
                data_values = dataset.get("data") if isinstance(dataset.get("data"), list) else []
                value_at_index = data_values[index] if index < len(data_values) else 0
                row[key] = numeric_cell(value_at_index)
            rows.append(row)

        return {
            "title": scalar_to_cell(chart_title),
            "chartType": render_type,
            "xKey": "label",
            "xLabel": "Label",
            "yLabel": scalar_to_cell(normalized_datasets[0].get("label")) if normalized_datasets else None,
            "data": rows,
            "series": [
                {
                    "key": chart_series_key(dataset, index),
                    "name": str(dataset.get("label") or f"Series {index + 1}"),
                    "color": chart_color(index),
                    "type": "line" if render_type == "line" else "bar",
                }
                for index, dataset in enumerate(normalized_datasets)
            ],
        }

    normalized = dict(value)
    normalized["title"] = scalar_to_cell(chart_title)
    normalized["chartType"] = chart_type
    normalized.pop("type", None)
    return normalized


def normalize_chart_type(value: Any) -> str:
    chart_type = str(value or "bar").lower()
    if chart_type == "horizontalbar":
        return "horizontal-bar"
    if chart_type == "doughnut":
        return "donut"
    return chart_type


def chart_series_key(dataset: dict[str, Any], index: int) -> str:
    import re

    label = str(dataset.get("label") or f"series_{index + 1}").strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", label).strip("_")
    return key or f"series_{index + 1}"


def chart_color(index: int) -> str:
    colors = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2"]
    return colors[index % len(colors)]


def numeric_cell(value: Any) -> int | float:
    if isinstance(value, int | float):
        return value
    try:
        return float(str(value or 0))
    except (TypeError, ValueError):
        return 0


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
    rows = [{"metric": str(key).replace("_", " ").title(), "value": summary_metric_cell(item)} for key, item in value.items()]
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


def normalize_list_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]


def normalize_response_items(payload: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for container in (payload.get("response"), payload.get("answer"), payload):
        if not isinstance(container, dict):
            continue
        for key in keys:
            values.extend(normalize_string_list(container.get(key)))
    return list(dict.fromkeys(values))


def normalize_session_id(value: Any, *, chat: Any | None, fallback: str) -> str:
    session_id = str(value or "").strip()
    if not session_id or "{{" in session_id or "}}" in session_id:
        session_id = str(getattr(chat, "id", "") or fallback)
    return session_id


def normalize_metrics(payload: dict[str, Any]) -> dict[str, float | int | str | bool | None]:
    metrics_source = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    metrics: dict[str, float | int | str | bool | None] = {}

    metric_map = {
        "latency_ms": first_present(payload.get("latency_ms"), payload.get("latencyMs"), metrics_source.get("latency_ms")),
        "semantic_candidate_count": first_present(payload.get("semantic_candidate_count"), payload.get("semantic_count"), metrics_source.get("semantic_candidate_count")),
        "selected_document_count": first_present(payload.get("selected_document_count"), payload.get("total_count"), metrics_source.get("selected_document_count")),
        "structured_result_count": first_present(payload.get("structured_result_count"), payload.get("structured_count"), metrics_source.get("structured_result_count")),
        "retrieved_count": first_present(payload.get("retrieved_count"), metrics_source.get("retrieved_count")),
    }
    for key, value in metric_map.items():
        normalized = scalar_to_cell(value)
        if normalized is not None:
            metrics[key] = normalized
    return metrics


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
    import re

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
    import re

    title = re.sub(r"^\s*(appendix|annex)\s+[a-z0-9]+\.?\s*", "", value, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" .:-")
    title = title.replace("The Law and Regulation relating to", "Laws and Regulations Relating to")
    return title[:120] if title else value.strip()[:120]


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


def first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


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


def summary_metric_cell(value: Any) -> str | int | float | bool | None:
    if isinstance(value, dict):
        note = value.get("truncation_note") or value.get("period_coverage_note")
        if note:
            return str(note)

        parts = []
        for key, item in value.items():
            if item is None:
                continue
            label = str(key).replace("_", " ").title()
            parts.append(f"{label}: {item}")
        return "; ".join(parts) if parts else None
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return scalar_to_cell(value)


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
