import logging
import re
from typing import Any
from uuid import uuid4

from app.schemas.normalized_chat import (
    ChatContentBlock,
    ChatTableColumn,
    ChartBlock,
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
    OfficialReferenceBlock,
    PredictionBlock,
    PublicError,
    ReferencesBlock,
    ResponseLimitation,
    SummaryBlock,
    SuggestionsBlock,
    TableBlock,
)
from app.services.normalizers.calculator import (
    calculator_source_citations,
    build_calculator_blocks,
    format_calculator_markdown,
    is_calculator_response,
)
from app.services.normalizers.calculator.errors import (
    calculator_error_block_message,
    normalize_calculator_public_errors,
)
from app.services.normalizers.calculator.normalizer import CalculatorNormalizer
from app.services.normalizers.charts import normalize_chart
from app.services.normalizers.citations import dedupe_citations, normalize_citations
from app.services.normalizers.fallback import FallbackNormalizer, normalize_service_name
from app.services.normalizers.general import GeneralNormalizer
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
        GeneralNormalizer(),
    ],
    fallback=FallbackNormalizer(),
)

GENERAL_SUGGESTIONS_TITLE = "Suggested follow-ups"
GENERAL_ERROR_MESSAGES = {
    "GENERAL_SERVICE_UNAVAILABLE": "The general service is temporarily unavailable.",
    "GENERAL_TIMEOUT": "The general service timed out.",
    "GENERAL_VALIDATION_ERROR": "The general service could not process the request.",
    "INVALID_GENERAL_RESPONSE": "The general service returned an invalid response.",
    "INTERNAL_API_ERROR": "The request could not be completed.",
}
RETRIEVAL_ERROR_MESSAGES = {
    "RETRIEVAL_SERVICE_UNAVAILABLE": "The retrieval service is temporarily unavailable.",
    "RETRIEVAL_TIMEOUT": "The retrieval service timed out.",
    "RETRIEVAL_VALIDATION_ERROR": "The retrieval service could not process the request.",
    "RETRIEVAL_MISSING_INPUT": "More information is required to complete the retrieval request.",
    "INVALID_RETRIEVAL_RESPONSE": "The retrieval service returned an invalid response.",
    "INTERNAL_API_ERROR": "The request could not be completed.",
}
TRADE_ERROR_MESSAGES = {
    "TRADE_SERVICE_UNAVAILABLE": "The trade data service is temporarily unavailable.",
    "TRADE_TIMEOUT": "The trade data request timed out.",
    "TRADE_VALIDATION_ERROR": "The trade data request could not be processed.",
    "TRADE_NO_RESULTS": "No trade data was found for the requested criteria.",
    "INVALID_TRADE_RESPONSE": "The trade data service returned an invalid response.",
    "INTERNAL_API_ERROR": "The request could not be completed.",
}

logger = logging.getLogger(__name__)


def normalize_chat_response(
    raw: Any,
    *,
    chat: Any | None = None,
    include_debug: bool = False,
    request_presentation: dict[str, Any] | None = None,
) -> NormalizedChatResponse:
    payload = raw if isinstance(raw, dict) else {"answer": str(raw or "")}
    request_id = str(payload.get("request_id") or payload.get("requestId") or uuid4())
    log_internal_metadata(payload, request_id=request_id)
    session_id = normalize_session_id(payload.get("session_id") or payload.get("sessionId"), chat=chat, fallback=request_id)
    status = normalize_status(payload.get("status"))
    service = normalizer_registry.normalize(payload)
    intent = normalize_intent(payload, service)
    response_body = build_response_body(payload, service=service)
    assert_orchestrator_answer_unchanged(payload, response_body)
    coverage = response_body.coverage
    confidence = response_body.confidence

    public_errors = normalize_public_errors(payload, service)
    blocks = build_content_blocks(
        payload,
        service=service,
        response_body=response_body,
        public_errors=public_errors,
        request_presentation=request_presentation,
    )
    if status != "failed":
        assert_response_content_matches_first_markdown(response_body, blocks)
    citations = normalize_citations(payload.get("citations") or payload.get("references") or [])
    if is_calculator_response(payload):
        citations = dedupe_citations(
            citations + calculator_source_citations(response_body.content, start_index=len(citations) + 1)
        )
    else:
        citations = dedupe_citations(citations)
    suggestions = normalize_suggestions(payload)
    clarifications = normalize_clarifications(payload)

    if (
        service == "retrieval"
        and status == "clarification_required"
        and not clarifications
    ):
        status = "completed"

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
        clarifications=clarifications,
        errors=public_errors,
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

    return sanitize_debug_metadata(debug_metadata)


def log_internal_metadata(payload: dict[str, Any], *, request_id: str) -> None:
    metadata_keys: list[str] = []
    for key in ("metadata", "meta"):
        value = payload.get(key)
        if isinstance(value, dict):
            metadata_keys.extend(str(item_key) for item_key in value.keys())
    if not metadata_keys:
        return
    logger.debug(
        "upstream_internal_metadata request_id=%s keys=%s",
        request_id,
        sorted(set(metadata_keys)),
    )


SENSITIVE_DEBUG_KEYS = {
    "api_key",
    "authorization",
    "complete_internal_prompt",
    "connection_string",
    "database",
    "database_url",
    "db_url",
    "debug",
    "dal_source_url",
    "exception",
    "execution_plan",
    "filters",
    "internal_url",
    "internal_dimensions",
    "internal_latency_breakdown",
    "latency_breakdown",
    "nlu_unified_result",
    "password",
    "provider",
    "provider_credentials",
    "provider_details",
    "provider_name",
    "query_params",
    "query_plan",
    "raw_exception",
    "raw_count_diagnostics",
    "raw_token",
    "retrieval_strategies",
    "retrieval_strategy",
    "rewritten_queries",
    "rewritten_query",
    "route",
    "routing_details",
    "routing_metadata",
    "secret",
    "service_latencies_s",
    "service_query",
    "service_route",
    "sql",
    "sql_query",
    "sql_params",
    "stack_trace",
    "traceback",
    "token",
    "validation",
}


