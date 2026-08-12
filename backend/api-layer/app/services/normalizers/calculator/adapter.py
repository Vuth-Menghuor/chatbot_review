from typing import Any

from app.schemas.normalized_chat import (
    ChatContentBlock,
    ClarificationBlock,
    DetailsBlock,
    DetailsItem,
    ErrorBlock,
    KeyValueBlock,
    KeyValueItem,
    MarkdownBlock,
    ReferencesBlock,
    SummaryBlock,
)
from app.services.normalizers.calculator.citations import (
    calculator_source_citations,
    dedupe_reference_items,
    reference_item_from_value,
)
from app.services.normalizers.calculator.details import (
    assumptions_details_block,
    assumptions_details_block_from_legacy_sections,
    calculation_details_block,
    calculation_details_block_from_legacy_sections,
)
from app.services.normalizers.calculator.fallback import (
    calculator_markdown_fallback_blocks,
    is_calculator_markdown_text,
)
from app.services.normalizers.calculator.formatting import scalar_to_cell
from app.services.normalizers.calculator.key_values import (
    input_key_value_block,
    input_key_value_block_from_legacy_sections,
    product_key_value_block,
    product_key_value_block_from_legacy_sections,
)
from app.services.normalizers.calculator.summary import (
    summary_block_from_legacy_sections,
    summary_block_from_structured_result,
)
from app.services.normalizers.calculator.tables import (
    table_block_from_upstream_table,
    tax_breakdown_table,
    tax_breakdown_table_from_legacy_content,
)
from app.services.normalizers.calculator.legacy import parse_calculator_text_sections
from app.services.normalizers.calculator.validation import warn_calculator_business_inconsistencies


class CalculatorResponseAdapter:
    """Convert external calculator payloads into frontend-supported blocks."""

    def can_handle(self, payload: dict[str, Any]) -> bool:
        result = payload.get("result")
        answer = payload.get("answer")
        return bool(
            payload.get("calculator_result")
            or payload.get("structured_result")
            or (isinstance(result, dict) and (result.get("tax_breakdown") or result.get("phases")))
            or payload.get("service") == "calculator"
            or payload.get("intent") in {"calculator", "calculation"}
            or (isinstance(answer, str) and is_calculator_markdown_text(answer))
        )

    def service_name(self, payload: dict[str, Any]) -> str:
        return "calculator"

    def build_blocks(self, payload: dict[str, Any], content: str) -> list[ChatContentBlock]:
        warn_calculator_business_inconsistencies(payload, content)
        top_level_sources_available = has_top_level_citations(payload) or bool(calculator_source_citations(content))

        structured = first_structured_calculator_result(payload)
        if structured:
            structured_blocks = blocks_from_structured_calculator_result(
                structured,
                include_references=not top_level_sources_available,
            )
            if structured_blocks:
                return structured_blocks

        table_block = table_block_from_upstream_table(payload.get("table"))
        if table_block:
            return [table_block]

        message_blocks = blocks_from_upstream_message(
            payload.get("message"),
            include_references=not top_level_sources_available,
        )
        if message_blocks:
            return message_blocks

        legacy_blocks = blocks_from_legacy_calculator_content(payload, content)
        if legacy_blocks:
            return legacy_blocks

        return calculator_markdown_fallback_blocks(content)


calculator_response_adapter = CalculatorResponseAdapter()


def is_calculator_response(payload: dict[str, Any]) -> bool:
    return calculator_response_adapter.can_handle(payload)


def build_calculator_blocks(payload: dict[str, Any], content: str) -> list[ChatContentBlock]:
    return calculator_response_adapter.build_blocks(payload, content)


