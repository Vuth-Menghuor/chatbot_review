import logging
import re
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

TAX_ACRONYM_PATTERN = re.compile(r"\b(COP|CPP|DPP|SOP|SPP|VOP|VPP|VAT|CD|ST|ATP)\b", re.IGNORECASE)
CLAIM_MARKERS = ("majority", "largest", "main", "highest")


def warn_calculator_business_inconsistencies(payload: dict[str, Any], content: str) -> None:
    if settings.environment not in {"development", "dev", "local", "testing"}:
        return

    warnings = calculator_business_inconsistencies(payload, content)
    for warning in warnings:
        logger.warning(
            "calculator_upstream_business_inconsistency request_id=%s session_id=%s issue=%s",
            payload.get("request_id") or payload.get("requestId"),
            payload.get("session_id") or payload.get("sessionId"),
            warning,
        )


def calculator_business_inconsistencies(payload: dict[str, Any], content: str) -> list[str]:
    claimed_acronyms = claimed_tax_acronyms(content)
    table_acronyms = tax_breakdown_acronyms(payload)
    if not claimed_acronyms or not table_acronyms:
        return []

    missing_from_table = sorted(claimed_acronyms - table_acronyms)
    if not missing_from_table:
        return []

    return [
        "answer_claimed_tax_component_not_present_in_structured_tax_breakdown:"
        f" claimed={','.join(missing_from_table)} table={','.join(sorted(table_acronyms))}"
    ]


def claimed_tax_acronyms(content: str) -> set[str]:
    acronyms: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", content):
        if any(marker in sentence.lower() for marker in CLAIM_MARKERS):
            acronyms.update(match.group(1).upper() for match in TAX_ACRONYM_PATTERN.finditer(sentence))
    return acronyms


def tax_breakdown_acronyms(payload: dict[str, Any]) -> set[str]:
    result = first_structured_result(payload)
    rows = result.get("tax_breakdown") if isinstance(result, dict) and isinstance(result.get("tax_breakdown"), list) else []
    acronyms: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("tax_component", "component", "name", "tax_type"):
            value = row.get(key)
            if isinstance(value, str):
                acronyms.update(match.group(1).upper() for match in TAX_ACRONYM_PATTERN.finditer(value))
    return acronyms


def first_structured_result(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("calculator_result", "structured_result"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    result = payload.get("result")
    if isinstance(result, dict):
        nested = result.get("result")
        if isinstance(nested, dict):
            return nested
        return result
    return {}
