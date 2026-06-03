"""Intent-to-visualization mapping configurations registry."""

from typing import Dict, Any

VISUALIZATION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "ranking": {
        "type": "bar",
        "label_col": "PARTNER_COUNTRY",
        "value_col": "VALUE_USD",
        "title": "Top Trading Partners",
        "dataset_label": "Trade Value (USD)",
    },
    "trend": {
        "type": "line",
        "label_col": "PERIOD",
        "value_col": "VALUE_USD",
        "title": "Trade Trend over Time",
        "dataset_label": "Trade Value (USD)",
    },
    "comparison": {
        "type": "bar",
        "label_col": "PARTNER_COUNTRY",
        "value_col": "VALUE_USD",
        "title": "Trade Comparison",
        "dataset_label": "Trade Value (USD)",
    },
    "breakdown": {
        "type": "pie",
        "label_col": "HS_CHAPTER",
        "value_col": "VALUE_USD",
        "title": "Trade Breakdown by Product",
        "dataset_label": "Trade Value (USD)",
    },
    "growth": {
        "type": "bar",
        "label_col": "PARTNER_COUNTRY",
        "value_col": "VALUE_USD",
        "title": "Trade Growth",
        "dataset_label": "Trade Value (USD)",
    },
    "trade_balance": {
        "type": "bar",
        "label_col": "FLOW",
        "value_col": "VALUE_USD",
        "title": "Trade Balance Summary",
        "dataset_label": "Trade Value (USD)",
    },
    "summary": {
        "type": "pie",
        "label_col": "FLOW",
        "value_col": "VALUE_USD",
        "title": "Trade Summary",
        "dataset_label": "Trade Value (USD)",
    },
}
