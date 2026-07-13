"""Semantic Metadata Registry: Bridge between natural language and DAL API.

Organized into three layers:
1. STRUCTURE: What fields and types actually exist.
2. SEMANTIC: Human language synonyms, labels, and aliases.
3. INTENT_RULES: Routing logic and validation constraints per intent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.registry.transport_modes import TRANSPORT_MODE_SYNONYMS


@dataclass
class StructureField:
    code: str
    field_type: str  # "dimension", "measure", "time"
    system: Optional[str] = None
    level: int = 1
    parent: Optional[str] = None
    unit: Optional[str] = None
    values: Optional[List[str]] = None
    patterns: Optional[List[str]] = None
    default: Optional[str] = None
    description: Optional[str] = None


@dataclass
class SemanticField:
    code: str
    synonyms: List[str] = field(default_factory=list)
    values_map: Dict[str, List[str]] = field(default_factory=dict)
    triggers: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)


@dataclass
class IntentRule:
    intent: str
    required_dimensions: List[str] = field(default_factory=list)
    optional_dimensions: List[str] = field(default_factory=list)
    supports_group_by: List[str] = field(default_factory=list)
    required_time: bool = False
    min_partner_countries: int = 0


# ---------------------------------------------------------------------------
# 1. Structure Layer
# ---------------------------------------------------------------------------
STRUCTURE: Dict[str, Dict[str, Any]] = {
    "dimensions": {
        "FLOW": {
            "system": "flow",
            "level": 1,
            "parent": None,
            "values": ["EX", "IM"],
            "description": "Trade flow direction, import (IM) or export (EX)",
        },
        "PARTNER_COUNTRY": {
            "system": "iso2",
            "level": 1,
            "parent": None,
            "description": "Partner country code in ISO-3166-1 alpha-2 format",
        },
        "MODE_OF_TRANSPORT": {
            "system": "mot",
            "level": 1,
            "parent": None,
            "values": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
            "description": "Mode of transport classification (e.g. 1=Sea, 3=Road, 4=Air)",
        },
        "HS_CHAPTER": {
            "system": "HS",
            "level": 1,
            "parent": None,
            "description": "Top-level HS commodity classification (2-digit)",
        },
        "HS_HEADING": {
            "system": "HS",
            "level": 2,
            "parent": "HS_CHAPTER",
            "description": "Four-digit HS commodity classification heading",
        },
        "SITC_SECTION": {
            "system": "SITC",
            "level": 1,
            "parent": None,
            "description": "Standard International Trade Classification section (1-digit)",
        },
        "SITC_DIVISION": {
            "system": "SITC",
            "level": 2,
            "parent": "SITC_SECTION",
            "description": "Standard International Trade Classification division detail (2-digit)",
        },
    },
    "measures": {
        "VALUE_USD": {
            "unit": "USD",
            "description": "Trade value in United States Dollars",
        },
        "VALUE_KHR": {
            "unit": "KHR",
            "description": "Trade value in Cambodian Riel",
        },
        "NET_WEIGHT": {
            "unit": "KGM",
            "description": "Net weight of trade goods in kilograms",
        },
        "QUANTITY": {
            "unit": "dynamic",
            "description": "Physical quantity of trade goods",
        },
        "QUANTITY.UNIT": {
            "unit": "string",
            "description": "Unit of measurement for the physical quantity",
        },
    },
    "time": {
        "PERIOD": {
            "patterns": ["YYYY", "YYYY-Qn", "YYYY-MM", "YYYY-Sn"],
            "description": "Time period of the data point, formatted according to the frequency",
        },
        "FREQUENCY": {
            "values": ["A", "M", "Q", "S"],
            "default": "A",
            "description": "Frequency of the data point (A=Annual, M=Monthly, Q=Quarterly, S=Semi-Annual)",
        },
    },
}

# Helper mapping to quick-lookup structural properties
STRUCTURE_REGISTRY: Dict[str, StructureField] = {}
for code, details in STRUCTURE["dimensions"].items():
    STRUCTURE_REGISTRY[code] = StructureField(code=code, field_type="dimension", **details)
for code, details in STRUCTURE["measures"].items():
    STRUCTURE_REGISTRY[code] = StructureField(code=code, field_type="measure", **details)
for code, details in STRUCTURE["time"].items():
    STRUCTURE_REGISTRY[code] = StructureField(code=code, field_type="time", **details)


# ---------------------------------------------------------------------------
# 2. Semantic Layer
# ---------------------------------------------------------------------------
SEMANTIC: Dict[str, Dict[str, Any]] = {
    "dimensions": {
        "FLOW": {
            "synonyms": ["trade_direction", "flow", "direction"],
            "values_map": {
                "EX": ["export", "exports", "outbound trade", "sell", "sending"],
                "IM": ["import", "imports", "inbound trade", "buy", "receiving"],
            },
        },
        "PARTNER_COUNTRY": {
            "synonyms": ["country", "partner", "destination", "origin", "partner_country"],
        },
        "MODE_OF_TRANSPORT": {
            "synonyms": ["mode_of_transport", "transport_mode", "mot", "transport"],
            "values_map": TRANSPORT_MODE_SYNONYMS,
        },
        "HS_CHAPTER": {
            "synonyms": ["hs_chapter", "chapter", "broad product"],
            "triggers": ["chapter", "broad product", "hs chapter"],
        },
        "HS_HEADING": {
            "synonyms": ["hs_heading", "heading", "specific product", "hs code"],
            "triggers": ["heading", "specific product", "hs code", "product code"],
        },
        "SITC_SECTION": {
            "synonyms": ["sitc_section", "economic_sector", "sector"],
            "triggers": ["sector", "industry", "economic structure", "sitc section"],
        },
        "SITC_DIVISION": {
            "synonyms": ["sitc_division", "sector_detail", "industry_detail"],
            "triggers": ["sector breakdown", "industry detail", "sitc division"],
        },
        "PERIOD": {
            "synonyms": ["period", "month", "year", "quarter", "time", "date"],
        },
        "FREQUENCY": {
            "synonyms": ["frequency", "freq"],
        },
    },
    "measures": {
        "VALUE_USD": {
            "synonyms": ["value", "usd", "trade value", "trade volume", "money"],
        },
        "VALUE_KHR": {
            "synonyms": ["riel", "khr", "local currency"],
        },
        "NET_WEIGHT": {
            "synonyms": ["weight", "kg", "kilograms", "net weight"],
        },
        "QUANTITY": {
            "synonyms": ["amount", "quantity", "units"],
        },
        "QUANTITY.UNIT": {
            "synonyms": ["unit", "quantity unit", "supplementary unit"],
        },
    },
}

SEMANTIC_REGISTRY: Dict[str, SemanticField] = {}
for code, details in SEMANTIC["dimensions"].items():
    SEMANTIC_REGISTRY[code] = SemanticField(code=code, **details)
for code, details in SEMANTIC["measures"].items():
    SEMANTIC_REGISTRY[code] = SemanticField(code=code, **details)


# ---------------------------------------------------------------------------
# 3. Intent Rules Layer
# ---------------------------------------------------------------------------
INTENT_RULES: Dict[str, IntentRule] = {
    "summary": IntentRule(
        intent="summary",
        required_dimensions=["FLOW"],
        optional_dimensions=["PARTNER_COUNTRY", "HS_CHAPTER", "SITC_SECTION", "MODE_OF_TRANSPORT"],
    ),
    "ranking": IntentRule(
        intent="ranking",
        required_dimensions=["FLOW"],
        supports_group_by=["PARTNER_COUNTRY", "HS_CHAPTER", "SITC_DIVISION"],
    ),
    "trend": IntentRule(
        intent="trend",
        required_time=True,
        optional_dimensions=["PARTNER_COUNTRY", "FLOW", "HS_CHAPTER", "SITC_SECTION"],
    ),
    "comparison": IntentRule(
        intent="comparison",
        required_dimensions=["FLOW"],
        min_partner_countries=2,
    ),
    "breakdown": IntentRule(
        intent="breakdown",
        required_dimensions=["FLOW"],
        supports_group_by=["HS_CHAPTER", "SITC_DIVISION", "MODE_OF_TRANSPORT"],
    ),
    "growth": IntentRule(
        intent="growth",
        required_dimensions=["FLOW"],
        required_time=True,
    ),
    "trade_balance": IntentRule(
        intent="trade_balance",
        required_dimensions=["PARTNER_COUNTRY"],
    ),
}


# ---------------------------------------------------------------------------
# 4. Dataset Binding Layer
# ---------------------------------------------------------------------------
DATASET_CONFIG: Dict[str, Dict[str, List[str]]] = {
    "trade_volume_1.0": {
        "dimensions": [
            "FLOW",
            "PARTNER_COUNTRY",
            "MODE_OF_TRANSPORT",
            "HS_CHAPTER",
            "HS_HEADING",
            "SITC_SECTION",
            "SITC_DIVISION",
        ],
        "measures": [
            "VALUE_USD",
            "VALUE_KHR",
            "NET_WEIGHT",
            "QUANTITY",
            "QUANTITY.UNIT",
        ],
        "time": [
            "PERIOD",
            "FREQUENCY",
        ],
    }
}

DATASETS = DATASET_CONFIG


# ---------------------------------------------------------------------------
# 5. Metadata Classification, Lookup & Hierarchy Helpers
# ---------------------------------------------------------------------------

CLASSIFICATION_SYSTEMS: Dict[str, List[str]] = {
    "HS": [
        "HS_CHAPTER",
        "HS_HEADING",
    ],
    "SITC": [
        "SITC_SECTION",
        "SITC_DIVISION",
    ]
}

CLASSIFICATION_HIERARCHY: Dict[str, List[str]] = {
    "HS_CHAPTER": ["HS_HEADING"],
    "SITC_SECTION": ["SITC_DIVISION"],
}


def normalize_intent(intent: str) -> str:
    """Normalize plural/singular/synonym intent names into canonical forms."""
    intent_clean = intent.strip().lower()
    intent_aliases = {
        "summaries": "summary",
        "rankings": "ranking",
        "trends": "trend",
        "comparisons": "comparison",
        "breakdowns": "breakdown",
        "growth analysis": "growth",
        "growth": "growth",
        "trade balance": "trade_balance",
        "trade_balance": "trade_balance",
    }
    return intent_aliases.get(intent_clean, intent_clean)


def find_dimension_by_synonym(synonym: str) -> Optional[str]:
    """Find the canonical dimension code from a synonym."""
    syn_clean = synonym.strip().lower()
    # Check exact code matches
    for code in STRUCTURE["dimensions"].keys():
        if code.lower() == syn_clean:
            return code
    # Check synonyms list
    for code, field in SEMANTIC_REGISTRY.items():
        if syn_clean in field.synonyms:
            return code
    return None


def find_measure_by_synonym(synonym: str) -> Optional[str]:
    """Find the canonical measure code from a synonym."""
    syn_clean = synonym.strip().lower()
    # Check exact code matches
    for code in STRUCTURE["measures"].keys():
        if code.lower() == syn_clean:
            return code
    # Check synonyms list
    for code, field in SEMANTIC_REGISTRY.items():
        if syn_clean in field.synonyms:
            return code
    return None


def get_parent_dimension(code: str) -> Optional[str]:
    """Return the parent dimension code if defined in STRUCTURE registry."""
    dim = STRUCTURE.get("dimensions", {}).get(code)
    if dim:
        return dim.get("parent")
    return None


def get_children_dimensions(code: str) -> List[str]:
    """Return a list of dimensions that list this code as their parent."""
    if code in CLASSIFICATION_HIERARCHY:
        return CLASSIFICATION_HIERARCHY[code]
    children = []
    for dim_code, dim_details in STRUCTURE.get("dimensions", {}).items():
        if dim_details.get("parent") == code:
            children.append(dim_code)
    return children
