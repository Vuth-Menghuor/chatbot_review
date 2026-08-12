from typing import Any

from app.schemas.normalized_chat import ChatTableColumn, TableBlock
from app.services.normalizers.calculator.extraction import extract_final_tax_breakdown_table
from app.services.normalizers.calculator.formatting import first_list, scalar_to_cell


def tax_breakdown_table(result: dict[str, Any]) -> TableBlock | None:
    tax_breakdown = result.get("tax_breakdown") if isinstance(result.get("tax_breakdown"), list) else []
    if not tax_breakdown:
        return None
    return calculator_table_from_rows("Tax Breakdown", tax_breakdown)


def tax_breakdown_table_from_legacy_content(content: str) -> TableBlock | None:
    table_section = extract_final_tax_breakdown_table(content)
    if not table_section:
        return None
    table_section.table.title = "Tax Breakdown"
    return table_section.table


def table_block_from_upstream_table(value: Any) -> TableBlock | None:
    block = normalize_calculator_table(value)
    if block:
        block.title = block.title or "Tax Breakdown"
    return block


def normalize_calculator_table(value: Any) -> TableBlock | None:
    if not isinstance(value, dict):
        return None

    rows = first_list(value, "rows", "data", "records", "items")
    block = calculator_table_from_rows(value.get("title") or value.get("name"), rows, columns=value.get("columns"))
    return block


def calculator_table_from_rows(title: Any, rows: list[Any], *, columns: Any = None) -> TableBlock | None:
    normalized_rows: list[dict[str, str | int | float | bool | None]] = []
    column_keys: list[str] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized_row: dict[str, str | int | float | bool | None] = {}
        for key, value in row.items():
            normalized_key = str(key)
            normalized_row[normalized_key] = scalar_to_cell(value)
            if normalized_key not in column_keys:
                column_keys.append(normalized_key)
        if normalized_row:
            normalized_rows.append(normalized_row)

    normalized_columns = calculator_table_columns(columns, column_keys)
    if not normalized_columns and not normalized_rows:
        return None
    return TableBlock(title=str(title) if title else None, columns=normalized_columns, rows=normalized_rows)


def calculator_table_columns(columns: Any, inferred_keys: list[str]) -> list[ChatTableColumn]:
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
    if normalized_columns:
        return normalized_columns
    return [ChatTableColumn(key=key, label=key) for key in inferred_keys]
