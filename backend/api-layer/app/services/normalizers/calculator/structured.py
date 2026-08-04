from typing import Any

from app.schemas.normalized_chat import (
    ChatContentBlock,
    DetailsBlock,
    DetailsItem,
    KeyValueBlock,
    ReferencesBlock,
    SummaryBlock,
)
from app.services.normalizers.calculator.citations import dedupe_reference_items, reference_item_from_value
from app.services.normalizers.calculator.extraction import extract_final_tax_breakdown_table
from app.services.normalizers.calculator.formatting import (
    is_calculator_markdown_text,
    key_value_items_from_bullets,
    key_value_items_from_mapping,
    normalize_markdown_content_blocks,
    normalize_table,
    scalar_to_cell,
)
from app.services.normalizers.calculator.legacy import (
    assumptions_block_from_sections,
    calculator_report_title,
    calculator_summary_data,
    details_items_from_list,
    details_items_from_sections,
    parse_calculator_text_sections,
)


# Keep the calculator entry point compatible while routing structured and legacy payloads to smaller modules.
def normalize_structured_calculator_blocks(payload: dict[str, Any], content: str) -> list[ChatContentBlock]:
    structured = first_structured_calculator_result(payload)
    if structured:
        return blocks_from_structured_calculator_result(structured)

    if not is_calculator_markdown_text(content):
        return []

    sections = parse_calculator_text_sections(content)
    if not sections:
        return []

    blocks: list[ChatContentBlock] = []
    summary_data = calculator_summary_data(sections, content)
    blocks.append(SummaryBlock(title=calculator_report_title(sections), data=summary_data))

    product_items = key_value_items_from_bullets(sections.get("PRODUCT INFORMATION", []))
    if product_items:
        blocks.append(KeyValueBlock(title="Product Information", items=product_items))

    input_items = key_value_items_from_bullets(sections.get("INPUT PARAMETERS", []))
    if input_items:
        blocks.append(KeyValueBlock(title="Input Parameters", items=input_items))

    table_section = extract_final_tax_breakdown_table(content)
    if table_section:
        table_section.table.title = "Tax Breakdown"
        blocks.append(table_section.table)

    detail_items = details_items_from_sections(sections)
    if detail_items:
        blocks.append(DetailsBlock(title="Calculation Details", items=detail_items))

    assumption_block = assumptions_block_from_sections(sections, content, payload)
    if assumption_block:
        blocks.append(assumption_block)

    return blocks


# Detect structured calculator results from all existing orchestrator payload shapes.
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


# Convert structured calculator business data into the existing frontend block sequence.
def blocks_from_structured_calculator_result(result: dict[str, Any]) -> list[ChatContentBlock]:
    blocks: list[ChatContentBlock] = []
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    product = result.get("product") if isinstance(result.get("product"), dict) else {}
    inputs = result.get("inputs") if isinstance(result.get("inputs"), dict) else {}
    tax_breakdown = result.get("tax_breakdown") if isinstance(result.get("tax_breakdown"), list) else []
    phases = result.get("phases") if isinstance(result.get("phases"), list) else []
    references = result.get("references") if isinstance(result.get("references"), list) else []
    assumptions = result.get("assumptions") if isinstance(result.get("assumptions"), list) else []

    blocks.append(SummaryBlock(title="Import Tax Calculation", data={key: scalar_to_cell(value) for key, value in summary.items()}))
    if product:
        blocks.append(KeyValueBlock(title="Product Information", items=key_value_items_from_mapping(product)))
    if inputs:
        blocks.append(KeyValueBlock(title="Input Parameters", items=key_value_items_from_mapping(inputs)))
    if tax_breakdown:
        table = normalize_table({
            "title": "Tax Breakdown",
            "columns": [
                {"key": "component", "label": "Tax Component"},
                {"key": "tax_base", "label": "Tax base"},
                {"key": "rate", "label": "Rate"},
                {"key": "amount", "label": "Amount"},
                {"key": "currency", "label": "Currency"},
            ],
            "rows": tax_breakdown,
        })
        if table:
            blocks.append(table)
    detail_items = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        title = str(phase.get("name") or phase.get("title") or "Calculation")
        lines = phase.get("lines") if isinstance(phase.get("lines"), list) else []
        content_lines = []
        if phase.get("basis"):
            content_lines.append(f"Basis: {phase['basis']}")
        if phase.get("total") is not None:
            content_lines.append(f"Total: {phase['total']} {phase.get('currency') or ''}".strip())
        for line in lines:
            if isinstance(line, dict):
                content_lines.append(" - ".join(str(value) for value in line.values() if value is not None))
        if content_lines:
            detail_items.append(DetailsItem(title=title, content="\n".join(content_lines)))
    if detail_items:
        blocks.append(DetailsBlock(title="Calculation Details", items=detail_items))
    assumption_items = details_items_from_list(assumptions, fallback_title="Notes")
    if assumption_items:
        blocks.append(DetailsBlock(title="Assumptions & Notes", items=assumption_items))
    if references:
        blocks.append(
            ReferencesBlock(
                title="References",
                items=dedupe_reference_items(
                    [reference_item_from_value(item, index) for index, item in enumerate(references, start=1)]
                ),
            )
        )
    return blocks
