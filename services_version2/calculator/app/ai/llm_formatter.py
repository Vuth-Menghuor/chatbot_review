"""
Calculator Human-Readable Formatter (Standalone)
================================================
Builds rich, step-by-step calculation reports directly from
result dictionaries. No LLM required.

Usage:
    from ..ai.llm_formatter import format_human_readable
    text = format_human_readable(request, result_dict)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

_DB_NAME = os.getenv("CALCULATOR_DB_NAME", "gdce_calculator")

logger = logging.getLogger(__name__)


def format_human_readable(
    request: Any,
    result_dict: Dict[str, Any],
) -> str:
    """
    Build a rich, step-by-step human-readable calculation report
    directly from the result dictionary. No LLM needed.

    Args:
        request: The CalculationRequest (or CalculateImportTaxesRequest)
        result_dict: The raw calculation result dictionary

    Returns:
        Formatted multi-line string suitable for direct display
    """
    bd = result_dict.get("breakdown", {})
    li = result_dict.get("line_items", [])
    assumptions = result_dict.get("assumptions", [])
    exchange_rate = result_dict.get("exchange_rate_usd_to_khr", 4022.0)
    total = result_dict.get("total", 0.0)
    currency = result_dict.get("currency", "KHR")
    cif_value_usd = result_dict.get("cif_value_usd", 0.0)
    hs_code = _get_hs_code(request)
    origin = _get_origin(request)
    description = _get_description(request)
    regime = _get_regime(request)
    calc_date = _get_calc_date(request)
    is_petroleum = _get_flag(request, "petroleum_case", False)
    is_rubber = _get_flag(request, "rubber_case", False)
    is_fta = _get_flag(request, "fta_applicable", False)
    is_export = (regime or "").lower() == "export"

    # --- Capture original input currency / value for accurate display ---
    input_currency = getattr(request, "currency", "USD") or "USD"
    try:
        input_value = float(getattr(request, "customs_value", 0))
    except (ValueError, TypeError):
        input_value = 0.0

    # --- HEADER ---
    title = "EXPORT TAX CALCULATION" if is_export else "IMPORT TAX CALCULATION"
    lines = [
        "-----------------------------------------------------------------",
        title,
        "-----------------------------------------------------------------",
        "",
        "PRODUCT INFORMATION:",
        f"* HS Code: {hs_code or 'N/A'} ({description or 'N/A'})",
        f"* Origin Country: {origin or 'General rates'}",
        f"* Incoterm: CIF (Cost, Insurance, Freight)",
        "",
    ]

    if input_currency == "KHR":
        lines.extend([
            "INPUT PARAMETERS:",
            f"* CIF Value: {_fmt_whole(input_value)} KHR",
            f"* Exchange Rate: N/A (already in local currency)",
            f"* Customs Regime: {_regime_label(regime, is_fta, is_petroleum)}",
            f"* Calculation Date: {calc_date}",
            "",
        ])
    else:
        lines.extend([
            "INPUT PARAMETERS:",
            f"* CIF Value: {_fmt_num(cif_value_usd)} USD",
            f"* Exchange Rate: 1 USD = {_fmt_num(exchange_rate)} KHR",
            f"* Customs Regime: {_regime_label(regime, is_fta, is_petroleum)}",
            f"* Calculation Date: {calc_date}",
            "",
        ])

    cif_khr = bd.get("cif_value", 0)
    is_dq = float(bd.get("dq_factor", 0)) > 0

    # --- PETROLEUM CASE ---
    if is_petroleum:
        lines.extend(_format_petroleum(bd, exchange_rate, total, currency, cif_khr, li, input_currency, input_value))
    # --- RUBBER CASE ---
    elif is_rubber and is_export:
        lines.extend(_format_rubber(bd, exchange_rate, total, currency, cif_khr, input_currency, input_value))
    # --- FTA/DV + DQ CASE ---
    elif is_dq:
        lines.extend(_format_fta_dq(bd, exchange_rate, total, currency, cif_khr, li, input_currency, input_value))
    # --- NORMAL / FTA CASE ---
    else:
        lines.extend(_format_normal(bd, exchange_rate, total, currency, cif_khr, is_fta, li, input_currency, input_value))

    # --- TABLE ---
    lines.extend(_build_table(li, total, currency, exchange_rate))

    # --- SUMMARY ---
    lines.extend(_build_summary(hs_code, description, cif_value_usd, origin, total, currency, li, is_export, is_petroleum, bd, input_currency, input_value))

    # --- APPLICABLE RATES (rendered from structured line_items, not assumptions) ---
    lines.extend(_build_rates_section(li))

    # --- ASSUMPTIONS & NOTES ---
    if assumptions:
        # Filter out empty strings and pure formatting artifacts before rendering
        clean_assumptions = [a for a in assumptions if a and str(a).strip()]
        if clean_assumptions:
            lines.append("-----------------------------------------------------------------")
            lines.append("ASSUMPTIONS & NOTES")
            lines.append("-----------------------------------------------------------------")
            for a in clean_assumptions:
                lines.append(f"  + {a}")
            lines.append("")

    # --- REFERENCES & CITATIONS ---
    references = result_dict.get("references", [])
    if references:
        lines.append("-----------------------------------------------------------------")
        lines.append("REFERENCES & CITATIONS")
        lines.append("-----------------------------------------------------------------")
        for idx, ref in enumerate(references, 1):
            title = ref.get("title", "Unknown source")
            doc_id = ref.get("doc_id", "")
            url = ref.get("source_url", "")
            section = ref.get("section_title", "")
            eff_date = ref.get("effective_start_date", "")
            ref_line = f"[{idx}] {title}"
            if section:
                ref_line += f" — {section}"
            if doc_id:
                ref_line += f" (ID: {doc_id})"
            if url:
                ref_line += f" | {url}"
            if eff_date:
                ref_line += f" | Effective: {eff_date}"
            lines.append(f"  * {ref_line}")
        lines.append("")

    # --- DATA SOURCES ---
    lines.append("-----------------------------------------------------------------")
    lines.append("DATA SOURCES")
    lines.append("-----------------------------------------------------------------")
    lines.append(f"* HS Codes & Descriptions: PostgreSQL ({_DB_NAME}.hs_codes)")
    lines.append(f"* Duty Rates (CD, ST, VAT, ET): PostgreSQL ({_DB_NAME}.duty_rates)")
    lines.append(f"* ATP Rates (Petroleum): PostgreSQL ({_DB_NAME}.duty_rates.atp_rate)")
    lines.append(f"* Exchange Rates: PostgreSQL ({_DB_NAME}.exchange_rates)")
    lines.append(f"* Deduction Values (DV): PostgreSQL ({_DB_NAME}.declared_values)")
    lines.append(f"* Dynamic Rules (Formulas, Rounding, Policies): PostgreSQL ({_DB_NAME})")
    lines.append(f"* Calculation History: PostgreSQL ({_DB_NAME}.calculation_history)")
    lines.append("* Official Tariff Lookup: https://gdce.gov.kh/tariff-search")
    lines.append("* Exchange Rate Source: https://nbc.gov.kh/")
    lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _fmt_num(v) -> str:
    if v is None:
        return "0.00"
    try:
        return f"{float(v):,.2f}"
    except (ValueError, TypeError):
        return str(v)


def _fmt_whole(v) -> str:
    if v is None:
        return "0"
    try:
        return f"{int(float(v)):,}"
    except (ValueError, TypeError):
        return str(v)


def _get_hs_code(request) -> Optional[str]:
    g = getattr(request, "goods", None) or {}
    return g.get("hs_code") if isinstance(g, dict) else getattr(request, "hs_code", None)


def _get_origin(request) -> Optional[str]:
    g = getattr(request, "goods", None) or {}
    return g.get("origin_country") if isinstance(g, dict) else getattr(request, "origin_country", None)


def _get_description(request) -> Optional[str]:
    g = getattr(request, "goods", None) or {}
    return g.get("description") if isinstance(g, dict) else None


def _get_regime(request) -> Optional[str]:
    return getattr(request, "regime", None)


def _get_calc_date(request) -> Optional[str]:
    return getattr(request, "calculation_date", None)


def _get_flag(request, flag_name: str, default: bool = False) -> bool:
    f = getattr(request, "flags", None) or {}
    return f.get(flag_name, default) if isinstance(f, dict) else getattr(request, flag_name, default)


def _regime_label(regime: Optional[str], fta: bool, petroleum: bool = False) -> str:
    r = (regime or "").lower()
    if petroleum:
        return "Petroleum (two-phase calculation)"
    if fta:
        return "Preferential (FTA rates)"
    if r == "export":
        return "Export"
    if r == "import":
        return "Normal (standard rates)"
    return (regime or "Normal").title()


def _find_line_item(li, tax_type: str) -> Optional[Dict[str, Any]]:
    for item in li:
        if item.get("tax_type") == tax_type:
            return item
    return None


def _build_rates_section(li: List[Dict[str, Any]]) -> List[str]:
    """Build an 'APPLICABLE RATES' section from structured line_items instead of assumptions."""
    rate_lines: List[str] = []
    for item in li:
        tax_type = item.get("tax_type", "")
        name = item.get("name", "")
        rate = item.get("rate")
        if rate is None:
            continue
        try:
            rate_val = float(rate)
        except (ValueError, TypeError):
            continue
        # Skip DPP/BUR/VVF fixed-fee rows in the rates summary
        if tax_type in ("DPP", "BUR", "VVF"):
            continue
        # ATP rate is stored in KHR/L; skip generic rate display here
        if tax_type == "ATP":
            continue
        rate_lines.append(f"  + {name}: {rate_val:.2f}%")
    if not rate_lines:
        return []
    return [
        "-----------------------------------------------------------------",
        "APPLICABLE RATES",
        "-----------------------------------------------------------------",
    ] + rate_lines + [""]


def _format_petroleum(bd, exchange_rate, total, currency, cif_khr, li, input_currency="USD", input_value=0.0) -> List[str]:
    cpp_base = bd.get("cpp_base", 0)
    cpp = bd.get("cpp_amount", 0)
    atp = bd.get("atp_amount", 0)
    spp = bd.get("spp_amount", 0)
    vpp = bd.get("vpp_amount", 0)
    dpp = bd.get("dpp_amount", 0)
    dpp_gap = bd.get("dpp_gap", 0)
    p2_cpp = bd.get("phase2_cpp_amount", 0)
    p2_atp = bd.get("phase2_atp_amount", 0)
    p2_spp = bd.get("phase2_spp_amount", 0)
    p2_vpp = bd.get("phase2_vpp_amount", 0)
    p2_total = bd.get("phase2_total", 0)

    # Derive ATP $/L rate from line items so it is never hard-coded
    atp_item = _find_line_item(li, "ATP")
    atp_rate_usd = None
    if atp_item and exchange_rate:
        try:
            rate_khr = float(atp_item.get("rate", 0) or 0)
            atp_rate_usd = rate_khr / float(exchange_rate)
        except (ValueError, TypeError, ZeroDivisionError):
            atp_rate_usd = None
    atp_rate_str = f"{_fmt_num(atp_rate_usd)}" if atp_rate_usd is not None else "0.02"

    if input_currency == "KHR":
        step1 = [
            "-----------------------------------------------------------------",
            "STEP 1: CURRENCY CONFIRMATION (KHR)",
            "-----------------------------------------------------------------",
            f"CIF Value = {_fmt_whole(cif_khr)} KHR (already in local currency)",
            "",
        ]
    else:
        step1 = [
            "-----------------------------------------------------------------",
            "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
            "-----------------------------------------------------------------",
            f"Formula: CIF Value (USD) x Exchange Rate",
            f"= {_fmt_num(cif_khr / exchange_rate if exchange_rate else 0)} x {_fmt_num(exchange_rate)} KHR/USD",
            f"= {_fmt_whole(cif_khr)} KHR",
            "",
        ]

    lines = step1 + [
        "-----------------------------------------------------------------",
        "STEP 2: PHASE 1 -- PETROLEUM TAX (Deduction Value Basis)",
        "-----------------------------------------------------------------",
        f"CPP base  = DV/ton x exchange_rate x net_mass_kg / 1000",
        f"          = {_fmt_whole(cpp_base)} KHR",
        f"CPP       = CPP base x CD rate = {_fmt_whole(cpp)} KHR",
        f"ATP       = volume_liter x {atp_rate_str} $/L x exchange_rate = {_fmt_whole(atp)} KHR",
        f"SPP       = (CPP base + CPP + ATP) x ST rate = {_fmt_whole(spp)} KHR",
        f"VPP       = (CPP base + CPP + ATP + SPP) x VAT rate = {_fmt_whole(vpp)} KHR",
        f"Phase 1 Total = {_fmt_whole(cpp + atp + spp + vpp)} KHR",
        "",
        "-----------------------------------------------------------------",
        "STEP 3: PHASE 2 -- PETROLEUM TAX (Customs Value / CIF Basis)",
        "-----------------------------------------------------------------",
        f"CIF value = {_fmt_whole(cif_khr)} KHR",
        f"CPP       = CIF value x CD rate = {_fmt_whole(p2_cpp)} KHR",
        f"ATP       = same as Phase 1 = {_fmt_whole(p2_atp)} KHR",
        f"SPP       = (CIF value + CPP + ATP) x ST rate = {_fmt_whole(p2_spp)} KHR",
        f"VPP       = (CIF value + CPP + ATP + SPP) x VAT rate = {_fmt_whole(p2_vpp)} KHR",
        f"Phase 2 Total = {_fmt_whole(p2_total)} KHR",
        "",
        "-----------------------------------------------------------------",
        "STEP 4: DIFFERENCE / PARTIAL SUBSIDY (DPP)",
        "-----------------------------------------------------------------",
        f"Absolute gap = |Phase 1 Total - Phase 2 Total|",
        f"             = |{_fmt_whole(cpp + atp + spp + vpp)} - {_fmt_whole(p2_total)}|",
        f"             = {_fmt_whole(dpp_gap)} KHR",
        "",
    ]
    return lines


def _format_rubber(bd, exchange_rate, total, currency, cif_khr, input_currency="USD", input_value=0.0) -> List[str]:
    etr = bd.get("etr_amount", 0)
    if input_currency == "KHR":
        step1 = [
            "-----------------------------------------------------------------",
            "STEP 1: CURRENCY CONFIRMATION (KHR)",
            "-----------------------------------------------------------------",
            f"CIF Value = {_fmt_whole(cif_khr)} KHR (already in local currency)",
            "",
        ]
    else:
        step1 = [
            "-----------------------------------------------------------------",
            "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
            "-----------------------------------------------------------------",
            f"Formula: CIF Value (USD) x Exchange Rate",
            f"= {_fmt_num(cif_khr / exchange_rate if exchange_rate else 0)} x {_fmt_num(exchange_rate)} KHR/USD",
            f"= {_fmt_whole(cif_khr)} KHR",
            "",
        ]
    lines = step1 + [
        "-----------------------------------------------------------------",
        "STEP 2: EXPORT TAX ON RUBBER (ETR)",
        "-----------------------------------------------------------------",
        f"ETR = (CIF_KHR / net_mass_kg) x ET rate",
        f"    = {_fmt_whole(etr)} KHR",
        "",
    ]
    return lines


def _format_normal(bd, exchange_rate, total, currency, cif_khr, is_fta, li, input_currency="USD", input_value=0.0) -> List[str]:
    cop = bd.get("cop_amount", 0)
    sop = bd.get("sop_amount", 0)
    vop = bd.get("vop_amount", 0)
    vvf = bd.get("vvf_amount", 0)

    cd_item = _find_line_item(li, "CD")
    st_item = _find_line_item(li, "ST")
    vat_item = _find_line_item(li, "VAT")
    cd_rate = float(cd_item.get("rate", 0)) if cd_item else 0
    st_rate = float(st_item.get("rate", 0)) if st_item else 0
    vat_rate = float(vat_item.get("rate", 0)) if vat_item else 0

    if input_currency == "KHR":
        step1 = [
            "-----------------------------------------------------------------",
            "STEP 1: CURRENCY CONFIRMATION (KHR)",
            "-----------------------------------------------------------------",
            f"CIF Value = {_fmt_whole(cif_khr)} KHR (already in local currency)",
            "",
        ]
    else:
        step1 = [
            "-----------------------------------------------------------------",
            "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
            "-----------------------------------------------------------------",
            f"Formula: CIF Value (USD) x Exchange Rate",
            f"= {_fmt_num(cif_khr / exchange_rate if exchange_rate else 0)} x {_fmt_num(exchange_rate)} KHR/USD",
            f"= {_fmt_whole(cif_khr)} KHR",
            "",
        ]

    lines = step1 + [
        "-----------------------------------------------------------------",
        "STEP 2: IMPORT TAXES (COP)",
        "-----------------------------------------------------------------",
        f"Import Taxes (COP) = Customs Value x Import Tax Rate",
        f"= {_fmt_whole(cif_khr)} x {cd_rate:.2f}%",
        f"= {_fmt_whole(cop)} KHR",
        "",
    ]

    if sop > 0:
        lines.extend([
            "-----------------------------------------------------------------",
            "STEP 3: SPECIAL TARIFF (SOP)",
            "-----------------------------------------------------------------",
            f"Special Tariff (SOP) = (Customs Value + Import Tax) x Special Tariff Rate",
            f"= ({_fmt_whole(cif_khr)} + {_fmt_whole(cop)}) x {st_rate:.2f}%",
            f"= {_fmt_whole(sop)} KHR",
            "",
        ])

    lines.extend([
        "-----------------------------------------------------------------",
        "STEP 4: VOP",
        "-----------------------------------------------------------------",
    ])
    if sop == 0:
        lines.append(f"VOP = (Customs Value + Import Tax) x {vat_rate:.2f}% (For non-taxable goods)")
        lines.append(f"= ({_fmt_whole(cif_khr)} + {_fmt_whole(cop)}) x {vat_rate:.2f}%")
    else:
        lines.append(f"VOP = (Customs Value + Import Tax + Special Tariff) x {vat_rate:.2f}% (For general taxable goods)")
        lines.append(f"= ({_fmt_whole(cif_khr)} + {_fmt_whole(cop)} + {_fmt_whole(sop)}) x {vat_rate:.2f}%")
    lines.append(f"= {_fmt_whole(vop)} KHR")
    lines.append("")

    # Total Duties and Taxes
    if sop == 0:
        formula_parts = "Import Taxes (COP) + VOP (For non-taxable goods)"
        math_parts = f"{_fmt_whole(cop)} + {_fmt_whole(vop)}"
    else:
        formula_parts = "Import Taxes (COP) + Special Tariff (SOP) + VOP (For general taxable goods)"
        math_parts = f"{_fmt_whole(cop)} + {_fmt_whole(sop)} + {_fmt_whole(vop)}"

    if vvf > 0:
        formula_parts += " + Vehicle Valuation Fee (VVF)"
        math_parts += f" + {_fmt_whole(vvf)}"

    lines.extend([
        "-----------------------------------------------------------------",
        "STEP 5: TOTAL DUTIES AND TAXES",
        "-----------------------------------------------------------------",
        f"Total Duties and Taxes = {formula_parts}",
        f"= {math_parts}",
        f"= {_fmt_whole(total)} KHR",
        "",
    ])

    if vvf > 0:
        lines.extend([
            "-----------------------------------------------------------------",
            "STEP 6: VEHICLE VALUATION FEE (VVF)",
            "-----------------------------------------------------------------",
            f"Fee = 60,000 KHR per vehicle unit",
            f"= {_fmt_whole(vvf)} KHR",
            "",
        ])

    return lines


def _format_fta_dq(bd, exchange_rate, total, currency, cif_khr, li, input_currency="USD", input_value=0.0) -> List[str]:
    customs_basis = bd.get("customs_basis", cif_khr)
    original_cop = bd.get("original_cop_amount", 0)
    before_dq_cop = bd.get("before_dq_cop", 0)
    payable_cop = bd.get("cop_amount", 0)
    original_sop = bd.get("original_sop_amount", 0)
    before_dq_sop = bd.get("before_dq_sop", 0)
    payable_sop = bd.get("sop_amount", 0)
    original_vop = bd.get("original_vop_amount", 0)
    before_dq_vop = bd.get("before_dq_vop", 0)
    payable_vop = bd.get("vop_amount", 0)
    bur = bd.get("bur_amount", 0)
    dq_factor = float(bd.get("dq_factor", 0))
    vvf = bd.get("vvf_amount", 0)

    dq_pct = dq_factor * 100
    net_pct = (1 - dq_factor) * 100
    vat_base = customs_basis + original_cop + original_sop

    cd_item = _find_line_item(li, "CD")
    st_item = _find_line_item(li, "ST")
    vat_item = _find_line_item(li, "VAT")
    cd_rate = float(cd_item.get("rate", 0)) if cd_item else 0
    st_rate = float(st_item.get("rate", 0)) if st_item else 0
    vat_rate = float(vat_item.get("rate", 0)) if vat_item else 0

    # Normal (MFN) rates for Original Amount formulas
    cd_rate_normal = float(bd.get("cd_rate_normal", cd_rate))
    st_rate_normal = float(bd.get("st_rate_normal", st_rate))
    vat_rate_normal = float(bd.get("vat_rate_normal", vat_rate))

    if input_currency == "KHR":
        step1 = [
            "-----------------------------------------------------------------",
            "STEP 1: CURRENCY CONFIRMATION (KHR)",
            "-----------------------------------------------------------------",
            f"CIF Value = {_fmt_whole(cif_khr)} KHR (already in local currency)",
            "",
        ]
    else:
        step1 = [
            "-----------------------------------------------------------------",
            "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
            "-----------------------------------------------------------------",
            f"Formula: CIF Value (USD) x Exchange Rate",
            f"= {_fmt_num(cif_khr / exchange_rate if exchange_rate else 0)} x {_fmt_num(exchange_rate)} KHR/USD",
            f"= {_fmt_whole(cif_khr)} KHR",
            "",
        ]

    lines = step1 + [
        "-----------------------------------------------------------------",
        "STEP 2: IMPORT TAXES (COP)",
        "-----------------------------------------------------------------",
        f"Original COP = Customs Value x Normal Import Tax Rate",
        f"= {_fmt_whole(customs_basis)} x {cd_rate_normal:.2f}%",
        f"= {_fmt_whole(original_cop)} KHR",
        f"",
        f"Before-DQ COP = Customs Value x Preferential Rate",
        f"= {_fmt_whole(customs_basis)} x {cd_rate:.2f}%",
        f"= {_fmt_whole(before_dq_cop)} KHR",
        f"",
        f"Payable COP = Before-DQ COP x (1 - DQ)",
        f"= {_fmt_whole(before_dq_cop)} x {net_pct:.0f}%",
        f"= {_fmt_whole(payable_cop)} KHR",
        "",
    ]

    if payable_sop > 0 or before_dq_sop > 0:
        lines.extend([
            "-----------------------------------------------------------------",
            "STEP 3: SPECIAL TARIFF (SOP)",
            "-----------------------------------------------------------------",
            f"SOP Base = Customs Value + Original COP",
            f"= {_fmt_whole(customs_basis)} + {_fmt_whole(original_cop)}",
            f"= {_fmt_whole(customs_basis + original_cop)} KHR",
            f"",
            f"Original SOP = SOP Base x Normal Special Tariff Rate",
            f"= {_fmt_whole(customs_basis + original_cop)} x {st_rate_normal:.2f}%",
            f"= {_fmt_whole(original_sop)} KHR",
            f"",
            f"Before-DQ SOP = SOP Base x Preferential Special Tariff Rate",
            f"= {_fmt_whole(customs_basis + original_cop)} x {st_rate:.2f}%",
            f"= {_fmt_whole(before_dq_sop)} KHR",
            f"",
            f"Payable SOP = Before-DQ SOP x (1 - DQ)",
            f"= {_fmt_whole(before_dq_sop)} x {net_pct:.0f}%",
            f"= {_fmt_whole(payable_sop)} KHR",
            "",
        ])

    lines.extend([
        "-----------------------------------------------------------------",
        "STEP 4: VOP",
        "-----------------------------------------------------------------",
    ])
    if payable_sop == 0 and before_dq_sop == 0:
        lines.append(f"VOP Base = Customs Value + Original COP")
        lines.append(f"= {_fmt_whole(customs_basis)} + {_fmt_whole(original_cop)}")
        lines.append(f"= {_fmt_whole(customs_basis + original_cop)} KHR")
        lines.append(f"")
        lines.append(f"Original VOP = VOP Base x Normal VAT Rate")
        lines.append(f"= {_fmt_whole(customs_basis + original_cop)} x {vat_rate_normal:.2f}%")
        lines.append(f"= {_fmt_whole(original_vop)} KHR")
    else:
        lines.append(f"VOP Base = Customs Value + Original COP + Original SOP")
        lines.append(f"= {_fmt_whole(customs_basis)} + {_fmt_whole(original_cop)} + {_fmt_whole(original_sop)}")
        lines.append(f"= {_fmt_whole(customs_basis + original_cop + original_sop)} KHR")
        lines.append(f"")
        lines.append(f"Original VOP = VOP Base x Normal VAT Rate")
        lines.append(f"= {_fmt_whole(customs_basis + original_cop + original_sop)} x {vat_rate_normal:.2f}%")
        lines.append(f"= {_fmt_whole(original_vop)} KHR")
    lines.append(f"")
    lines.append(f"Before-DQ VOP = VOP Base x Preferential VAT Rate")
    lines.append(f"= {_fmt_whole(vat_base)} x {vat_rate:.2f}%")
    lines.append(f"= {_fmt_whole(before_dq_vop)} KHR")
    lines.append(f"")
    lines.append(f"Payable VOP = Before-DQ VOP x (1 - DQ)")
    lines.append(f"= {_fmt_whole(before_dq_vop)} x {net_pct:.0f}%")
    lines.append(f"= {_fmt_whole(payable_vop)} KHR")
    lines.append("")

    lines.extend([
        "-----------------------------------------------------------------",
        "STEP 5: BUR (BUILD-UP REBATE)",
        "-----------------------------------------------------------------",
        f"Before-DQ COP = Customs Value x Preferential Rate = {_fmt_whole(before_dq_cop)} KHR",
        f"Before-DQ SOP = SOP Base x Preferential ST Rate = {_fmt_whole(before_dq_sop)} KHR",
        f"Before-DQ VOP = VOP Base x Preferential VAT Rate = {_fmt_whole(before_dq_vop)} KHR",
        f"",
        f"BUR = (Before-DQ COP + Before-DQ SOP + Before-DQ VOP) x DQ (Deduction Quantity) Factor",
        f"= ({_fmt_whole(before_dq_cop)} + {_fmt_whole(before_dq_sop)} + {_fmt_whole(before_dq_vop)}) x {dq_pct:.0f}%",
        f"= {_fmt_whole(bur)} KHR",
        "",
        "-----------------------------------------------------------------",
        "STEP 6: TOTAL DUTIES AND TAXES PAYABLE",
        "-----------------------------------------------------------------",
        f"Total = Payable COP + Payable SOP + Payable VOP + VVF",
        f"= {_fmt_whole(payable_cop)} + {_fmt_whole(payable_sop)} + {_fmt_whole(payable_vop)} + {_fmt_whole(vvf)}",
        f"= {_fmt_whole(total)} KHR",
        "",
    ])

    if vvf > 0:
        lines.extend([
            "-----------------------------------------------------------------",
            "STEP 7: VEHICLE VALUATION FEE (VVF)",
            "-----------------------------------------------------------------",
            f"Fee = 60,000 KHR per vehicle unit",
            f"= {_fmt_whole(vvf)} KHR",
            "",
        ])

    return lines


def _build_table(li, total, currency, exchange_rate=None) -> List[str]:
    # Build header dynamically so separator width always matches data rows
    header = f"| {'Tax Component':38} | {'Tax base (KHR)':14} | {'Rate':10} | {'Amount (KHR)':12} |"
    sep    = f"|{'-' * (len(header) - 2)}|"
    lines = [
        sep,
        "FINAL TAX BREAKDOWN",
        sep,
        header,
        sep,
    ]
    for item in li:
        tax_type = item.get("tax_type", "")
        name = (item.get("name") or "")[:38]
        base = _fmt_whole(item.get("base", 0))
        rate = item.get("rate")
        amount = _fmt_whole(item.get("amount", 0))

        # DPP: informational / adjustment row — show base=0 and rate=0.00 per SAD format
        if tax_type == "DPP":
            lines.append(f"| {name:38} | {'0':>14} | {'0.00':>10} | {amount:12} |")
            continue

        # ATP: rate is stored in KHR/L but should display as USD/L
        if tax_type == "ATP" and rate is not None and exchange_rate:
            try:
                rate_usd = float(rate) / float(exchange_rate)
                rate_str = f"{rate_usd:.2f} $/L"
            except (ValueError, TypeError, ZeroDivisionError):
                rate_str = str(rate)
        elif rate is not None:
            try:
                rate_str = f"{float(rate):.2f}"
            except (ValueError, TypeError):
                rate_str = str(rate)
        else:
            rate_str = "0.00"
        lines.append(f"| {name:38} | {base:14} | {rate_str:10} | {amount:12} |")

    total_line = f"| {'TOTAL TAX':38} | {'':14} | {'':10} | {_fmt_whole(total):12} |"
    lines.append(sep)
    lines.append(total_line)
    lines.append(sep)
    lines.append("")
    return lines


def _build_summary(hs_code, description, cif_value_usd, origin, total, currency, li, is_export=False, is_petroleum=False, bd=None, input_currency="USD", input_value=0.0) -> List[str]:
    # Find VOP amount for percentage calculation
    vop_item = _find_line_item(li, "VAT")
    vop_amount = vop_item.get("amount", 0) if vop_item else 0
    total_num = float(total) if total else 0
    vop_pct = (float(vop_amount) / total_num * 100) if total_num else 0

    action = "export" if is_export else "import"
    tax_word = "export taxes" if is_export else "import taxes"

    if input_currency == "KHR":
        lines = [
            "SUMMARY:",
            f"To {action} 1 consignment of {description or 'goods'} ({hs_code or 'N/A'}) valued at",
            f"{_fmt_whole(input_value)} KHR CIF from {origin or 'Unknown'}, you must pay {_fmt_whole(total)} KHR in {tax_word}.",
        ]
    else:
        lines = [
            "SUMMARY:",
            f"To {action} 1 consignment of {description or 'goods'} ({hs_code or 'N/A'}) valued at",
            f"{_fmt_num(cif_value_usd)} USD CIF from {origin or 'Unknown'}, you must pay {_fmt_whole(total)} KHR in {tax_word}.",
        ]
    if is_petroleum and bd:
        p1 = float(bd.get("cpp_amount", 0)) + float(bd.get("atp_amount", 0)) + float(bd.get("spp_amount", 0)) + float(bd.get("vpp_amount", 0))
        p2 = float(bd.get("phase2_total", 0))
        # Cambodian customs rule: importer ALWAYS pays Phase 1 (DV basis).
        # The DPP difference is handled by the state, not added to the importer's bill.
        if p2 > p1:
            lines.append(
                f"Phase 2 (CIF basis) would be higher by {_fmt_whole(abs(p1 - p2))} KHR, "
                f"but importer pays Phase 1 amount. The difference is a state charge (DPP)."
            )
        elif p1 > p2:
            lines.append(
                f"Phase 1 (DV basis) is higher by {_fmt_whole(abs(p1 - p2))} KHR — "
                f"state subsidizes the difference (DPP). Importer pays Phase 1 amount."
            )
        else:
            lines.append("Phase 1 and Phase 2 are equal — no subsidy or additional charge.")
    if vop_pct > 0 and not is_export:
        lines.append(f"The majority is VOP ({vop_pct:.1f}% of total taxes).")
    lines.append("")
    return lines


__all__ = [
    "format_human_readable",
]
