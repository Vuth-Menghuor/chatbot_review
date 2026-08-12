from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTableColumn(BaseModel):
    key: str
    label: str


class MarkdownBlock(BaseModel):
    type: Literal["markdown"] = "markdown"
    text: str


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str | None = None
    columns: list[ChatTableColumn] = Field(default_factory=list)
    rows: list[dict[str, str | int | float | bool | None]] = Field(default_factory=list)


class SummaryBlock(BaseModel):
    type: Literal["summary"] = "summary"
    title: str
    data: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class KeyValueItem(BaseModel):
    key: str
    value: str | int | float | bool | None


class KeyValueBlock(BaseModel):
    type: Literal["key_value"] = "key_value"
    title: str
    items: list[KeyValueItem] = Field(default_factory=list)


class DetailsItem(BaseModel):
    title: str
    content: str


class DetailsBlock(BaseModel):
    type: Literal["details"] = "details"
    title: str
    items: list[DetailsItem] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)


class ReferencesBlock(BaseModel):
    type: Literal["references"] = "references"
    title: str | None = None
    items: list[dict[str, str | int | float | bool | None]] = Field(default_factory=list)


class OfficialReferenceBlock(BaseModel):
    type: Literal["official_reference"] = "official_reference"
    title: str
    label: str
    url: str
    agency: str | None = None
    source_type: str | None = None


class ClarificationBlock(BaseModel):
    type: Literal["clarification"] = "clarification"
    title: str | None = None
    questions: list[str] = Field(default_factory=list)


class ErrorBlock(BaseModel):
    type: Literal["error"] = "error"
    message: str


class PublicError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    title: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class PredictionBlock(BaseModel):
    type: Literal["prediction"] = "prediction"
    title: str
    data: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class SuggestionsBlock(BaseModel):
    type: Literal["suggestions"] = "suggestions"
    title: str | None = None
    items: list[str] = Field(default_factory=list)


class CoverageBlock(BaseModel):
    type: Literal["coverage"] = "coverage"
    title: str
    tone: Literal["info", "warning"] = "info"
    items: list[str] = Field(default_factory=list)
    note: str | None = None


ChatContentBlock = (
    MarkdownBlock
    | SummaryBlock
    | KeyValueBlock
    | TableBlock
    | DetailsBlock
    | ReferencesBlock
    | OfficialReferenceBlock
    | ClarificationBlock
    | ErrorBlock
    | ChartBlock
    | PredictionBlock
    | SuggestionsBlock
    | CoverageBlock
)


class ResponseLimitation(BaseModel):
    code: str | None = None
    message: str


class NormalizedResponseBody(BaseModel):
    type: Literal["markdown", "table", "chart"] = "markdown"
    coverage: Literal["complete", "partial", "unknown"] = "unknown"
    confidence: Literal["high", "medium", "low"] | None = None
    summary: str | None = None
    content: str
    limitations: list[ResponseLimitation] = Field(default_factory=list)


class Citation(BaseModel):
    id: str
    marker: int | None = None
    label: str | None = None
    title: str | None = None
    snippet: str | None = None
    url: str | None = None
    score: float | None = None
    citation_id: str | None = None
    document_id: str | None = None
    filename: str | None = None
    chunk_index: int | None = None
    retrieval_method: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedAssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: list[ChatContentBlock] = Field(default_factory=list)


class NormalizedChatDebug(BaseModel):
    """Internal diagnostics. Return only for development or administrator views."""

    latency_ms: float | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    answer_source: str | None = None
    semantic_count: int | None = None
    structured_count: int | None = None
    total_count: int | None = None
    query_strategy: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedChatResponse(BaseModel):
    """Frontend-safe chat response envelope produced by the API layer."""

    api_version: Literal["1.0"] = "1.0"
    request_id: str
    session_id: str
    chat_id: str | None = None
    project_id: str | None = None
    status: Literal["completed", "clarification_required", "partial", "failed", "processing"]
    service: str | None = None
    intent: str
    query: str | None = None
    language: str | None = None
    coverage: Literal["complete", "partial", "unknown"] = "unknown"
    confidence: Literal["high", "medium", "low"] | None = None
    response: NormalizedResponseBody
    message: NormalizedAssistantMessage
    citations: list[Citation] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    clarifications: list[str] = Field(default_factory=list)
    errors: list[str | PublicError] = Field(default_factory=list)
    metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    debug: NormalizedChatDebug | None = None