def sanitize_debug_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in SENSITIVE_DEBUG_KEYS:
                continue
            sanitized_value = sanitize_debug_metadata(item)
            if sanitized_value is not None:
                sanitized[key] = sanitized_value
        return sanitized
    if isinstance(value, list):
        return [item for item in (sanitize_debug_metadata(item) for item in value) if item is not None]
    return value


def build_response_body(payload: dict[str, Any], *, service: str | None = None) -> NormalizedResponseBody:
    response_value = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    answer_value = payload.get("answer") if isinstance(payload.get("answer"), dict) else {}
    source = response_value or answer_value

    summary = first_text(source, "summary", "overview", "direct_answer") if isinstance(source, dict) else None
    source_content = first_text(source, "content", "markdown", "text") if isinstance(source, dict) else None
    if service == "trade" and source_content:
        content = normalize_plain_answer_text(source_content)
    else:
        content = (
            preserved_plain_answer(payload)
            or source_content
            or first_text(payload, "content", "human_readable", "summary")
            or summary
            or ""
        )
    source_limitations = source.get("limitations") if isinstance(source, dict) else None
    source_missing = source.get("missing") if isinstance(source, dict) else None
    limitations = normalize_limitations(
        source_limitations
        or payload.get("limitations")
        or source_missing
        or payload.get("missing")
        or payload.get("missing_data")
        or payload.get("warnings")
    )
    coverage = normalize_coverage(
        (source.get("coverage") if isinstance(source, dict) else None)
        or payload.get("coverage")
        or payload.get("answer_coverage")
    )
    confidence = normalize_confidence(
        payload.get("candidate_confidence")
        or get_nested(payload, "metadata", "candidate_confidence")
        or (source.get("confidence") if isinstance(source, dict) else None)
        or payload.get("confidence")
    )
    if service == "retrieval":
        confidence = None

    return NormalizedResponseBody(
        type=get_response_type(payload),
        coverage=coverage,
        confidence=confidence,
        summary=summary,
        content=content,
        limitations=limitations,
    )


def preserved_plain_answer(payload: dict[str, Any]) -> str | None:
    for key in ("answer", "final_answer", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return normalize_plain_answer_text(value)
    return None


def normalize_plain_answer_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    return sanitize_unsafe_html(normalized)


UNSAFE_HTML_BLOCK_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed|svg)\b[^>]*>.*?<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
UNSAFE_HTML_TAG_RE = re.compile(
    r"<\s*/?\s*(script|style|iframe|object|embed|svg)\b[^>]*>",
    re.IGNORECASE,
)
HTML_EVENT_ATTRIBUTE_RE = re.compile(
    r"\s+on[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)
JAVASCRIPT_URL_RE = re.compile(r"javascript\s*:", re.IGNORECASE)
HS_CANDIDATE_LINE_RE = re.compile(
    r"^\s*(?P<rank>\d+)[.)]\s*"
    r"(?P<hs_code>(?:\d{4}(?:\.\d{2}){1,3})|\d{6,10})"
    r"\s*(?:[-–—:]\s*)?(?P<description>.+?)\s*$"
)
OFFICIAL_GDCE_REFERENCE_RE = re.compile(
    r"(?im)^.*?"
    r"(?P<url>https?://(?:www\.)?customs\.gov\.kh/"
    r"en/publications/14037-customs-tariff-of-cambodia-km-2022)"
    r"[^\n]*$"
)


def sanitize_unsafe_html(value: str) -> str:
    sanitized = UNSAFE_HTML_BLOCK_RE.sub("", value)
    sanitized = UNSAFE_HTML_TAG_RE.sub("", sanitized)
    sanitized = HTML_EVENT_ATTRIBUTE_RE.sub("", sanitized)
    sanitized = JAVASCRIPT_URL_RE.sub("", sanitized)
    return sanitized


def assert_orchestrator_answer_unchanged(payload: dict[str, Any], response_body: NormalizedResponseBody) -> None:
    service = normalize_service_name(payload.get("service") or payload.get("intent") or payload.get("route"))
    if service == "trade" and isinstance(payload.get("response"), dict) and payload["response"].get("content"):
        return
    answer = payload.get("answer")
    if not isinstance(answer, str):
        return
    if not answer.strip():
        return
    if response_body.content != normalize_plain_answer_text(answer):
        raise ValueError("Normalized content must match orchestrator answer")


def build_content_blocks(
    payload: dict[str, Any],
    *,
    service: str | None = None,
    response_body: NormalizedResponseBody,
    public_errors: list[str | PublicError] | None = None,
    request_presentation: dict[str, Any] | None = None,
) -> list[ChatContentBlock]:
    blocks: list[ChatContentBlock] = []
    is_calculator = is_calculator_response(payload)

    if is_calculator:
        message = payload.get("message")
        has_explicit_message_blocks = isinstance(message, dict) and isinstance(message.get("content"), list)
        if (
            normalize_status(payload.get("status")) != "failed"
            and (response_body.content or isinstance(payload.get("table"), dict) or has_explicit_message_blocks)
        ):
            blocks.extend(build_calculator_blocks(payload, response_body.content))
    elif service == "general":
        return build_general_content_blocks(payload, response_body=response_body, public_errors=public_errors)
    elif service == "retrieval":
        return build_retrieval_content_blocks(
            payload,
            response_body=response_body,
            public_errors=public_errors,
            request_presentation=request_presentation,
        )
    elif service == "trade":
        return build_trade_content_blocks(
            payload,
            response_body=response_body,
            public_errors=public_errors,
            request_presentation=request_presentation,
        )
    elif response_body.content:
        blocks.append(MarkdownBlock(text=response_body.content))

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
                title="Important limitation",
                tone="warning",
                items=limitation_messages or missing_items,
            )
        )

    if not is_calculator:
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
        or payload.get("questions")
    )
    clarification_block = normalize_clarification_block(clarifications)
    if clarification_block:
        blocks.append(clarification_block)

    status = normalize_status(payload.get("status"))
    public_error_values = [error for error in (public_errors or []) if isinstance(error, PublicError)]
    safe_calculator_error = calculator_error_block_message(public_error_values)
    safe_public_errors = [safe_calculator_error] if safe_calculator_error else [error.message for error in public_error_values]
    errors = safe_public_errors or (normalize_errors(payload.get("errors") or payload.get("error")) if status == "failed" else [])
    if errors:
        blocks.extend(ErrorBlock(message=message) for message in errors)
    elif status == "failed":
        blocks.append(ErrorBlock(message=first_text(payload, "error", "detail") or "Request failed"))

    suggestions = normalize_suggestions(payload)
    if suggestions:
        blocks.append(SuggestionsBlock(title="Related questions", items=suggestions))

    if not blocks:
        blocks.append(MarkdownBlock(text=""))

    return blocks


