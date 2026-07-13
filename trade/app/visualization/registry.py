"""Intent-to-visualization mapping configurations registry."""

from typing import Any, Dict

VISUALIZATION_REGISTRY: Dict[str, Dict[str, Any]] = {
    "ranking": {
        "type": "bar",
        "label_col": "PARTNER_COUNTRY",
        "value_col": "VALUE_USD",
        "title": "Trade Volume Ranking",
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
        "title": "Trade Comparison Analysis",
        "dataset_label": "Trade Value (USD)",
    },
    "breakdown": {
        "type": "pie",
        "label_col": "HS_CHAPTER",
        "value_col": "VALUE_USD",
        "title": "Trade Share Breakdown",
        "dataset_label": "Trade Value (USD)",
    },
    "growth": {
        "type": "bar",
        "label_col": "PARTNER_COUNTRY",
        "value_col": "growth_rate_pct",
        "title": "Trade Growth Analysis",
        "dataset_label": "Growth Rate (%)",
    },
    "trade_balance": {
        "type": "bar",
        "label_col": "FLOW",
        "value_col": "VALUE_USD",
        "title": "Trade Balance Analysis",
        "dataset_label": "Trade Value (USD)",
    },
    "summary": {
        "type": "pie",
        "label_col": "FLOW",
        "value_col": "VALUE_USD",
        "title": "Trade Volume Summary",
        "dataset_label": "Trade Value (USD)",
    },
}
