"""Intent strategy definitions."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.handlers.scopes import INTENT_MEASURES, INTENT_VISUALIZATIONS


@dataclass
class IntentStrategy:
    """Configuration for a single query intent."""

    name: str
    default_metrics: list[str] = field(default_factory=lambda: ["VALUE_USD", "NET_WEIGHT"])
    default_group_by: list[str] = field(default_factory=list)
    default_dimensions: list[str] = field(default_factory=list)
    default_sort: str | None = None
    default_limit: int = 1000
    default_frequency: str | None = None
    description: str = ""
    suggested_visualizations: list[str] = field(default_factory=list)


STRATEGIES: dict[str, IntentStrategy] = {
    "summary": IntentStrategy(
        name="summary",
        default_metrics=INTENT_MEASURES["summary"],
        default_group_by=["FLOW"],
        default_dimensions=["FLOW"],
        description="Total trade value/weight for a given period and filters.",
        suggested_visualizations=INTENT_VISUALIZATIONS["summary"],
    ),
    "ranking": IntentStrategy(
        name="ranking",
        default_metrics=INTENT_MEASURES["ranking"],
        default_group_by=["PARTNER_COUNTRY"],
        default_dimensions=["PARTNER_COUNTRY"],
        default_sort="VALUE_USD:desc",
        default_limit=10,
        description="Top N partner countries by trade value.",
        suggested_visualizations=INTENT_VISUALIZATIONS["ranking"],
    ),
    "trend": IntentStrategy(
        name="trend",
        default_metrics=INTENT_MEASURES["trend"],
        default_group_by=["PERIOD", "FLOW"],
        default_dimensions=["PERIOD", "FLOW"],
        default_frequency="M",
        description="Monthly or quarterly trade trends over time.",
        suggested_visualizations=INTENT_VISUALIZATIONS["trend"],
    ),
    "comparison": IntentStrategy(
        name="comparison",
        default_metrics=INTENT_MEASURES["comparison"],
        default_group_by=["PARTNER_COUNTRY", "FLOW"],
        default_dimensions=["PARTNER_COUNTRY", "FLOW"],
        default_sort="VALUE_USD:desc",
        description="Side-by-side comparison of two or more partner countries.",
        suggested_visualizations=INTENT_VISUALIZATIONS["comparison"],
    ),
    "breakdown": IntentStrategy(
        name="breakdown",
        default_metrics=INTENT_MEASURES["breakdown"],
        default_group_by=["HS_CHAPTER"],
        default_dimensions=["HS_CHAPTER"],
        default_sort="VALUE_USD:desc",
        default_limit=20,
        description="Trade value broken down by HS code.",
        suggested_visualizations=INTENT_VISUALIZATIONS["breakdown"],
    ),
    "growth": IntentStrategy(
        name="growth",
        default_metrics=INTENT_MEASURES["growth"],
        default_group_by=["PARTNER_COUNTRY"],
        default_dimensions=["PARTNER_COUNTRY"],
        default_sort="VALUE_USD:desc",
        default_limit=10,
        description="Countries with highest year-over-year export/import growth.",
        suggested_visualizations=INTENT_VISUALIZATIONS["growth"],
    ),
    "trade_balance": IntentStrategy(
        name="trade_balance",
        default_metrics=INTENT_MEASURES["trade_balance"],
        default_group_by=["FLOW"],
        default_dimensions=["FLOW"],
        description="Export vs import balance for a specific partner country.",
        suggested_visualizations=INTENT_VISUALIZATIONS["trade_balance"],
    ),
}