def build_trade_content_blocks(
    payload: dict[str, Any],
    *,
    response_body: NormalizedResponseBody,
    public_errors: list[str | PublicError] | None = None,
    request_presentation: dict[str, Any] | None = None,
) -> list[ChatContentBlock]:
    markdown_blocks: list[ChatContentBlock] = []
    summary_blocks: list[ChatContentBlock] = []
    table_blocks: list[ChatContentBlock] = []
    reference_blocks: list[ChatContentBlock] = []
    chart_blocks: list[ChatContentBlock] = []
    coverage_blocks: list[ChatContentBlock] = []
    clarification_blocks: list[ChatContentBlock] = []
    suggestion_blocks: list[ChatContentBlock] = []
    error_blocks: list[ChatContentBlock] = []

    # Standard orchestrator QueryResponse fields are the primary contract.
    if response_body.content:
        markdown_blocks.append(MarkdownBlock(text=response_body.content))

    summary_payload = payload.get("summary")
    has_primary_summary = isinstance(summary_payload, dict) and bool(summary_payload)
    upstream_summary_block = normalize_trade_summary_block(summary_payload)
    if upstream_summary_block:
        append_unique_block(summary_blocks, upstream_summary_block)
    upstream_data_quality_block = normalize_trade_data_quality_block(summary_payload)
    if upstream_data_quality_block:
        append_unique_block(coverage_blocks, upstream_data_quality_block)

    if not has_primary_summary:
        legacy_data_quality_block = normalize_trade_data_quality_block(payload.get("summary_metrics"))
        if legacy_data_quality_block:
            append_unique_block(coverage_blocks, legacy_data_quality_block)
        summary_block = normalize_trade_summary_metrics_block(payload.get("summary_metrics"))
        if summary_block:
            append_unique_block(summary_blocks, summary_block)

    upstream_table_block = normalize_table(payload.get("table"))
    if upstream_table_block:
        append_unique_block(table_blocks, upstream_table_block)
    top_level_citations = normalize_citations(payload.get("citations") or payload.get("references") or [])

    chart_block = normalize_trade_chart_block(payload.get("visualization"))
    if chart_block:
        append_unique_block(chart_blocks, chart_block)

    if presentation_requests_chart(request_presentation or payload.get("presentation")) and not chart_block:
        append_unique_block(
            coverage_blocks,
            CoverageBlock(
                title="Chart data unavailable",
                tone="warning",
                items=["The service returned a text trade answer but no quantitative dataset for a chart."],
            ),
        )

    no_results_block = normalize_trade_no_results_coverage_block(payload)
    if no_results_block:
        append_unique_block(coverage_blocks, no_results_block)

    limitation_messages = [limitation.message for limitation in response_body.limitations]
    missing_items = normalize_response_items(payload, "missing", "not_found", "unavailable")
    if limitation_messages or missing_items:
        append_unique_block(
            coverage_blocks,
            CoverageBlock(
                title="Important limitation",
                tone="warning",
                items=limitation_messages or missing_items,
            ),
        )

    # Direct trade-service shapes remain supported as compatibility input after the orchestrator envelope.
    for block in normalize_structured_trade_blocks(payload, include_tables=not upstream_table_block):
        if isinstance(block, SummaryBlock) and not summary_blocks:
            append_unique_block(summary_blocks, block)
        elif isinstance(block, TableBlock) and not table_blocks:
            append_unique_block(table_blocks, block)
        elif isinstance(block, ReferencesBlock):
            reference_block = filter_trade_references_block(block, top_level_citations)
            if reference_block:
                append_unique_block(reference_blocks, reference_block)
        elif isinstance(block, CoverageBlock):
            append_unique_block(coverage_blocks, block)

    clarification_block = normalize_clarification_block(
        payload.get("clarifications")
        or payload.get("clarifying_questions")
        or payload.get("clarification_questions")
        or payload.get("questions")
    )
    if clarification_block:
        append_unique_block(clarification_blocks, clarification_block)

    suggestions = normalize_suggestions(payload)
    if suggestions:
        append_unique_block(suggestion_blocks, SuggestionsBlock(title="Related questions", items=suggestions))

    public_error_values = [error for error in (public_errors or []) if isinstance(error, PublicError)]
    safe_public_errors = [error.message for error in public_error_values]
    if safe_public_errors:
        for message in safe_public_errors:
            append_unique_block(error_blocks, ErrorBlock(message=message))
    elif normalize_status(payload.get("status")) == "failed":
        append_unique_block(error_blocks, ErrorBlock(message=first_text(payload, "error", "detail") or "Request failed"))

    blocks = [
        *markdown_blocks,
        *summary_blocks,
        *table_blocks,
        *reference_blocks,
        *chart_blocks,
        *coverage_blocks,
        *clarification_blocks,
        *suggestion_blocks,
        *error_blocks,
    ]

    if not blocks:
        blocks.append(MarkdownBlock(text=""))

    return blocks


def normalize_trade_summary_block(value: Any) -> SummaryBlock | None:
    if not isinstance(value, dict) or not value:
        return None
    summary_data = {
        str(key): scalar_to_cell(item)
        for key, item in value.items()
        if key != "data_quality"
    }
    if not summary_data:
        return None
    return SummaryBlock(
        title="Trade Data Summary",
        data=summary_data,
    )


