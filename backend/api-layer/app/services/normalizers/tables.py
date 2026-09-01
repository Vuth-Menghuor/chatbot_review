from __future__ import annotations

from typing import Any

from app.schemas.normalized_chat import ChatTableColumn, TableBlock


# Table blocks normalize tabular payloads into the frontend renderer contract.


# Keep generic table payload handling here so the main response normalizer only decides when to render a table.
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
                label = table_column_label(key, column.get("label") or column.get("title"))
            else:
                key = str(column)
                label = table_column_label(key, None)
            if key:
                normalized_columns.append(ChatTableColumn(key=key, label=label))

    if not normalized_columns and rows and isinstance(rows[0], dict):
        normalized_columns = [ChatTableColumn(key=str(key), label=table_column_label(str(key), None)) for key in rows[0]]

    normalized_rows = normalize_table_rows(rows, normalized_columns)
    if not normalized_columns and not normalized_rows:
        return None

    return TableBlock(
        title=table_title(value, normalized_columns),
        columns=normalized_columns,
        rows=normalized_rows,
    )


# Convert machine field names into labels only when the upstream service did not provide a better label.
def table_column_label(key: str, label: Any) -> str:
    clean_label = str(label or "").strip()
    if clean_label and clean_label.lower() != key.strip().lower():
        return clean_label
    return key.replace("_", " ").strip().title() or "Value"


# A table without a heading is hard to scan in a chat response. Prefer the upstream title,
# then infer a concise domain title from stable column names.
def table_title(value: dict[str, Any], columns: list[ChatTableColumn]) -> str:
    for key in ("title", "name"):
        title = value.get(key)
        if isinstance(title, str) and title.strip():
            return title.strip()

    keys = {column.key.strip().lower() for column in columns}
    if "partner_country" in keys:
        return "Trade Partners"
    if "hs_code" in keys:
        return "HS Code Results"
    if {"component", "amount"}.issubset(keys):
        return "Tax Breakdown"
    if "commodity" in keys:
        return "Commodity Results"
    if "flow" in keys:
        return "Trade Values"
    return "Results"


def normalize_table_rows(rows: list[Any], columns: list[ChatTableColumn]) -> list[dict[str, str | int | float | bool | None]]:
    normalized_rows: list[dict[str, str | int | float | bool | None]] = []
    for row in rows:
        if isinstance(row, dict):
            normalized_rows.append(row)
        elif isinstance(row, list | tuple) and columns:
            normalized_rows.append(
                {
                    column.key: scalar_to_cell(row[index]) if index < len(row) else None
                    for index, column in enumerate(columns)
                }
            )
    return normalized_rows


# Collect every table-like payload shape the orchestrator may send before converting each one into a TableBlock.
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


# Convert document search matches into a predictable HS-code table for the frontend.
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


# Convert calculator tax line items into a stable table shape with known columns.
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


# Reuse this small picker anywhere a payload may name row data with different keys.
def first_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


# Keep table cells JSON-safe because the normalized schema only accepts scalar values.
def scalar_to_cell(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)
