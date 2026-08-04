from typing import Any

from app.schemas.normalized_chat import ChatContentBlock, CoverageBlock, ReferencesBlock, SummaryBlock
from app.services.normalizers.tables import scalar_to_cell
from app.services.normalizers.trade.citations import normalize_trade_references
from app.services.normalizers.trade.tables import (
    normalize_import_export_values_table,
    normalize_top_export_partners_table,
    normalize_trade_ranking_table,
)


# Find structured trade data in the common payload shapes returned by the orchestrator and direct trade service.
def first_structured_trade_result(payload: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("trade_result", "trade_data"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value

    result = payload.get("result")
    if isinstance(result, dict):
        nested = result.get("result")
        if isinstance(nested, dict) and is_trade_result(nested):
            return nested
        if is_trade_result(result):
            return result

    return None


# Detect trade result dictionaries by structured data keys instead of brittle answer text.
def is_trade_result(value: dict[str, Any]) -> bool:
    return any(
        key in value
        for key in (
            "top_export_partners",
            "export_partners",
            "import_export_values",
            "trade_values",
            "ranking",
            "rankings",
            "records",
            "missing",
            "missing_data",
        )
    )


# Convert structured trade data into the existing reusable UI blocks.
def normalize_structured_trade_blocks(payload: dict[str, Any]) -> list[ChatContentBlock]:
    result = first_structured_trade_result(payload)
    if not result:
        return []

    blocks: list[ChatContentBlock] = []
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    if summary:
        blocks.append(SummaryBlock(title="Trade Data Summary", data={key: scalar_to_cell(value) for key, value in summary.items()}))

    for table in (
        normalize_top_export_partners_table(result),
        normalize_import_export_values_table(result),
        normalize_trade_ranking_table(result),
    ):
        if table:
            blocks.append(table)

    missing_items = normalize_missing_trade_data(result)
    if missing_items:
        blocks.append(
            CoverageBlock(
                title="Missing Trade Data",
                tone="warning",
                items=missing_items,
                note="The available trade dataset does not include every requested value.",
            )
        )

    references = normalize_trade_references(result.get("references") or result.get("citations") or result.get("sources"))
    if references:
        blocks.append(ReferencesBlock(title="References", items=references))

    return blocks


# Normalize missing-data messages from strings, lists, or structured dictionaries.
def normalize_missing_trade_data(value: dict[str, Any]) -> list[str]:
    missing = value.get("missing_data") or value.get("missing")
    if missing is None:
        return []
    if isinstance(missing, str):
        return [missing] if missing.strip() else []
    if isinstance(missing, list):
        return [str(item) for item in missing if str(item).strip()]
    if isinstance(missing, dict):
        items = []
        for key, item in missing.items():
            if item is None:
                continue
            label = str(key).replace("_", " ").title()
            items.append(f"{label}: {item}")
        return items
    return [str(missing)] if str(missing).strip() else []
