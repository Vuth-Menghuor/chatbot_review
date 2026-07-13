"""Natural-language parameter validation and schema checks for trade_query.

Strictly handles validation and safety checks (Stage 5 Validation).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.exceptions import ValidationError
from app.registry.semantic_registry import DATASET_CONFIG, INTENT_RULES, STRUCTURE
from app.schemas.query_plan import FinalQueryPlan

logger = logging.getLogger(__name__)


def validate_question(question: str) -> str:
    """Format validation for the natural language question input."""
    if not question or not isinstance(question, str):
        raise ValidationError("Question must be a non-empty string", field="question")
    question = question.strip()
    if len(question) < 5:
        raise ValidationError("Question must be at least 5 characters", field="question")
    return question


def validate_query_plan(plan: FinalQueryPlan) -> None:
    """Stage 5 Validation: Validate the finalized FinalQueryPlan against registry dataset rules."""
    # 1. Intent validation
    if plan.intent not in INTENT_RULES:
        raise ValidationError(f"Unknown intent: {plan.intent}", field="intent")

    # 2. Dataset validation
    version = plan.version
    if version not in DATASET_CONFIG:
        raise ValidationError(f"Unknown dataset version: {version}", field="version")
    dataset_rules = DATASET_CONFIG[version]

    # 3. Measures/metrics validation
    if plan.metrics:
        for m in plan.metrics:
            if m not in dataset_rules["measures"]:
                raise ValidationError(f"Unsupported measure: {m}", field="metrics")

    # 4. Group_by / dimension validation
    if plan.group_by:
        for g in plan.group_by:
            if g not in dataset_rules["dimensions"] and g not in dataset_rules["time"]:
                raise ValidationError(f"Unsupported group_by dimension: {g}", field="group_by")

    if plan.dimensions:
        for d in plan.dimensions:
            if d not in dataset_rules["dimensions"] and d not in dataset_rules["time"]:
                raise ValidationError(f"Unsupported dimension: {d}", field="dimensions")

    # 5. Filters validation
    # Verify that all keys in plan.filters are valid dimensions in the dataset structure
    for key in plan.filters.keys():
        check_key = key
        if key in ("HS_HEADING", "HS_CODE"):
            check_key = "HS_HEADING"
        if check_key not in dataset_rules["dimensions"]:
            raise ValidationError(f"Filter dimension not supported by dataset: {key}", field="filters")

    # 6. Mode of transport code validation
    mot = plan.filters.get("MODE_OF_TRANSPORT")
    if mot:
        valid_mots = STRUCTURE["dimensions"]["MODE_OF_TRANSPORT"]["values"]
        if isinstance(mot, list):
            for m in mot:
                if str(m) not in valid_mots:
                    raise ValidationError(f"Invalid mode of transport: {m}", field="mode_of_transport")
        else:
            if str(mot) not in valid_mots:
                raise ValidationError(f"Invalid mode of transport: {mot}", field="mode_of_transport")

    # 7. Trade flow / direction code validation
    direction = plan.filters.get("FLOW")
    if direction:
        valid_flows = STRUCTURE["dimensions"]["FLOW"]["values"]
        if isinstance(direction, list):
            for d in direction:
                if str(d) not in valid_flows:
                    raise ValidationError(f"Invalid trade direction: {d}", field="trade_direction")
        else:
            if str(direction) not in valid_flows:
                raise ValidationError(f"Invalid trade direction: {direction}", field="trade_direction")

    # 8. HS code format validation (numeric checks)
    hs_code = plan.filters.get("HS_CODE") or plan.filters.get("HS_HEADING") or plan.filters.get("HS_CHAPTER")
    if hs_code:
        if isinstance(hs_code, list):
            for code in hs_code:
                if not str(code).isdigit():
                    raise ValidationError(f"HS code must be numeric digits, got: {code}", field="hs_code")
        else:
            if not str(hs_code).isdigit():
                raise ValidationError(f"HS code must be numeric digits, got: {hs_code}", field="hs_code")

    # 9. Period and frequency format validation
    if plan.frequency and plan.period:
        freq = plan.frequency.upper()
        p = plan.period
        import re
        if not re.match(r"^\d{4}$", p):
            if freq == "Q":
                if not re.match(r"^\d{4}-Q[1-4]$", p):
                    raise ValidationError(f"Quarterly period must be YYYY-Qn (1-4) or YYYY, got: {p}", field="period")
            elif freq == "M":
                if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", p):
                    raise ValidationError(f"Monthly period must be YYYY-MM (01-12) or YYYY, got: {p}", field="period")
            elif freq == "S":
                if not re.match(r"^\d{4}-S[12]$", p):
                    raise ValidationError(f"Semi-Annual period must be YYYY-Sn (1-2) or YYYY, got: {p}", field="period")
            elif freq == "A":
                raise ValidationError(f"Annual period must be YYYY, got: {p}", field="period")


def validate_extracted_parameters(params: dict[str, Any]) -> None:
    """Validate structured parameter values and schema rules against semantic registry."""
    if params.get("metrics"):
        for m in params["metrics"]:
            if m == "VALUE_KHR":
                warning_payload = {
                    "warning": "VALUE_KHR not available",
                    "fallback_suggested": "VALUE_USD",
                }
                raise ValidationError(json.dumps(warning_payload), field="metrics")

    # Reconstruct FinalQueryPlan for backward compatibility
    filters = params.get("filters", {})
    if not filters:
        filters = {}
        if params.get("trade_direction"):
            filters["FLOW"] = params["trade_direction"]
        partner = params.get("partner_countries") or params.get("partner_country")
        if partner:
            filters["PARTNER_COUNTRY"] = partner
        if params.get("mode_of_transport"):
            filters["MODE_OF_TRANSPORT"] = params["mode_of_transport"]
        if params.get("hs_code"):
            filters["HS_CODE"] = params["hs_code"]
        if params.get("hs_chapter"):
            filters["HS_CHAPTER"] = params["hs_chapter"]
        if params.get("sitc_section"):
            filters["SITC_SECTION"] = params["sitc_section"]
        if params.get("sitc_division"):
            filters["SITC_DIVISION"] = params["sitc_division"]

    plan = FinalQueryPlan(
        intent=params.get("intent", "summary"),
        version=params.get("version", "trade_volume_1.0"),
        filters=filters,
        metrics=params.get("metrics") or [],
        group_by=params.get("group_by") or [],
        dimensions=params.get("dimensions") or [],
        period=params.get("period"),
        start_period=params.get("start_period"),
        end_period=params.get("end_period"),
        frequency=params.get("frequency"),
        sort=params.get("sort"),
        limit=params.get("limit", 1000),
        offset=params.get("offset", 0),
    )
    validate_query_plan(plan)