def first_structured_calculator_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("calculator_result", "structured_result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value

    result = payload.get("result")
    if isinstance(result, dict):
        nested = result.get("result")
        if isinstance(nested, dict):
            return nested
        if any(key in result for key in ("summary", "product", "inputs", "tax_breakdown", "phases")):
            return result

    return None


def blocks_from_structured_calculator_result(
    result: dict[str, Any],
    *,
    include_references: bool = True,
) -> list[ChatContentBlock]:
    blocks: list[ChatContentBlock] = []
    for block in (
        summary_block_from_structured_result(result),
        product_key_value_block(result),
        input_key_value_block(result),
        tax_breakdown_table(result),
        calculation_details_block(result),
        assumptions_details_block(result),
        references_block(result) if include_references else None,
    ):
        if block:
            blocks.append(block)
    return blocks


def blocks_from_legacy_calculator_content(payload: dict[str, Any], content: str) -> list[ChatContentBlock]:
    if not is_calculator_markdown_text(content):
        return []

    sections = parse_calculator_text_sections(content)
    if not sections:
        return []

    blocks: list[ChatContentBlock] = [summary_block_from_legacy_sections(sections, content)]
    for block in (
        product_key_value_block_from_legacy_sections(sections),
        input_key_value_block_from_legacy_sections(sections),
        tax_breakdown_table_from_legacy_content(content),
        calculation_details_block_from_legacy_sections(sections),
        assumptions_details_block_from_legacy_sections(sections, content, payload),
    ):
        if block:
            blocks.append(block)
    return blocks


def references_block(result: dict[str, Any]) -> ReferencesBlock | None:
    references = result.get("references") if isinstance(result.get("references"), list) else []
    if not references:
        return None
    return ReferencesBlock(
        title="References",
        items=dedupe_reference_items(
            [reference_item_from_value(item, index) for index, item in enumerate(references, start=1)]
        ),
    )


def has_top_level_citations(payload: dict[str, Any]) -> bool:
    citations = payload.get("citations") or payload.get("references")
    if not isinstance(citations, list):
        return False
    return any(
        isinstance(item, dict)
        or (isinstance(item, str) and bool(item.strip()))
        for item in citations
    )


def blocks_from_upstream_message(value: Any, *, include_references: bool = True) -> list[ChatContentBlock]:
    content = value.get("content") if isinstance(value, dict) else None
    if not isinstance(content, list):
        return []

    blocks: list[ChatContentBlock] = []
    for item in content:
        if not include_references and isinstance(item, dict) and item.get("type") == "references":
            continue
        block = block_from_upstream_message_item(item)
        if block:
            blocks.append(block)
    return blocks


def block_from_upstream_message_item(value: Any) -> ChatContentBlock | None:
    if not isinstance(value, dict):
        return None

    block_type = value.get("type")
    if block_type == "markdown":
        text = value.get("text") if isinstance(value.get("text"), str) else value.get("content")
        return MarkdownBlock(text=text) if isinstance(text, str) else None
    if block_type == "summary":
        return SummaryBlock(title=str(value.get("title") or "Summary"), data=scalar_mapping(value.get("data")))
    if block_type == "key_value":
        items = key_value_items_from_upstream(value.get("items"))
        return KeyValueBlock(title=str(value.get("title") or "Details"), items=items) if items else None
    if block_type == "table":
        return table_block_from_upstream_table(value)
    if block_type == "details":
        items = details_items_from_upstream(value.get("items"))
        data = value.get("data") if isinstance(value.get("data"), dict) else {}
        return DetailsBlock(title=str(value.get("title") or "Details"), items=items, data=data) if items or data else None
    if block_type == "references":
        items = reference_items_from_upstream(value.get("items"))
        return ReferencesBlock(title=value.get("title") or "References", items=items) if items else None
    if block_type == "clarification":
        questions = [item for item in value.get("questions", []) if isinstance(item, str)]
        return ClarificationBlock(title=value.get("title"), questions=questions) if questions else None
    if block_type == "error":
        message = value.get("message") if isinstance(value.get("message"), str) else None
        return ErrorBlock(message=message) if message else None
    return None


def key_value_items_from_upstream(value: Any) -> list[KeyValueItem]:
    if not isinstance(value, list):
        return []
    items: list[KeyValueItem] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or item.get("label") or item.get("name")
        if key is None:
            continue
        items.append(KeyValueItem(key=str(key), value=scalar_to_cell(item.get("value"))))
    return items


def details_items_from_upstream(value: Any) -> list[DetailsItem]:
    if not isinstance(value, list):
        return []
    items: list[DetailsItem] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            content = item.get("content") if isinstance(item.get("content"), str) else item.get("text")
            title = item.get("title") or item.get("name") or f"Detail {index}"
            if isinstance(content, str):
                items.append(DetailsItem(title=str(title), content=content))
        elif isinstance(item, str):
            items.append(DetailsItem(title=f"Detail {index}", content=item))
    return items


def reference_items_from_upstream(value: Any) -> list[dict[str, str | int | float | bool | None]]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, dict):
            normalized = scalar_mapping(item)
            if normalized:
                items.append(normalized)
    return items


def scalar_mapping(value: Any) -> dict[str, str | int | float | bool | None]:
    if not isinstance(value, dict):
        return {}
    return {str(key): cell for key, item in value.items() if (cell := scalar_to_cell(item)) is not None}
