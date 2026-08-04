from typing import Any
from uuid import uuid4

from app.schemas.normalized_chat import (
    ChatContentBlock,
    ClarificationBlock,
    CoverageBlock,
    DetailsBlock,
    DetailsItem,
    ErrorBlock,
    KeyValueBlock,
    KeyValueItem,
    MarkdownBlock,
    NormalizedAssistantMessage,
    NormalizedChatDebug,
    NormalizedChatResponse,
    NormalizedResponseBody,
    ReferencesBlock,
    ResponseLimitation,
    SummaryBlock,
    SuggestionsBlock,
    TableBlock,
)
from app.services.normalizers.calculator import (
    calculator_source_citations,
    extract_final_tax_breakdown_table,
    format_calculator_markdown,
    normalize_markdown_content_blocks,
    normalize_structured_calculator_blocks,
)
from app.services.normalizers.calculator.normalizer import CalculatorNormalizer
from app.services.normalizers.charts import normalize_chart
from app.services.normalizers.citations import dedupe_citations, normalize_citations
from app.services.normalizers.fallback import FallbackNormalizer
from app.services.normalizers.metrics import normalize_summary_metrics
from app.services.normalizers.registry import NormalizerRegistry
from app.services.normalizers.retrieval import RetrievalNormalizer, normalize_structured_retrieval_blocks
from app.services.normalizers.tables import (
    iter_table_values,
    normalize_documents_table,
    normalize_line_items_table,
    normalize_table,
    scalar_to_cell,
)
from app.services.normalizers.trade import TradeNormalizer, normalize_structured_trade_blocks

normalizer_registry = NormalizerRegistry(
    normalizers=[
        CalculatorNormalizer(),
        TradeNormalizer(),
        RetrievalNormalizer(),
    ],
    fallback=FallbackNormalizer(),
)


def normalize_chat_response(raw: Any, *, chat: Any | None = None, include_debug: bool = False) -> NormalizedChatResponse:
    payload = raw if isinstance(raw, dict) else {"answer": str(raw or "")}
    request_id = str(payload.get("request_id") or payload.get("requestId") or uuid4())
    session_id = normalize_session_id(payload.get("session_id") or payload.get("sessionId"), chat=chat, fallback=request_id)
    status = normalize_status(payload.get("status"))
    service = normalizer_registry.normalize(payload)
    intent = str(payload.get("intent") or payload.get("route") or "general")
    response_body = build_response_body(payload)
    assert_orchestrator_answer_unchanged(payload, response_body)
    coverage = response_body.coverage
    confidence = response_body.confidence

    blocks = build_content_blocks(payload, response_body=response_body)
    if status != "failed":
        assert_response_content_matches_first_markdown(response_body, blocks)
    citations = normalize_citations(payload.get("citations") or payload.get("references") or [])
    citations = dedupe_citations(citations + calculator_source_citations(response_body.content, start_index=len(citations) + 1))
    suggestions = normalize_string_list(payload.get("suggestions"))
    metrics = normalize_metrics(payload)

    debug = build_debug_info(payload) if include_debug else None

    return NormalizedChatResponse(
        request_id=request_id,
        session_id=session_id,
        chat_id=str(getattr(chat, "id", "")) if getattr(chat, "id", None) else None,
        project_id=str(getattr(chat, "project_id", "")) if getattr(chat, "project_id", None) else None,
        status=status,
        service=service,
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
        structured_blocks = normalize_structured_calculator_blocks(payload, response_body.content)
        blocks.extend(structured_blocks or normalize_markdown_content_blocks(response_body.content))

    blocks.extend(normalize_structured_trade_blocks(payload))
    blocks.extend(normalize_structured_retrieval_blocks(payload))

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
    if not response_body.content:
        return
    if any(isinstance(block, (SummaryBlock, KeyValueBlock, DetailsBlock, ReferencesBlock)) for block in blocks):
        return
    if any(isinstance(block, TableBlock) for block in blocks):
        return
    if format_calculator_markdown(response_body.content) != response_body.content:
        return

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


def normalize_clarification_block(value: Any) -> ClarificationBlock | None:
    questions = normalize_string_list(value)
    if not questions:
        return None
    return ClarificationBlock(title="More information is needed", questions=questions)


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
            if text is not None and str(text).strip():
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
