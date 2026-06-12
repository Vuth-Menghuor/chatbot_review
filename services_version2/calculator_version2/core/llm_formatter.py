"""
Calculator LLM Formatter (Standalone)
=====================================
Replaces the optional orchestrator dependency with a local,
calculator-native formatter that calls any LLM via HTTP.

Compatible interface with the old orchestrator LLMFormatter:
  - LLMFormatter
  - FormatterIntent
  - HSCodeInfo

Usage:
    from ..core.llm_formatter import LLMFormatter, FormatterIntent, HSCodeInfo
    formatter = LLMFormatter()
    text = await formatter.format_response(...)
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional
from dataclasses import dataclass
from enum import Enum

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class HSCodeInfo:
    """HS Code information for formatting context."""
    hs_code: str
    description: str
    category: str = ""


class FormatterIntent(str, Enum):
    """Which type of response to format."""
    CALCULATION = "calculation"
    RETRIEVAL = "retrieval"
    TRADE_QUERY = "trade_query"
    POLICY = "policy"
    GENERAL = "general"


class LLMFormatter:
    """
    Format calculation responses using a local or remote LLM.

    Defaults to Ollama (http://127.0.0.1:11434) but can be pointed
    at any OpenAI-compatible endpoint via env vars:
        CALCULATOR_LLM_HOST      (default: 127.0.0.1)
        CALCULATOR_LLM_PORT      (default: 11434)
        CALCULATOR_LLM_MODEL     (default: mistral)
        CALCULATOR_LLM_ENABLED   (default: true)
    """

    def __init__(
        self,
        llm_host: Optional[str] = None,
        llm_port: Optional[int] = None,
        llm_model: Optional[str] = None,
    ):
        settings = get_settings()
        self.llm_host = llm_host or getattr(settings, "llm_host", None) or "127.0.0.1"
        self.llm_port = llm_port or getattr(settings, "llm_port", None) or 11434
        self.llm_url = f"http://{self.llm_host}:{self.llm_port}"
        self.model = llm_model or getattr(settings, "llm_model", None) or "mistral"
        self.enabled = getattr(settings, "llm_enabled", True)

    async def format_response(
        self,
        response_text: str,
        intent: FormatterIntent,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format response based on intent type.

        Args:
            response_text: Raw response from calculator
            intent: Type of response (calculation, retrieval, etc.)
            original_question: User's original question
            context: Additional context (exchange_rate, hs_code_info, rates, etc.)

        Returns:
            Formatted, user-friendly response string
        """
        if not self.enabled:
            logger.debug("LLM formatting disabled - returning raw response")
            return response_text

        try:
            if intent == FormatterIntent.CALCULATION:
                return await self._format_calculation(response_text, original_question, context)
            elif intent == FormatterIntent.RETRIEVAL:
                return await self._format_retrieval(response_text, original_question)
            elif intent == FormatterIntent.TRADE_QUERY:
                return await self._format_trade_query(response_text, original_question)
            elif intent == FormatterIntent.POLICY:
                return await self._format_policy(response_text, original_question)
            else:
                return await self._format_generic(response_text, original_question)
        except Exception as e:
            logger.warning(f"LLM formatting failed: {e}. Returning raw response.")
            return response_text

    def format_response_sync(
        self,
        response_text: str,
        intent: FormatterIntent,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Synchronous wrapper for environments that can't await."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is None:
            return asyncio.run(self.format_response(response_text, intent, original_question, context))
        # If already inside an event loop, schedule and return raw to avoid blocking
        logger.debug("format_response_sync called inside running loop; returning raw text")
        return response_text

    # ------------------------------------------------------------------
    # Internal formatters
    # ------------------------------------------------------------------

    async def _format_calculation(
        self,
        response_text: str,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        context = context or {}
        breakdown = self._build_calculation_breakdown(response_text, original_question, context)

        llm_prompt = f"""You are a customs expert. Format this tax calculation showing step-by-step formulas.

Base Answer: {response_text}
Question: {original_question}

{breakdown}

INCLUDE in response:
1. Product information and HS code details
2. Input parameters (CIF value, currency, origin)
3. Exchange rate conversion IF currencies differ (formula: value_usd x exchange_rate)
4. STEP-BY-STEP calculation with FORMULAS for each tax:
   - Step 1: Convert CIF value to KHR
   - Step 2: Calculate Customs Duty (formula: cif_value_khr x duty_rate)
   - Step 3: Calculate Special Tax
   - Step 4: Calculate VAT
   - Step 5: Calculate Excise Tax (if applicable)
5. Final breakdown table with all components
6. TOTAL TAX prominently displayed
7. Assumptions and data sources

Format with:
- Clear section headers with --- lines
- Professional table format for breakdown
- Formulas shown explicitly
- All values with units (KHR, USD, %, etc.)

Do NOT abbreviate tax terms on first mention."""

        try:
            return await self._call_llm(llm_prompt)
        except Exception as e:
            logger.warning(f"LLM formatting for calculation failed: {e}")
            return self._fallback_calculation_format(response_text, context)

    def _build_calculation_breakdown(
        self,
        response_text: str,
        original_question: str,
        context: Dict[str, Any],
    ) -> str:
        hs_code_info = context.get("hs_code_info")
        exchange_rate = context.get("exchange_rate", 4022)
        cif_value = context.get("cif_value", "N/A")
        cif_currency = context.get("cif_currency", "USD")
        origin = context.get("origin_country", "Unknown")
        rates = context.get("rates", {})

        breakdown_match = re.search(r"CD=(\d+), ST=(\d+), VAT=(\d+), ET=(\d+)", response_text)
        if breakdown_match:
            cd, st, vat, et = breakdown_match.groups()
        else:
            cd = st = vat = et = 0

        return f"""
CALCULATION CONTEXT:
- HS Code: {hs_code_info.hs_code if hs_code_info else 'Unknown'}
- Description: {hs_code_info.description if hs_code_info else 'Unknown'}
- CIF Value: {cif_value} {cif_currency}
- Origin: {origin}
- Exchange Rate: 1 {cif_currency} = {exchange_rate} KHR

STEP-BY-STEP CALCULATION:
1. Currency Conversion: {cif_value} {cif_currency} x {exchange_rate}
2. Customs Duty: {rates.get('cd_rate', 0)}% applied = {cd} KHR
3. Special Tax: {rates.get('st_rate', 0)}% applied = {st} KHR
4. Value Added Tax (VAT): {rates.get('vat_rate', 0.10) * 100}% applied = {vat} KHR
5. Excise Tax: {rates.get('et_rate', 0)}% applied = {et} KHR

TOTAL TAX: {int(cd) + int(st) + int(vat) + int(et)} KHR
"""

    def _fallback_calculation_format(
        self,
        response_text: str,
        context: Dict[str, Any],
    ) -> str:
        hs_code_info = context.get("hs_code_info")
        exchange_rate = context.get("exchange_rate", 4022)
        total_match = re.search(r"Total: (\d+)", response_text)
        total = total_match.group(1) if total_match else "Unknown"

        return f"""
IMPORT TAX CALCULATION RESULT
{'-' * 50}

Product: {hs_code_info.description if hs_code_info else 'N/A'}
HS Code: {hs_code_info.hs_code if hs_code_info else 'N/A'}

Exchange Rate: 1 USD = {exchange_rate} KHR

{response_text}

TOTAL: {total} KHR
{'-' * 50}

For detailed calculation steps, enable LLM formatting.
"""

    async def _format_retrieval(
        self, response_text: str, original_question: str
    ) -> str:
        llm_prompt = f"""Format this HS code lookup result clearly:

Question: {original_question}
Result: {response_text}

Include:
- HS Code and full description
- Product classification
- Any relevant notes
- Sources if available

Format with clear structure."""
        try:
            return await self._call_llm(llm_prompt)
        except Exception:
            return response_text

    async def _format_trade_query(
        self, response_text: str, original_question: str
    ) -> str:
        llm_prompt = f"""Format this trade data result clearly:

Question: {original_question}
Data: {response_text}

Include statistics in readable format with explanations."""
        try:
            return await self._call_llm(llm_prompt)
        except Exception:
            return response_text

    async def _format_policy(
        self, response_text: str, original_question: str
    ) -> str:
        return response_text

    async def _format_generic(
        self, response_text: str, original_question: str
    ) -> str:
        return response_text

    async def generate(self, prompt: str) -> str:
        """Public entry point for raw prompt generation."""
        return await self._call_llm(prompt)

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM endpoint (Ollama-style /api/generate by default)."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.llm_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def disable(self) -> None:
        self.enabled = False
        logger.info("LLM formatting disabled")

    def enable(self) -> None:
        self.enabled = True
        logger.info("LLM formatting enabled")

    def is_available(self) -> bool:
        return self.enabled


# Backward-compatible names for any external references
CalculatorResponse = None  # not used in calculator-native path
LLMFormatterConfig = None
LLMResponseFormatter = None

# ============================================================================
# Human-Readable Formatter (No LLM Required)
# ============================================================================

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

    # --- HEADER ---
    lines = [
        "-----------------------------------------------------------------",
        "IMPORT TAX CALCULATION",
        "-----------------------------------------------------------------",
        "",
        "PRODUCT INFORMATION:",
        f"* HS Code: {hs_code or 'N/A'} ({description or 'N/A'})",
        f"* Origin Country: {origin or 'General rates'}",
        f"* Incoterm: CIF (Cost, Insurance, Freight)",
        "",
        "INPUT PARAMETERS:",
        f"* CIF Value: {_fmt_num(cif_value_usd)} USD",
        f"* Exchange Rate: 1 USD = {_fmt_num(exchange_rate)} KHR",
        f"* Customs Regime: {_regime_label(regime, is_fta)}",
        f"* Calculation Date: {calc_date}",
        "",
    ]

    cif_khr = bd.get("cif_value", 0)

    # --- PETROLEUM CASE ---
    if is_petroleum:
        lines.extend(_format_petroleum(bd, exchange_rate, total, currency, cif_khr, li))
    # --- RUBBER CASE ---
    elif is_rubber and is_export:
        lines.extend(_format_rubber(bd, exchange_rate, total, currency, cif_khr))
    # --- NORMAL / FTA CASE ---
    else:
        lines.extend(_format_normal(bd, exchange_rate, total, currency, cif_khr, is_fta))

    # --- TABLE ---
    lines.extend(_build_table(li, total, currency, exchange_rate))

    # --- SUMMARY ---
    lines.extend(_build_summary(hs_code, description, cif_value_usd, origin, total, currency, li))

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


def _regime_label(regime: Optional[str], fta: bool) -> str:
    r = (regime or "").lower()
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


def _format_petroleum(bd, exchange_rate, total, currency, cif_khr, li) -> List[str]:
    cpp_base = bd.get("cpp_base", 0)
    cpp = bd.get("cpp_amount", 0)
    atp = bd.get("atp_amount", 0)
    spp = bd.get("spp_amount", 0)
    vpp = bd.get("vpp_amount", 0)
    dpp = bd.get("dpp_amount", 0)
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

    lines = [
        "-----------------------------------------------------------------",
        "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
        "-----------------------------------------------------------------",
        f"Formula: CIF Value (USD) x Exchange Rate",
        f"= {_fmt_num(cif_khr / exchange_rate if exchange_rate else 0)} x {_fmt_num(exchange_rate)} KHR/USD",
        f"= {_fmt_whole(cif_khr)} KHR",
        "",
        "-----------------------------------------------------------------",
        "STEP 2: PHASE 1 -- PETROLEUM TAX (Declared Value Basis)",
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
        f"CPP base  = CIF value = {_fmt_whole(cif_khr)} KHR",
        f"CPP       = CPP base x CD rate = {_fmt_whole(p2_cpp)} KHR",
        f"ATP       = same as Phase 1 = {_fmt_whole(p2_atp)} KHR",
        f"SPP       = (CPP base + CPP + ATP) x ST rate = {_fmt_whole(p2_spp)} KHR",
        f"VPP       = (CPP base + CPP + ATP + SPP) x VAT rate = {_fmt_whole(p2_vpp)} KHR",
        f"Phase 2 Total = {_fmt_whole(p2_total)} KHR",
        "",
        "-----------------------------------------------------------------",
        "STEP 4: DIFFERENCE / PARTIAL SUBSIDY (DPP)",
        "-----------------------------------------------------------------",
        f"DPP = Phase 1 Total - Phase 2 Total",
        f"    = {_fmt_whole(cpp + atp + spp + vpp)} - {_fmt_whole(p2_total)}",
        f"    = {_fmt_whole(dpp)} KHR",
        "",
    ]
    return lines


def _format_rubber(bd, exchange_rate, total, currency, cif_khr) -> List[str]:
    etr = bd.get("etr_amount", 0)
    lines = [
        "-----------------------------------------------------------------",
        "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
        "-----------------------------------------------------------------",
        f"Formula: CIF Value (USD) x Exchange Rate",
        f"= {_fmt_num(cif_khr / exchange_rate if exchange_rate else 0)} x {_fmt_num(exchange_rate)} KHR/USD",
        f"= {_fmt_whole(cif_khr)} KHR",
        "",
        "-----------------------------------------------------------------",
        "STEP 2: EXPORT TAX ON RUBBER (ETR)",
        "-----------------------------------------------------------------",
        f"ETR = (CIF_KHR / net_mass_kg) x ET rate",
        f"    = {_fmt_whole(etr)} KHR",
        "",
    ]
    return lines


def _format_normal(bd, exchange_rate, total, currency, cif_khr, is_fta) -> List[str]:
    cop = bd.get("cop_amount", 0)
    sop = bd.get("sop_amount", 0)
    vop = bd.get("vop_amount", 0)
    vvf = bd.get("vvf_amount", 0)
    fees = bd.get("fees", 0)
    customs_basis = bd.get("customs_basis", cif_khr)

    lines = [
        "-----------------------------------------------------------------",
        "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
        "-----------------------------------------------------------------",
        f"Formula: CIF Value (USD) x Exchange Rate",
        f"= {_fmt_num(cif_khr / exchange_rate if exchange_rate else 0)} x {_fmt_num(exchange_rate)} KHR/USD",
        f"= {_fmt_whole(cif_khr)} KHR",
        "",
        "-----------------------------------------------------------------",
        "STEP 2: IMPORT TAXES (COP)",
        "-----------------------------------------------------------------",
        f"Formula: CIF Value (KHR) x CD rate",
        f"= {_fmt_whole(cif_khr)} x CD rate",
        f"= {_fmt_whole(cop)} KHR",
        "",
        "-----------------------------------------------------------------",
        "STEP 3: SPECIAL TARIFF (SOP)",
        "-----------------------------------------------------------------",
        f"Formula: (CIF Value + COP) x ST rate",
        f"= {_fmt_whole(cif_khr + cop)} x ST rate",
        f"= {_fmt_whole(sop)} KHR",
        "",
        "-----------------------------------------------------------------",
        "STEP 4: VALUE ADDED TAX (VOP)",
        "-----------------------------------------------------------------",
    ]
    if sop == 0:
        lines.append(f"Formula: (CIF Value + COP) x VAT rate")
        lines.append(f"= {_fmt_whole(cif_khr + cop)} x VAT rate")
    else:
        lines.append(f"Formula: (CIF Value + COP + SOP) x VAT rate")
        lines.append(f"= {_fmt_whole(cif_khr + cop + sop)} x VAT rate")
    lines.append(f"= {_fmt_whole(vop)} KHR")
    lines.append("")

    if vvf > 0:
        lines.extend([
            "-----------------------------------------------------------------",
            "STEP 5: VEHICLE VALUATION FEE (VVF)",
            "-----------------------------------------------------------------",
            f"Fee = 60,000 KHR per vehicle unit",
            f"= {_fmt_whole(vvf)} KHR",
            "",
        ])

    return lines


def _build_table(li, total, currency, exchange_rate=None) -> List[str]:
    lines = [
        "-----------------------------------------------------------------",
        "FINAL TAX BREAKDOWN",
        "-----------------------------------------------------------------",
        "| Tax Component                          | Tax base (KHR) | Rate       | Amount (KHR) |",
        "|----------------------------------------------------------------------------------|",
    ]
    for item in li:
        name = (item.get("name") or "")[:38]
        base = _fmt_whole(item.get("base", 0))
        rate = item.get("rate")
        amount = _fmt_whole(item.get("amount", 0))
        tax_type = item.get("tax_type", "")

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
        lines.append(f"| {name:38} | {base:14} | {rate_str:>10} | {amount:12} |")

    lines.append("|----------------------------------------------------------------------------------|")
    lines.append(f"| TOTAL TAX                              |                |            | {_fmt_whole(total):12} |")
    lines.append("|----------------------------------------------------------------------------------|")
    lines.append("")
    return lines


def _build_summary(hs_code, description, cif_value_usd, origin, total, currency, li) -> List[str]:
    # Find VAT amount for percentage calculation
    vat_item = _find_line_item(li, "VAT")
    vat_amount = vat_item.get("amount", 0) if vat_item else 0
    total_num = float(total) if total else 0
    vat_pct = (float(vat_amount) / total_num * 100) if total_num else 0

    lines = [
        "SUMMARY:",
        f"To import 1 consignment of {description or 'goods'} ({hs_code or 'N/A'}) valued at",
        f"{_fmt_num(cif_value_usd)} USD CIF from {origin or 'Unknown'}, you must pay {_fmt_whole(total)} KHR in import taxes.",
    ]
    if vat_pct > 0:
        lines.append(f"The majority is VAT ({vat_pct:.1f}% of total taxes).")
    lines.append("")
    return lines


__all__ = [
    "HSCodeInfo",
    "FormatterIntent",
    "LLMFormatter",
    "format_human_readable",
]
