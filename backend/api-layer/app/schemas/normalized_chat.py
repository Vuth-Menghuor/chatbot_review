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


class ClarificationBlock(BaseModel):
    type: Literal["clarification"] = "clarification"
    title: str | None = None
    questions: list[str] = Field(default_factory=list)


class ErrorBlock(BaseModel):
    type: Literal["error"] = "error"
    message: str


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    title: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


ChatContentBlock = MarkdownBlock | TableBlock | ClarificationBlock | ErrorBlock | ChartBlock


class Citation(BaseModel):
    id: str
    label: str | None = None
    title: str | None = None
    snippet: str | None = None
    url: str | None = None
    score: float | None = None


class NormalizedAssistantMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: list[ChatContentBlock] = Field(default_factory=list)


class NormalizedChatDebug(BaseModel):
    """Internal diagnostics. Return only for development or administrator views."""

    latency_ms: float | None = None
    confidence: Literal["high", "medium", "low"] | None = None
    answer_source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NormalizedChatResponse(BaseModel):
    """Frontend-safe chat response envelope produced by the API layer."""

    request_id: str
    session_id: str
    status: Literal["completed", "processing", "failed"]
    intent: str
    message: NormalizedAssistantMessage
    citations: list[Citation] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    debug: NormalizedChatDebug | None = None
