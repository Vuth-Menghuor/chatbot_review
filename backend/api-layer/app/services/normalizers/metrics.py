from __future__ import annotations

from typing import Any

from app.schemas.normalized_chat import ChatTableColumn, TableBlock
from app.services.normalizers.tables import scalar_to_cell


# Summary metrics are rendered as compact key/value tables, separate from general data tables.


# Convert summary dictionaries into a compact table card that the frontend can scan quickly.
def normalize_summary_metrics(value: Any) -> TableBlock | None:
    if not isinstance(value, dict) or not value:
        return None
    rows = [{"metric": str(key).replace("_", " ").title(), "value": summary_metric_cell(item)} for key, item in value.items()]
    return TableBlock(
        title="Summary Metrics",
        columns=[
            ChatTableColumn(key="metric", label="Metric"),
            ChatTableColumn(key="value", label="Value"),
        ],
        rows=rows,
    )


# Preserve important metric notes while still flattening nested metrics into displayable scalar cells.
def summary_metric_cell(value: Any) -> str | int | float | bool | None:
    if isinstance(value, dict):
        note = value.get("truncation_note") or value.get("period_coverage_note")
        if note:
            return str(note)

        parts = []
        for key, item in value.items():
            if item is None:
                continue
            label = str(key).replace("_", " ").title()
            parts.append(f"{label}: {item}")
        return "; ".join(parts) if parts else None
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return scalar_to_cell(value)
