from typing import Any

from app.schemas.normalized_chat import DetailsBlock, DetailsItem
from app.services.normalizers.calculator.formatting import scalar_to_cell
from app.services.normalizers.calculator.legacy import (
    assumptions_block_from_sections,
    details_items_from_sections,
)


def calculation_details_block(result: dict[str, Any]) -> DetailsBlock | None:
    phases = result.get("phases") if isinstance(result.get("phases"), list) else []
    detail_items = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        title = str(phase.get("name") or phase.get("title") or "Calculation")
        lines = phase.get("lines") if isinstance(phase.get("lines"), list) else []
        content_lines = []
        for key, value in phase.items():
            if key in {"lines", "name", "title"}:
                continue
            cell = scalar_to_cell(value)
            if cell is not None:
                content_lines.append(f"{key}: {cell}")
        for line in lines:
            if isinstance(line, dict):
                line_values = []
                for key, value in line.items():
                    cell = scalar_to_cell(value)
                    if cell is not None:
                        line_values.append(f"{key}: {cell}")
                if line_values:
                    content_lines.append("\n".join(line_values))
        if content_lines:
            detail_items.append(DetailsItem(title=title, content="\n".join(content_lines)))
    return DetailsBlock(title="Calculation Details", items=detail_items) if detail_items else None


def assumptions_details_block(result: dict[str, Any]) -> DetailsBlock | None:
    assumptions = result.get("assumptions") if isinstance(result.get("assumptions"), list) else []
    items = details_items_from_list(assumptions, fallback_title="Notes")
    return DetailsBlock(title="Assumptions & Notes", items=items) if items else None


def calculation_details_block_from_legacy_sections(sections: dict[str, list[str]]) -> DetailsBlock | None:
    items = details_items_from_sections(sections)
    return DetailsBlock(title="Calculation Details", items=items) if items else None


def assumptions_details_block_from_legacy_sections(
    sections: dict[str, list[str]],
    content: str,
    payload: dict[str, Any],
) -> DetailsBlock | None:
    return assumptions_block_from_sections(sections, content, payload)


def details_items_from_list(items: list[Any], *, fallback_title: str) -> list[DetailsItem]:
    details: list[DetailsItem] = []
    for index, item in enumerate(items, start=1):
        if isinstance(item, dict):
            content = scalar_to_cell(item.get("content") or item.get("text") or item.get("note"))
            title = scalar_to_cell(item.get("title") or item.get("name")) or fallback_title
        else:
            content = scalar_to_cell(item)
            title = fallback_title if index == 1 else f"{fallback_title} {index}"
        if content:
            details.append(DetailsItem(title=title, content=content))
    return details
