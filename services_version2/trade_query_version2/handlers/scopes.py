"""
Trade Query Scopes — data and visualization scope definitions.

This module maps the three official scopes from the trade query specification
into constants and helpers used by intent strategies and the normaliser.

IMPORTANT: The DAL API dimension/measure support is not fully documented.
The lists below are derived from:
1. What the existing DAL request builder actually maps (proven)
2. What the scope document says should exist (aspirational)

Proven DAL dimensions (used by _map_group_dimension in dal_request_builder.py):
    PARTNER_COUNTRY, FLOW, HS_CODE, MODE_OF_TRANSPORT

Proven DAL measures (used as defaults in dal_request_builder.py):
    VALUE_USD, NET_WEIGHT

Aspirational dimensions/measures (not yet proven against the live DAL):
    PERIOD, COUNTRY, QUANTITY, GROWTH_RATE, MARKET_SHARE

If the live DAL returns a 4xx when these are used, fall back to the proven set.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 1. Query Scope — already represented by STRATEGIES in strategies.py
# ---------------------------------------------------------------------------

QUERY_INTENTS: list[str] = [
    "summary",
    "ranking",
    "trend",
    "comparison",
    "breakdown",
    "growth",
    "trade_balance",
]

# ---------------------------------------------------------------------------
# 2. Data Scope — PROVEN dimensions / measures the DAL client actually knows
# ---------------------------------------------------------------------------

PROVEN_DIMENSIONS: list[str] = [
    "PARTNER_COUNTRY",
    "FLOW",
    "HS_CHAPTER",
    "HS_HEADING",
    "MODE_OF_TRANSPORT",
]

# PERIOD and COUNTRY are aspirational — used by strategies for grouping
# but not guaranteed to be accepted by the live DAL.
ASPIRATIONAL_DIMENSIONS: list[str] = [
    "PERIOD",
    "COUNTRY",
]

DIMENSIONS: list[str] = PROVEN_DIMENSIONS + ASPIRATIONAL_DIMENSIONS

PROVEN_MEASURES: list[str] = [
    "VALUE_USD",
    "NET_WEIGHT",
]

# Aspirational measures — the DAL may or may not support these.
# If a DAL call fails with these, retry with PROVEN_MEASURES only.
ASPIRATIONAL_MEASURES: list[str] = [
    "QUANTITY",
    "GROWTH_RATE",
    "MARKET_SHARE",
]

MEASURES: list[str] = PROVEN_MEASURES + ASPIRATIONAL_MEASURES

CAPABILITIES: list[str] = [
    "filtering",
    "grouping",
    "aggregation",
    "sorting",
    "pagination",
    "period_selection",
]

# ---------------------------------------------------------------------------
# 3. Visualization Scope — how results may be shown
# ---------------------------------------------------------------------------

VISUALIZATION_TYPES: list[str] = [
    "table",
    "bar_chart",
    "line_chart",
    "pie_chart",
]

# ---------------------------------------------------------------------------
# Per-intent configurations
# ---------------------------------------------------------------------------

# Visualizations that make sense for each intent (frontend hint)
INTENT_VISUALIZATIONS: dict[str, list[str]] = {
    "summary":    ["table", "pie_chart"],
    "ranking":    ["bar_chart", "table"],
    "trend":      ["line_chart", "table"],
    "comparison": ["bar_chart", "table"],
    "breakdown":  ["pie_chart", "table"],
    "growth":     ["bar_chart", "line_chart", "table"],
    "trade_balance": ["bar_chart", "table"],
}

# Default measures per intent.
# Each list starts with proven measures, followed by aspirational ones.
# The DAL client will attempt all of them; if the DAL rejects aspirational
# measures, the caller can fall back to PROVEN_MEASURES only.
INTENT_MEASURES: dict[str, list[str]] = {
    "summary":    ["VALUE_USD", "NET_WEIGHT"],
    "ranking":    ["VALUE_USD", "NET_WEIGHT"],
    "trend":      ["VALUE_USD", "NET_WEIGHT"],
    "comparison": ["VALUE_USD", "NET_WEIGHT"],
    "breakdown":  ["VALUE_USD", "NET_WEIGHT"],
    "growth":     ["VALUE_USD", "NET_WEIGHT"],
    "trade_balance": ["VALUE_USD", "NET_WEIGHT"],
}


@dataclass
class ScopeConfig:
    """Full scope configuration for a single intent."""

    intent: str
    dimensions: list[str] = field(default_factory=list)
    measures: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    visualizations: list[str] = field(default_factory=list)


def get_scope_config(intent: str) -> ScopeConfig:
    """Return the full data + visualization scope for an intent."""
    return ScopeConfig(
        intent=intent,
        dimensions=DIMENSIONS,
        measures=INTENT_MEASURES.get(intent, PROVEN_MEASURES),
        capabilities=CAPABILITIES,
        visualizations=INTENT_VISUALIZATIONS.get(intent, ["table"]),
    )