def normalize_trade_summary_metrics_block(value: Any) -> TableBlock | None:
    if not isinstance(value, dict):
        return normalize_summary_metrics(value)
    summary_metrics = {
        key: item
        for key, item in value.items()
        if key != "data_quality"
    }
    if not summary_metrics:
        return None
    return normalize_summary_metrics(summary_metrics)


TRADE_DATA_QUALITY_NOTE_KEYS = (
    "truncation_note",
    "partial_year_note",
    "period_coverage_note",
    "period_mismatch_note",
    "period_note",
)


def normalize_trade_data_quality_block(value: Any) -> CoverageBlock | None:
    if not isinstance(value, dict):
        return None
    data_quality = value.get("data_quality")
    if not isinstance(data_quality, dict):
        return None

    items = []
    for key in TRADE_DATA_QUALITY_NOTE_KEYS:
        note = data_quality.get(key)
        if isinstance(note, str) and note.strip():
            items.append(note.strip())

    if not items:
        return None
    return CoverageBlock(title="Data availability", tone="warning", items=list(dict.fromkeys(items)))


def normalize_trade_no_results_coverage_block(payload: dict[str, Any]) -> CoverageBlock | None:
    if normalize_status(payload.get("status")) == "failed":
        return None
    raw_errors = normalize_errors(payload.get("errors") or payload.get("error"))
    if classify_trade_error_code(payload, raw_errors) != "TRADE_NO_RESULTS":
        return None
    return CoverageBlock(
        title="Data availability",
        tone="warning",
        items=[TRADE_ERROR_MESSAGES["TRADE_NO_RESULTS"]],
    )


def filter_trade_references_block(
    block: ReferencesBlock,
    top_level_citations: list[Any],
) -> ReferencesBlock | None:
    if not top_level_citations:
        return block

    top_level_keys = {key for citation in top_level_citations for key in citation_source_keys(citation)}
    items = [
        item
        for item in block.items
        if not top_level_keys.intersection(reference_item_source_keys(item))
    ]
    if not items:
        return None
    return ReferencesBlock(title=block.title, items=items)


def citation_source_keys(citation: Any) -> set[str]:
    keys = set()
    for prefix, value in (
        ("url", getattr(citation, "url", None)),
        ("document", getattr(citation, "document_id", None)),
        ("citation", getattr(citation, "citation_id", None)),
        ("id", getattr(citation, "id", None)),
        ("title", getattr(citation, "title", None)),
    ):
        if isinstance(value, str) and value.strip():
            keys.add(f"{prefix}:{value.strip().lower()}")
    return keys


def reference_item_source_keys(item: dict[str, Any]) -> set[str]:
    keys = set()
    for prefix, value in (
        ("url", item.get("url")),
        ("document", item.get("source_id")),
        ("id", item.get("id")),
        ("title", item.get("title")),
    ):
        if isinstance(value, str | int | float | bool) and str(value).strip():
            keys.add(f"{prefix}:{str(value).strip().lower()}")
    return keys


def append_unique_block(blocks: list[ChatContentBlock], block: ChatContentBlock) -> None:
    key = block_dedupe_key(block)
    if any(block_dedupe_key(existing) == key for existing in blocks):
        return
    blocks.append(block)


def block_dedupe_key(block: ChatContentBlock) -> tuple[Any, ...]:
    if isinstance(block, MarkdownBlock):
        return (block.type, block.text)
    if isinstance(block, TableBlock):
        return (block.type, block.title, tuple(column.key for column in block.columns), tuple(tuple(row.items()) for row in block.rows))
    if isinstance(block, SummaryBlock):
        return (block.type, block.title, tuple(block.data.items()))
    if isinstance(block, ReferencesBlock):
        return (block.type, block.title, tuple(tuple(item.items()) for item in block.items))
    if isinstance(block, OfficialReferenceBlock):
        return (block.type, block.url)
    if isinstance(block, CoverageBlock):
        return (block.type, block.title, block.tone, tuple(block.items), block.note)
    if isinstance(block, ClarificationBlock):
        return (block.type, block.title, tuple(block.questions))
    if isinstance(block, SuggestionsBlock):
        return (block.type, block.title, tuple(block.items))
    if isinstance(block, ErrorBlock):
        return (block.type, block.message)
    if isinstance(block, ChartBlock):
        return (block.type, block.title, repr(block.data))
    return (repr(block),)


def build_retrieval_content_blocks(
    payload: dict[str, Any],
    *,
    response_body: NormalizedResponseBody,
    public_errors: list[str | PublicError] | None = None,
    request_presentation: dict[str, Any] | None = None,
) -> list[ChatContentBlock]:
    explicit_blocks = normalize_general_message_content_blocks(payload)
    if explicit_blocks:
        return enhance_explicit_retrieval_blocks(
            explicit_blocks,
            payload=payload,
            response_body=response_body,
        )

    blocks: list[ChatContentBlock] = []
    official_reference_block = extract_official_reference_block(response_body)
    if response_body.content:
        blocks.append(MarkdownBlock(text=response_body.content))

    prediction_block = normalize_hs_code_prediction_block(payload)
    if prediction_block:
        blocks.append(prediction_block)

    if not prediction_block:
        for block in normalize_inferred_hs_code_blocks(payload, response_body=response_body):
            blocks.append(block)

    for table_block in normalize_retrieval_table_blocks(payload):
        if not any(isinstance(block, TableBlock) and block.title == table_block.title for block in blocks):
            blocks.append(table_block)

    if official_reference_block:
        blocks.append(official_reference_block)

    chart_block = normalize_retrieval_chart_block(payload.get("visualization"))
    if chart_block:
        blocks.append(chart_block)

    clarification_block = normalize_clarification_block(
        payload.get("clarifications")
        or payload.get("clarifying_questions")
        or payload.get("clarification_questions")
        or payload.get("questions")
    )
    if clarification_block:
        blocks.append(clarification_block)

    suggestions = normalize_suggestions(payload)
    if suggestions:
        blocks.append(SuggestionsBlock(title="Related questions", items=suggestions))

    coverage_blocks = normalize_retrieval_coverage_blocks(
        payload,
        response_body=response_body,
        chart_requested=presentation_requests_chart(request_presentation or payload.get("presentation")),
        chart_available=chart_block is not None,
    )
    blocks.extend(coverage_blocks)

    public_error_values = [error for error in (public_errors or []) if isinstance(error, PublicError)]
    error_messages = [error.message for error in public_error_values] or normalize_errors(payload.get("errors") or payload.get("error"))
    if error_messages:
        blocks.extend(ErrorBlock(message=message) for message in error_messages)
    elif normalize_status(payload.get("status")) == "failed":
        blocks.append(ErrorBlock(message="Request failed"))

    return blocks


