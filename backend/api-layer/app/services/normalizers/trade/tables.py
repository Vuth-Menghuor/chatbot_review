from typing import Any

from app.schemas.normalized_chat import ChatTableColumn, TableBlock
from app.services.normalizers.tables import scalar_to_cell


# Build the top export partners table from structured partner rows.
def normalize_top_export_partners_table(result: dict[str, Any]) -> TableBlock | None:
    rows = first_list(result, "top_export_partners", "export_partners", "partners")
    if not rows:
        return None
    return table_from_rows(
        "Top Export Partners",
        rows,
        [
            ("rank", "Rank"),
            ("partner_country", "Partner Country"),
            ("value_usd", "Value USD"),
            ("share_percent", "Share Percent"),
            ("period", "Period"),
        ],
    )


# Build an import/export values table from rows or a compact import/export dictionary.
def normalize_import_export_values_table(result: dict[str, Any]) -> TableBlock | None:
    value = result.get("import_export_values") or result.get("trade_values")
    if isinstance(value, dict):
        rows = [{"flow": key, "value_usd": item} for key, item in value.items()]
    elif isinstance(value, list):
        rows = value
    else:
        rows = []
    if not rows:
        return None
    return table_from_rows(
        "Import/Export Values",
        rows,
        [
            ("flow", "Flow"),
            ("value_usd", "Value USD"),
            ("quantity", "Quantity"),
            ("unit", "Unit"),
            ("period", "Period"),
        ],
    )


# Build a generic trade ranking table for ranked commodities, countries, or flows.
def normalize_trade_ranking_table(result: dict[str, Any]) -> TableBlock | None:
    rows = first_list(result, "ranking", "rankings", "records")
    if not rows:
        return None
    return table_from_rows(
        "Trade Ranking",
        rows,
        [
            ("rank", "Rank"),
            ("item", "Item"),
            ("commodity", "Commodity"),
            ("partner_country", "Partner Country"),
            ("flow", "Flow"),
            ("value_usd", "Value USD"),
            ("period", "Period"),
        ],
    )


# Convert row dictionaries into stable columns while preserving extra structured fields at the end.
def table_from_rows(title: str, rows: list[Any], preferred_columns: list[tuple[str, str]]) -> TableBlock | None:
    normalized_rows = [normalize_row(row) for row in rows if isinstance(row, dict)]
    normalized_rows = [row for row in normalized_rows if any(value is not None for value in row.values())]
    if not normalized_rows:
        return None

    preferred_keys = [key for key, _ in preferred_columns]
    discovered_keys = list(dict.fromkeys(key for row in normalized_rows for key in row))
    ordered_keys = [key for key in preferred_keys if key in discovered_keys]
    ordered_keys.extend(key for key in discovered_keys if key not in ordered_keys)
    labels = dict(preferred_columns)

    return TableBlock(
        title=title,
        columns=[ChatTableColumn(key=key, label=labels.get(key, default_label(key))) for key in ordered_keys],
        rows=normalized_rows,
    )


# Keep table rows JSON-safe for the normalized response schema.
def normalize_row(row: dict[str, Any]) -> dict[str, str | int | float | bool | None]:
    return {str(key): scalar_to_cell(value) for key, value in row.items()}


# Pick the first list-valued trade result key.
def first_list(payload: dict[str, Any], *keys: str) -> list[Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


# Convert snake_case fields into readable table labels.
def default_label(key: str) -> str:
    return key.replace("_", " ").title()
