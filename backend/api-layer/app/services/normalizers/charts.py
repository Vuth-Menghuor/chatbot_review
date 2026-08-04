from __future__ import annotations

import re
from typing import Any

from app.schemas.normalized_chat import ChartBlock
from app.services.normalizers.tables import scalar_to_cell


# Chart blocks normalize visualization payloads into the frontend chart renderer contract.


# Keep chart payload handling outside the main normalizer so chart renderer changes stay isolated.
def normalize_chart(value: Any) -> ChartBlock | None:
    if not isinstance(value, dict) or not value:
        return None
    title = value.get("title")
    return ChartBlock(title=title, data=normalize_chart_data(value, title=title))


# Convert common chart formats into the frontend's row-and-series chart contract.
def normalize_chart_data(value: dict[str, Any], *, title: Any = None) -> dict[str, Any]:
    chart_type = normalize_chart_type(value.get("type") or value.get("chartType"))
    chart_title = title or value.get("title")

    labels = value.get("labels")
    datasets = value.get("datasets")
    if isinstance(labels, list) and isinstance(datasets, list):
        normalized_labels = [str(label) for label in labels]
        normalized_datasets = [dataset for dataset in datasets if isinstance(dataset, dict)]
        render_type = "bar" if chart_type == "line" and len(normalized_labels) < 2 else chart_type
        rows: list[dict[str, str | int | float | bool | None]] = []

        for index, label in enumerate(normalized_labels):
            row: dict[str, str | int | float | bool | None] = {"label": label}
            for dataset_index, dataset in enumerate(normalized_datasets):
                key = chart_series_key(dataset, dataset_index)
                data_values = dataset.get("data") if isinstance(dataset.get("data"), list) else []
                value_at_index = data_values[index] if index < len(data_values) else 0
                row[key] = numeric_cell(value_at_index)
            rows.append(row)

        return {
            "title": scalar_to_cell(chart_title),
            "chartType": render_type,
            "xKey": "label",
            "xLabel": "Label",
            "yLabel": scalar_to_cell(normalized_datasets[0].get("label")) if normalized_datasets else None,
            "data": rows,
            "series": [
                {
                    "key": chart_series_key(dataset, index),
                    "name": str(dataset.get("label") or f"Series {index + 1}"),
                    "color": chart_color(index),
                    "type": "line" if render_type == "line" else "bar",
                }
                for index, dataset in enumerate(normalized_datasets)
            ],
        }

    normalized = dict(value)
    normalized["title"] = scalar_to_cell(chart_title)
    normalized["chartType"] = chart_type
    normalized.pop("type", None)
    return normalized


# Normalize backend chart aliases so the frontend receives one consistent chart type vocabulary.
def normalize_chart_type(value: Any) -> str:
    chart_type = str(value or "bar").lower()
    if chart_type == "horizontalbar":
        return "horizontal-bar"
    if chart_type == "doughnut":
        return "donut"
    return chart_type


# Build stable data keys from dataset labels so chart rows and series can reference the same field.
def chart_series_key(dataset: dict[str, Any], index: int) -> str:
    label = str(dataset.get("label") or f"series_{index + 1}").strip().lower()
    key = re.sub(r"[^a-z0-9]+", "_", label).strip("_")
    return key or f"series_{index + 1}"


# Assign deterministic colors so repeated chart renders do not visually reshuffle series.
def chart_color(index: int) -> str:
    colors = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2"]
    return colors[index % len(colors)]


# Coerce chart data points to numbers because chart libraries expect numeric y-values.
def numeric_cell(value: Any) -> int | float:
    if isinstance(value, int | float):
        return value
    try:
        return float(str(value or 0))
    except (TypeError, ValueError):
        return 0