def enhance_explicit_retrieval_blocks(
    blocks: list[ChatContentBlock],
    *,
    payload: dict[str, Any],
    response_body: NormalizedResponseBody,
) -> list[ChatContentBlock]:
    official_reference_block = extract_official_reference_block(response_body)
    if official_reference_block:
        blocks = [
            MarkdownBlock(text=strip_official_reference_line(block.text)) if isinstance(block, MarkdownBlock) else block
            for block in blocks
        ]

    inferred_blocks = normalize_inferred_hs_code_blocks(payload, response_body=response_body)
    if not inferred_blocks:
        if official_reference_block and not any(isinstance(block, OfficialReferenceBlock) for block in blocks):
            insertion_index = 1 if blocks and isinstance(blocks[0], MarkdownBlock) else 0
            return [*blocks[:insertion_index], official_reference_block, *blocks[insertion_index:]]
        return blocks

    existing_prediction = any(isinstance(block, PredictionBlock) for block in blocks)
    existing_table = any(isinstance(block, TableBlock) for block in blocks)
    blocks_to_insert = [
        block
        for block in inferred_blocks
        if not (
            (isinstance(block, PredictionBlock) and existing_prediction)
            or (isinstance(block, TableBlock) and existing_table)
        )
    ]
    if official_reference_block and not any(isinstance(block, OfficialReferenceBlock) for block in blocks):
        blocks_to_insert.append(official_reference_block)

    if not blocks_to_insert:
        return blocks

    insertion_index = 1 if blocks and isinstance(blocks[0], MarkdownBlock) else 0
    return [*blocks[:insertion_index], *blocks_to_insert, *blocks[insertion_index:]]


def extract_official_reference_block(response_body: NormalizedResponseBody) -> OfficialReferenceBlock | None:
    match = OFFICIAL_GDCE_REFERENCE_RE.search(response_body.content or "")
    if not match:
        return None
    url = match.group("url").rstrip(".,)")
    response_body.content = strip_official_reference_line(response_body.content)
    return OfficialReferenceBlock(
        title="Official GDCE tariff lookup",
        label="Verify on the official GDCE tariff lookup",
        url=url,
        agency="GDCE",
        source_type="official_tariff",
    )


def strip_official_reference_line(value: str) -> str:
    return OFFICIAL_GDCE_REFERENCE_RE.sub("", value or "").strip()


def normalize_retrieval_table_blocks(payload: dict[str, Any]) -> list[TableBlock]:
    blocks: list[TableBlock] = []
    candidate_table = normalize_hs_code_candidate_table(payload)
    if candidate_table:
        blocks.append(candidate_table)

    for table_value in iter_table_values(payload):
        table_block = normalize_table(table_value)
        if table_block and table_block.rows:
            blocks.append(table_block)

    documents_block = normalize_documents_table(payload.get("documents"))
    if documents_block and documents_block.rows:
        blocks.append(documents_block)

    line_items_block = normalize_line_items_table(payload.get("line_items"))
    if line_items_block and line_items_block.rows:
        blocks.append(line_items_block)

    return blocks


def normalize_inferred_hs_code_blocks(
    payload: dict[str, Any],
    *,
    response_body: NormalizedResponseBody,
) -> list[ChatContentBlock]:
    if structured_hs_code_result(payload):
        return []

    candidates = parse_hs_code_candidates_from_text(response_body.content)
    if not candidates:
        return []

    primary = candidates[0]
    prediction = PredictionBlock(
        title="Preliminary HS Code",
        data={
            "hsCode": primary["hs_code"],
            "description": primary["description"],
            "preliminary": response_body.coverage != "complete",
        },
    )
    table = TableBlock(
        title="Possible HS Code Matches",
        columns=[
            ChatTableColumn(key="rank", label="Rank"),
            ChatTableColumn(key="hs_code", label="HS Code"),
            ChatTableColumn(key="description", label="Description"),
        ],
        rows=[
            {
                "rank": candidate["rank"],
                "hs_code": candidate["hs_code"],
                "description": candidate["description"],
            }
            for candidate in candidates
        ],
    )
    return [prediction, table]


def parse_hs_code_candidates_from_text(value: str) -> list[dict[str, str | int]]:
    candidates: list[dict[str, str | int]] = []
    seen_codes: set[str] = set()
    for line in value.splitlines():
        match = HS_CANDIDATE_LINE_RE.match(line)
        if not match:
            continue
        hs_code = match.group("hs_code").strip()
        if hs_code in seen_codes:
            continue
        description = match.group("description").strip()
        if not description:
            continue
        seen_codes.add(hs_code)
        candidates.append(
            {
                "rank": int(match.group("rank")),
                "hs_code": hs_code,
                "description": description,
            }
        )

    return candidates


def structured_hs_code_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    if result.get("kind") != "hs_code_lookup":
        return None
    return result


def normalize_hs_code_prediction_block(payload: dict[str, Any]) -> PredictionBlock | None:
    result = structured_hs_code_result(payload)
    if not result:
        return None
    primary_candidate = result.get("primary_candidate")
    if not isinstance(primary_candidate, dict):
        return None

    hs_code = scalar_to_cell(primary_candidate.get("hs_code"))
    description = scalar_to_cell(primary_candidate.get("description"))
    preliminary = scalar_to_cell(result.get("is_preliminary"))
    if hs_code is None and description is None:
        return None

    return PredictionBlock(
        title="Preliminary HS Code",
        data={
            "hsCode": hs_code,
            "description": description,
            "preliminary": preliminary,
        },
    )


