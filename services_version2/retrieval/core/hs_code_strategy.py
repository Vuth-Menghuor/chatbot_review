"""
HS code ranking and interaction strategy for Retrieval service.

Implements:
- Keyword -> HS heading mapping boost
- Default single best result policy
- 4-digit heading prediction
- Select and compare flows
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import re


KEYWORD_TO_HEADING = {
    "horse": "0101",
    "horses": "0101",
    "equine": "0101",
    "chicken": "0207",
    "cattle": "0102",
    "beef": "0201",
    "tilapia": "0303",
    "frozen fish": "0303",
    "pollock": "0302",
    "norway lobster": "0306",
    "nephrops": "0306",
    "mackerel": "0303",
    "tuna": "0303",
    "shark": "0304",
    "dogfish": "0304",
    "toothfish": "0304",
    "squid": "0307",
    "cuttlefish": "0307",
    "alaska pollock": "0302",
    "rice": "1006",
    "plantain": "0803",
    "plantains": "0803",
    "truffle": "2003",
    "truffles": "2003",
    "maize": "1005",
    "corn seed": "1005",
    "barley": "1104",
    "sugar": "1701",
    "sugar beet": "1209",
    "seed": "1209",
    "cement": "2523",
    "laptop": "8471",
    "computer": "8471",
    "desktop": "8471",
    "adp": "8471",
    "mobile": "8517",
    "phone": "8517",
    "motorcycle": "8711",
    "motorbike": "8711",
    "car": "8703",
    "truck": "8704",
    "hybrid truck": "8704",
    "steel": "7208",
    "plastic pipe": "3917",
    "pvc pipe": "3917",
    "garment": "6203",
    "shirt": "6205",
    "tomato": "0702",
    "tomatoes": "0702",
    "mercury": "2805",
    "asbestos": "2524",
    "cocaine": "2939",
    "ecgonine": "2939",
    "sodium cyclamate": "2929",
    "antimalarial": "3003",
    "medicament": "3003",
    "antibiotic medicaments": "3004",
    "ointment": "3004",
    "oral": "3004",
    "rice wine": "2206",
    "mineral water": "2201",
    "toothpaste": "3306",
    "dentifrice": "3306",
    "ptfe": "3904",
    "polytetrafluoroethylene": "3904",
    "hydraulic brake fluid": "2710",
    "aviation turbine fuel": "2710",
    "jet fuel": "2710",
    "hfc-134a": "2903",
    "tetrafluoroethane": "2903",
    "natural rubber": "4001",
    "rubber tyres": "4011",
    "bicycle tyres": "4011",
    "printed circuits": "8534",
    "air conditioner": "8415",
    "heating resistors": "8516",
    "audio-frequency amplifier": "8518",
    "starter motor": "8511",
    "drive axle": "8708",
    "crown wheels": "8708",
    "pinions": "8708",
    "copper-alloy coated steel wire": "7217",
    "razor blades": "8212",
    "machine-tools": "8464",
    "ceramics": "8464",
    "radio receivers": "8527",
    "instrument panel clocks": "9104",
    "lead-acid starter batteries": "8507",
    "refuse truck": "8704",
    "garbage truck": "8704",
    "passenger car": "8703",
    "bus": "8702",
    "vehicle air conditioning": "8415",
    "hearse": "8703",
    "hooklift truck": "8704",
    "led-powered": "9405",
    "warning signs": "9405",
    "salmon": "1604",
    "coconut water": "2009",
    "spark ignition engine": "8407",
    "marine engine": "8407",
}


@dataclass
class HSSelectionResult:
    documents: List[Dict[str, Any]]
    heading_4_digit: Optional[str]
    missing_parameters: List[str]
    mode: str
    clarification: Optional[str] = None


def _normalize_hs_code(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) < 4:
        return None
    if len(digits) == 8:
        return f"{digits[:4]}.{digits[4:6]}.{digits[6:8]}"
    if len(digits) == 6:
        return f"{digits[:4]}.{digits[4:6]}"
    return digits[:4]


def _heading_from_hs(raw: Optional[str]) -> Optional[str]:
    normalized = _normalize_hs_code(raw)
    if not normalized:
        return None
    return normalized.replace(".", "")[:4]


def _extract_hs(doc: Dict[str, Any]) -> Optional[str]:
    metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata", {}), dict) else {}
    return (
        doc.get("hs_code")
        or metadata.get("hs_code")
        or metadata.get("hscode")
        or metadata.get("tariff_code")
    )


def _keyword_heading(query: str) -> Optional[str]:
    q = query.lower()
    best_key: Optional[str] = None
    for key in KEYWORD_TO_HEADING:
        if key in q and (best_key is None or len(key) > len(best_key)):
            best_key = key
    if best_key is None:
        return None
    return KEYWORD_TO_HEADING[best_key]


def _boost_score(base_score: float, query_heading: Optional[str], doc_heading: Optional[str]) -> float:
    boosted = base_score
    if query_heading and doc_heading and query_heading == doc_heading:
        # Stronger heading boost for phrase-style HS queries (e.g., "HS code for horse")
        # so explicit keyword mapping wins over semantically adjacent noise.
        boosted += 0.35
    return min(1.0, boosted)


def rank_hs_documents(query: str, documents: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    heading = _keyword_heading(query)
    ranked: List[Dict[str, Any]] = []

    for doc in documents:
        hs_code = _extract_hs(doc)
        doc_heading = _heading_from_hs(hs_code)
        base_score = float(doc.get("score", 0.0) or 0.0)
        adjusted = _boost_score(base_score, heading, doc_heading)

        normalized_hs = _normalize_hs_code(hs_code)
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        metadata = dict(metadata)
        if normalized_hs:
            metadata["hs_code"] = normalized_hs
            metadata["heading_4_digit"] = doc_heading

        updated = dict(doc)
        updated["score"] = adjusted
        updated["metadata"] = metadata
        ranked.append(updated)

    ranked.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
    return ranked, heading


def _with_same_heading(ranked: List[Dict[str, Any]], heading: str) -> List[Dict[str, Any]]:
    return [d for d in ranked if _heading_from_hs(_extract_hs(d)) == heading]


def select_hs_documents(
    query: str,
    documents: List[Dict[str, Any]],
    mode: str = "best",
    selected_code: Optional[str] = None,
    compare_codes: Optional[List[str]] = None,
) -> HSSelectionResult:
    ranked, predicted_heading = rank_hs_documents(query, documents)
    compare_codes = compare_codes or []
    missing: List[str] = []

    if not ranked:
        return HSSelectionResult(documents=[], heading_4_digit=predicted_heading, missing_parameters=missing, mode=mode)

    if mode == "select":
        if not selected_code:
            missing.append("selected_code")
            return HSSelectionResult(documents=[], heading_4_digit=predicted_heading, missing_parameters=missing, mode=mode)
        normalized = _normalize_hs_code(selected_code)
        chosen = [d for d in ranked if _normalize_hs_code(_extract_hs(d)) == normalized]
        return HSSelectionResult(documents=chosen[:1], heading_4_digit=predicted_heading, missing_parameters=missing, mode=mode)

    if mode == "compare":
        if not compare_codes:
            missing.append("compare_codes")
            return HSSelectionResult(documents=[], heading_4_digit=predicted_heading, missing_parameters=missing, mode=mode)
        normalized_codes = {_normalize_hs_code(code) for code in compare_codes}
        compared = [d for d in ranked if _normalize_hs_code(_extract_hs(d)) in normalized_codes]
        return HSSelectionResult(documents=compared, heading_4_digit=predicted_heading, missing_parameters=missing, mode=mode)

    # Best mode: if top candidates are too close, return top alternatives and ask for clarification.
    if len(ranked) >= 2:
        top_score = float(ranked[0].get("score", 0.0) or 0.0)
        second_score = float(ranked[1].get("score", 0.0) or 0.0)
        close_confidence_gap = abs(top_score - second_score) <= 0.03
        top_code = _normalize_hs_code(_extract_hs(ranked[0]))
        second_code = _normalize_hs_code(_extract_hs(ranked[1]))
        different_top_codes = bool(top_code and second_code and top_code != second_code)
        if close_confidence_gap and different_top_codes:
            missing.append("product_specification")
            return HSSelectionResult(
                documents=ranked[:3],
                heading_4_digit=predicted_heading,
                missing_parameters=missing,
                mode="best",
                clarification=(
                    "Top HS candidates are very close. Please provide more product details "
                    "(material, composition, usage, and technical specs) for precise classification."
                ),
            )

    if predicted_heading:
        predicted_cluster = _with_same_heading(ranked, predicted_heading)
        if predicted_cluster:
            return HSSelectionResult(
                documents=predicted_cluster[:1],
                heading_4_digit=predicted_heading,
                missing_parameters=missing,
                mode="best",
            )

    top = ranked[0]
    top_heading = _heading_from_hs(_extract_hs(top))
    cluster = _with_same_heading(ranked, top_heading) if top_heading else [top]
    return HSSelectionResult(documents=cluster[:1], heading_4_digit=top_heading or predicted_heading, missing_parameters=missing, mode="best")