def normalize_hs_code_candidate_table(payload: dict[str, Any]) -> TableBlock | None:
    result = structured_hs_code_result(payload)
    if not result:
        return None
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return None

    rows: list[dict[str, str | int | float | bool | None]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        row = {
            "rank": scalar_to_cell(candidate.get("rank")),
            "hs_code": scalar_to_cell(candidate.get("hs_code")),
            "description": scalar_to_cell(candidate.get("description")),
            "retrieval_score": scalar_to_cell(candidate.get("retrieval_score")),
        }
        if any(value is not None for value in row.values()):
            rows.append(row)
    if not rows:
        return None

    return TableBlock(
        title="Possible HS Code Matches",
        columns=[
            ChatTableColumn(key="rank", label="Rank"),
            ChatTableColumn(key="hs_code", label="HS Code"),
            ChatTableColumn(key="description", label="Description"),
            ChatTableColumn(key="retrieval_score", label="Match Score"),
        ],
        rows=rows,
    )


def normalize_retrieval_chart_block(value: Any) -> ChartBlock | None:
    if not has_quantitative_chart_data(value):
        return None
    return normalize_chart(value)


def normalize_trade_chart_block(value: Any) -> ChartBlock | None:
    if not has_quantitative_chart_data(value):
        return None
    return normalize_chart(value)


def has_quantitative_chart_data(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    labels = value.get("labels")
    datasets = value.get("datasets")
    if isinstance(labels, list) and isinstance(datasets, list) and labels:
        for dataset in datasets:
            if not isinstance(dataset, dict):
                continue
            data = dataset.get("data")
            if isinstance(data, list) and any(is_number_like(item) for item in data):
                return True

    data_rows = value.get("data")
    series = value.get("series")
    if isinstance(data_rows, list) and isinstance(series, list) and data_rows:
        series_keys = [item.get("key") for item in series if isinstance(item, dict) and item.get("key")]
        for row in data_rows:
            if isinstance(row, dict) and any(is_number_like(row.get(key)) for key in series_keys):
                return True

    return False


def is_number_like(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int | float):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


def normalize_retrieval_coverage_blocks(
    payload: dict[str, Any],
    *,
    response_body: NormalizedResponseBody,
    chart_requested: bool = False,
    chart_available: bool = False,
) -> list[CoverageBlock]:
    blocks: list[CoverageBlock] = []
    found_items = normalize_response_items(payload, "found", "available", "known")
    if found_items:
        blocks.append(CoverageBlock(title="What was found", tone="info", items=found_items))

    limitation_messages = [limitation.message for limitation in response_body.limitations]
    missing_items = normalize_response_items(payload, "missing", "not_found", "unavailable")
    if limitation_messages or missing_items:
        blocks.append(
            CoverageBlock(
                title="Important limitation",
                tone="warning",
                items=limitation_messages or missing_items,
            )
        )
    if chart_requested and not chart_available:
        blocks.append(
            CoverageBlock(
                title="Chart data unavailable",
                tone="warning",
                items=[
                    "The service returned a text classification result but no quantitative dataset for a chart."
                ],
            )
        )
    return blocks


def presentation_requests_chart(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    preferred_blocks = value.get("preferred_blocks")
    if not isinstance(preferred_blocks, list):
        return False
    return any(str(block).strip().lower() == "chart" for block in preferred_blocks)


def build_general_content_blocks(
    payload: dict[str, Any],
    *,
    response_body: NormalizedResponseBody,
    public_errors: list[str | PublicError] | None = None,
) -> list[ChatContentBlock]:
    blocks = normalize_general_message_content_blocks(payload)
    has_explicit_blocks = bool(blocks)
    has_primary_answer = has_primary_general_answer_block(blocks)

    if not has_primary_answer and response_body.content:
        blocks.insert(0, MarkdownBlock(text=response_body.content))

    if not has_explicit_blocks:
        clarification_block = normalize_clarification_block(
            payload.get("clarifications")
            or payload.get("clarifying_questions")
            or payload.get("clarification_questions")
            or payload.get("questions")
        )
        if clarification_block:
            blocks.append(clarification_block)

    if not has_explicit_blocks:
        suggestions = normalize_suggestions(payload)
        if suggestions:
            blocks.append(SuggestionsBlock(title=GENERAL_SUGGESTIONS_TITLE, items=suggestions))

    if not has_explicit_blocks:
        coverage_items = [limitation.message for limitation in response_body.limitations]
        coverage_items.extend(normalize_response_items(payload, "missing", "not_found", "unavailable"))
        if coverage_items:
            blocks.append(CoverageBlock(title="Information limitation", tone="warning", items=list(dict.fromkeys(coverage_items))))

    if not blocks and normalize_status(payload.get("status")) != "failed":
        blocks.append(MarkdownBlock(text=""))

    error_messages = normalize_general_error_messages(payload, public_errors=public_errors)
    if error_messages:
        if not any(isinstance(block, ErrorBlock) for block in blocks):
            blocks.extend(ErrorBlock(message=message) for message in error_messages)
    elif normalize_status(payload.get("status")) == "failed" and not any(isinstance(block, ErrorBlock) for block in blocks):
        blocks.append(ErrorBlock(message="Request failed"))

    return blocks


def has_primary_general_answer_block(blocks: list[ChatContentBlock]) -> bool:
    for block in blocks:
        if isinstance(block, MarkdownBlock):
            if block.text.strip():
                return True
            continue
        if isinstance(block, TableBlock):
            if block.rows:
                return True
            continue
        if isinstance(block, (SummaryBlock, KeyValueBlock, DetailsBlock, ChartBlock, PredictionBlock)):
            return True
    return False


def normalize_general_error_messages(
    payload: dict[str, Any],
    *,
    public_errors: list[str | PublicError] | None = None,
) -> list[str]:
    messages: list[str] = []
    for error in public_errors or []:
        if isinstance(error, PublicError):
            messages.append(error.message)
        elif isinstance(error, str) and error.strip():
            messages.append(error.strip())
    if not messages:
        messages.extend(normalize_errors(payload.get("errors") or payload.get("error")))
    return list(dict.fromkeys(messages))


def normalize_general_message_content_blocks(payload: dict[str, Any]) -> list[ChatContentBlock]:
    message = payload.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []

    blocks: list[ChatContentBlock] = []
    for item in content:
        block = normalize_general_message_content_block(item)
        if block:
            blocks.append(block)
    return blocks


def normalize_general_message_content_block(value: Any) -> ChatContentBlock | None:
    if not isinstance(value, dict):
        return None
    block_type = str(value.get("type") or "").strip().lower()

    if block_type == "markdown":
        text = value.get("text") if isinstance(value.get("text"), str) else value.get("content")
        return MarkdownBlock(text=text if isinstance(text, str) else "")

    if block_type == "clarification":
        questions = normalize_string_list(value.get("questions") or value.get("items") or value.get("content"))
        if not questions:
            return None
        title = value.get("title") if isinstance(value.get("title"), str) else "More information is needed"
        return ClarificationBlock(title=title, questions=questions)

    if block_type == "suggestions":
        items = normalize_string_list(value.get("items") or value.get("suggestions") or value.get("content"))
        if not items:
            return None
        title = value.get("title") if isinstance(value.get("title"), str) else GENERAL_SUGGESTIONS_TITLE
        return SuggestionsBlock(title=title, items=items)

    if block_type == "coverage":
        items = normalize_string_list(value.get("items") or value.get("limitations") or value.get("content"))
        if not items:
            return None
        raw_tone = str(value.get("tone") or "warning").lower()
        tone = "info" if raw_tone == "info" else "warning"
        title = value.get("title") if isinstance(value.get("title"), str) else "Information limitation"
        note = value.get("note") if isinstance(value.get("note"), str) else None
        return CoverageBlock(title=title, tone=tone, items=items, note=note)

    if block_type == "references":
        items = value.get("items") or value.get("references") or value.get("citations")
        normalized_items = normalize_reference_items(items)
        if not normalized_items:
            return None
        title = value.get("title") if isinstance(value.get("title"), str) else "References"
        return ReferencesBlock(title=title, items=normalized_items)

    if block_type == "official_reference":
        url = value.get("url") if isinstance(value.get("url"), str) else None
        if not url:
            return None
        title = value.get("title") if isinstance(value.get("title"), str) else "Official reference"
        label = value.get("label") if isinstance(value.get("label"), str) else title
        agency = value.get("agency") if isinstance(value.get("agency"), str) else None
        source_type = value.get("source_type") if isinstance(value.get("source_type"), str) else None
        return OfficialReferenceBlock(title=title, label=label, url=url, agency=agency, source_type=source_type)

    if block_type == "error":
        message = value.get("message") if isinstance(value.get("message"), str) else value.get("content")
        text = message if isinstance(message, str) and message.strip() else "Request failed"
        return ErrorBlock(message=text)

    return None


def normalize_reference_items(value: Any) -> list[dict[str, str | int | float | bool | None]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, str | int | float | bool | None]] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if text:
                items.append({"title": text})
            continue
        if not isinstance(item, dict):
            continue
        normalized = {
            str(key): scalar_to_cell(item_value)
            for key, item_value in item.items()
            if scalar_to_cell(item_value) is not None
        }
        if normalized:
            items.append(normalized)
    return items


def assert_response_content_matches_first_markdown(
    response_body: NormalizedResponseBody,
    blocks: list[ChatContentBlock],
) -> None:
    if not response_body.content:
        return
    if any(
        isinstance(
            block,
            (
                SummaryBlock,
                KeyValueBlock,
                DetailsBlock,
                ReferencesBlock,
                ClarificationBlock,
                SuggestionsBlock,
                CoverageBlock,
                ErrorBlock,
            ),
        )
        for block in blocks
    ):
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
    if status in {"completed", "success", "ok", "done"}:
        return "completed"
    if status in {"clarification_required", "needs_clarification", "clarify", "clarification"}:
        return "clarification_required"
    if status in {"partial_answer", "partial", "incomplete"}:
        return "partial"
    if status in {"processing", "pending", "running", "streaming"}:
        return "processing"
    if status in {"failed", "error", "invalid_query"}:
        return "failed"
    return "completed"


def normalize_intent(payload: dict[str, Any], service: str | None) -> str:
    raw_intent = str(payload.get("intent") or payload.get("route") or "").strip()
    if service == "calculator" and raw_intent.lower() in {"", "general", "calculator", "calculation"}:
        return "calculation"
    result = payload.get("result")
    if service == "retrieval" and not raw_intent and isinstance(result, dict) and result.get("kind") == "hs_code_lookup":
        return "hs_code_lookup"
    return raw_intent or "general"


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


def normalize_clarifications(payload: dict[str, Any]) -> list[str]:
    return normalize_string_list(
        payload.get("clarifications")
        or payload.get("clarifying_questions")
        or payload.get("clarification_questions")
        or payload.get("questions")
    )


def normalize_errors(value: Any) -> list[str]:
    if isinstance(value, dict):
        message = value.get("message") or value.get("detail") or value.get("code")
        return [str(message)] if message else []
    return normalize_string_list(value)


def normalize_public_errors(payload: dict[str, Any], service: str | None) -> list[str | PublicError]:
    if service == "calculator":
        return normalize_calculator_public_errors(payload)
    if service == "general":
        general_errors = normalize_general_public_errors(payload)
        if general_errors:
            return general_errors
    if service == "retrieval":
        retrieval_errors = normalize_retrieval_public_errors(payload)
        if retrieval_errors:
            return retrieval_errors
    if service == "trade":
        trade_errors = normalize_trade_public_errors(payload)
        return trade_errors
    return normalize_errors(payload.get("errors") or payload.get("error"))


def normalize_general_public_errors(payload: dict[str, Any]) -> list[PublicError]:
    raw_errors = normalize_errors(payload.get("errors") or payload.get("error"))
    if not raw_errors and normalize_status(payload.get("status")) != "failed":
        return []

    code = classify_general_error_code(payload, raw_errors)
    return [
        PublicError(
            code=code,
            message=GENERAL_ERROR_MESSAGES[code],
            retryable=code in {"GENERAL_SERVICE_UNAVAILABLE", "GENERAL_TIMEOUT", "INTERNAL_API_ERROR"},
        )
    ]


def classify_general_error_code(payload: dict[str, Any], raw_errors: list[str]) -> str:
    raw_text = " ".join(str(value) for value in raw_errors + [payload.get("status"), payload.get("detail")] if value).lower()
    explicit_code = str(get_nested(payload, "error", "code") or payload.get("code") or "").strip().upper()
    if explicit_code in GENERAL_ERROR_MESSAGES:
        return explicit_code
    if "timeout" in raw_text or "timed out" in raw_text:
        return "GENERAL_TIMEOUT"
    if "validation" in raw_text or "invalid query" in raw_text or "missing input" in raw_text or "bad request" in raw_text:
        return "GENERAL_VALIDATION_ERROR"
    if "invalid response" in raw_text or "malformed" in raw_text:
        return "INVALID_GENERAL_RESPONSE"
    if "unavailable" in raw_text or "connection" in raw_text or "503" in raw_text:
        return "GENERAL_SERVICE_UNAVAILABLE"
    return "INTERNAL_API_ERROR"


def normalize_retrieval_public_errors(payload: dict[str, Any]) -> list[PublicError]:
    raw_errors = normalize_errors(payload.get("errors") or payload.get("error"))
    if not raw_errors and normalize_status(payload.get("status")) != "failed":
        return []

    code = classify_retrieval_error_code(payload, raw_errors)
    logger.warning(
        "retrieval_upstream_error request_id=%s session_id=%s public_code=%s raw_error=%r",
        payload.get("request_id") or payload.get("requestId"),
        payload.get("session_id") or payload.get("sessionId"),
        code,
        payload.get("errors") or payload.get("error"),
    )
    return [
        PublicError(
            code=code,
            message=RETRIEVAL_ERROR_MESSAGES[code],
            retryable=code in {"RETRIEVAL_SERVICE_UNAVAILABLE", "RETRIEVAL_TIMEOUT", "INTERNAL_API_ERROR"},
        )
    ]


def classify_retrieval_error_code(payload: dict[str, Any], raw_errors: list[str]) -> str:
    raw_text = " ".join(str(value) for value in raw_errors + [payload.get("status"), payload.get("detail")] if value).lower()
    explicit_code = str(get_nested(payload, "error", "code") or payload.get("code") or "").strip().upper()
    if explicit_code in RETRIEVAL_ERROR_MESSAGES:
        return explicit_code
    if "timeout" in raw_text or "timed out" in raw_text:
        return "RETRIEVAL_TIMEOUT"
    if "missing input" in raw_text or "missing required" in raw_text or "required field" in raw_text:
        return "RETRIEVAL_MISSING_INPUT"
    if "validation" in raw_text or "invalid query" in raw_text or "bad request" in raw_text:
        return "RETRIEVAL_VALIDATION_ERROR"
    if "invalid response" in raw_text or "malformed" in raw_text:
        return "INVALID_RETRIEVAL_RESPONSE"
    if "unavailable" in raw_text or "connection" in raw_text or "503" in raw_text:
        return "RETRIEVAL_SERVICE_UNAVAILABLE"
    return "INTERNAL_API_ERROR"


def normalize_trade_public_errors(payload: dict[str, Any]) -> list[PublicError]:
    raw_errors = normalize_errors(payload.get("errors") or payload.get("error"))
    if normalize_status(payload.get("status")) != "failed":
        return []

    code = classify_trade_error_code(payload, raw_errors)
    logger.warning(
        "trade_upstream_error request_id=%s session_id=%s public_code=%s raw_error=%r",
        payload.get("request_id") or payload.get("requestId"),
        payload.get("session_id") or payload.get("sessionId"),
        code,
        payload.get("errors") or payload.get("error"),
    )
    return [
        PublicError(
            code=code,
            message=TRADE_ERROR_MESSAGES[code],
            retryable=code in {"TRADE_SERVICE_UNAVAILABLE", "TRADE_TIMEOUT", "INTERNAL_API_ERROR"},
        )
    ]


def classify_trade_error_code(payload: dict[str, Any], raw_errors: list[str]) -> str:
    raw_text = " ".join(str(value) for value in raw_errors + [payload.get("status"), payload.get("detail")] if value).lower()
    explicit_code = str(get_nested(payload, "error", "code") or payload.get("code") or "").strip().upper()
    if explicit_code in TRADE_ERROR_MESSAGES:
        return explicit_code
    if "timeout" in raw_text or "timed out" in raw_text:
        return "TRADE_TIMEOUT"
    if "no results" in raw_text or "not found" in raw_text or "no trade data" in raw_text or "empty result" in raw_text:
        return "TRADE_NO_RESULTS"
    if "validation" in raw_text or "invalid query" in raw_text or "missing input" in raw_text or "bad request" in raw_text:
        return "TRADE_VALIDATION_ERROR"
    if "invalid response" in raw_text or "malformed" in raw_text:
        return "INVALID_TRADE_RESPONSE"
    if "unavailable" in raw_text or "connection" in raw_text or "503" in raw_text:
        return "TRADE_SERVICE_UNAVAILABLE"
    return "INTERNAL_API_ERROR"


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, dict):
        return normalize_string_list(
            value.get("questions")
            or value.get("items")
            or value.get("message")
            or value.get("detail")
            or value.get("question")
        )
    if isinstance(value, list):
        normalized = []
        seen = set()
        for item in value:
            if isinstance(item, dict):
                text = item.get("message") or item.get("detail") or item.get("question")
            else:
                text = item
            text = str(text).strip() if text is not None else ""
            if text and text not in seen:
                seen.add(text)
                normalized.append(text)
        return normalized
    return []


def normalize_suggestions(payload: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    seen: set[str] = set()
    for key in ("suggestion", "suggestions", "followups", "follow_ups", "follow_up_questions"):
        if key not in payload or payload.get(key) is None:
            continue
        value = payload.get(key)
        if not isinstance(value, (list, str)):
            continue
        for item in normalize_string_list(value):
            if item in seen:
                continue
            seen.add(item)
            suggestions.append(item)
    return suggestions


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
