"""
GDCE Calculator Service - API Endpoints
=======================================
HTTP layer for calculator microservice. Uses FastAPI, depends on core
business logic (ImportTaxCalculator) and CSV-backed infrastructure.

Integrated with:
- CurrencyHandler: For flexible currency input/output
- HSCodeHandler: For HS code lookup and candidates
- LLMFormatter: For user-friendly response formatting (calculator-native, no orchestrator required)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from .deps import get_db
from .schemas import (
    CalculateImportTaxesRequest,
    CalculateImportTaxesResponse,
    DirectQueryRequest,
    DirectQueryResponse,
    FlagsModel,
    GoodsModel,
    HSCodeExtractRequest,
    HSCodeExtractResponse,
    HSCodeInfoModel,
    HSCodeLookupRequest,
    HSCodeLookupResponse,
    NaturalLanguageRequest,
    NaturalLanguageResponse,
    ValuationModel,
    ErrorResponse,
)
from ..core.calculator import CalculationRequest, ImportTaxCalculator
from ..core.intent_extractor import IntentExtractor, IntentResult
from ..core.llm_formatter import format_human_readable, LLMFormatter
from ..core.models import TaxReference

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", tags=["Health"], summary="Service info")
async def root() -> Dict[str, Any]:
    """Return basic service metadata."""
    return {
        "service": "GDCE Calculator Service",
        "version": "2.0.0",
        "status": "ready",
        "endpoints": {
            "health": "/health",
            "calculate": "/calculate_import_taxes",
            "docs": "/docs",
        },
    }


@router.get("/health", tags=["Health"], summary="Health check")
async def health(db=Depends(get_db)) -> Dict[str, Any]:
    """Return service health status including database availability."""
    db_status = db.check_health()
    return {
        "status": "healthy" if db_status.get("ok") else "degraded",
        "service": "GDCE Calculator Service",
        "version": "2.0.0",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/diagnostics", tags=["Health"], summary="Deep diagnostics & smoke tests")
async def diagnostics(db=Depends(get_db), fastapi_request: Request = None) -> Dict[str, Any]:
    """
    Automated self-test endpoint.

    Runs smoke tests against all major subsystems and returns a structured
    report with pass/fail status and timing for each check.

    Checks performed:
    - Database connectivity (CalculatorDB, Qdrant, PostgreSQL, CSV)
    - Rules engine availability (provider + formula engine)
    - Exchange rate lookup (USD -> KHR)
    - Duty rate lookup (sample petroleum HS code)
    - End-to-end calculation smoke test
    """
    import time

    start = time.time()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    results: Dict[str, Any] = {
        "overall_status": "unknown",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
    }

    # 1. Database / infrastructure health
    t0 = time.time()
    try:
        db_health = db.check_health()
        db_ok = db_health.get("ok", False)
        results["checks"]["database"] = {
            "status": "pass" if db_ok else "fail",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "details": db_health,
        }
    except Exception as exc:
        results["checks"]["database"] = {
            "status": "fail",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "error": str(exc),
        }

    # 2. Rules engine availability
    t0 = time.time()
    try:
        rules_provider = (
            getattr(fastapi_request.app.state, "rules_provider", None)
            if fastapi_request else None
        )
        formula_engine = (
            getattr(fastapi_request.app.state, "formula_engine", None)
            if fastapi_request else None
        )
        results["checks"]["rules_engine"] = {
            "status": "pass" if (rules_provider and formula_engine) else "degraded",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "rules_provider_loaded": rules_provider is not None,
            "formula_engine_loaded": formula_engine is not None,
        }
    except Exception as exc:
        results["checks"]["rules_engine"] = {
            "status": "fail",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "error": str(exc),
        }

    # 3. Exchange rate lookup smoke test
    t0 = time.time()
    try:
        rate = db.get_exchange_rate("USD", effective_date=today)
        results["checks"]["exchange_rate_lookup"] = {
            "status": "pass" if rate is not None else "fail",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "currency": "USD",
            "khr_rate": float(rate) if rate is not None else None,
        }
    except Exception as exc:
        results["checks"]["exchange_rate_lookup"] = {
            "status": "fail",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "error": str(exc),
        }

    # 4. Duty rate lookup smoke test (petroleum — guaranteed by hardcoded fallback)
    t0 = time.time()
    sample_hs = "2710.12.11"
    try:
        rates = db.get_duty_rates(sample_hs, origin_country="XX", effective_date=today)
        results["checks"]["duty_rate_lookup"] = {
            "status": "pass" if rates is not None else "fail",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "sample_hs_code": sample_hs,
            "rates_found": rates is not None,
        }
    except Exception as exc:
        results["checks"]["duty_rate_lookup"] = {
            "status": "fail",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "error": str(exc),
        }

    # 5. End-to-end calculation smoke test
    t0 = time.time()
    try:
        rules_provider = (
            getattr(fastapi_request.app.state, "rules_provider", None)
            if fastapi_request else None
        )
        formula_engine = (
            getattr(fastapi_request.app.state, "formula_engine", None)
            if fastapi_request else None
        )
        calculator = ImportTaxCalculator(
            db, rules_provider=rules_provider, formula_engine=formula_engine
        )

        calc_request = CalculationRequest(
            calculation_date=today,
            regime="import",
            goods={
                "description": "Gasoline",
                "hs_code": sample_hs,
                "volume_liter": 1000,
                "net_mass_kg": 750,
            },
            valuation={"customs_value": 50000, "currency": "USD"},
            flags={"petroleum_case": True},
        )
        result = calculator.calculate(calc_request)
        result_dict = result.to_dict()
        results["checks"]["smoke_calculation"] = {
            "status": "pass",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "calculation_id": result_dict.get("calculation_id"),
            "total": result_dict.get("total"),
            "currency": result_dict.get("currency"),
        }
    except Exception as exc:
        results["checks"]["smoke_calculation"] = {
            "status": "fail",
            "duration_ms": round((time.time() - t0) * 1000, 2),
            "error": str(exc),
        }

    # Overall verdict
    total_duration = round((time.time() - start) * 1000, 2)
    check_statuses = [c.get("status") for c in results["checks"].values()]
    all_pass = all(s == "pass" for s in check_statuses)
    any_fail = any(s == "fail" for s in check_statuses)

    results["total_duration_ms"] = total_duration
    results["overall_status"] = (
        "healthy" if all_pass else ("degraded" if not any_fail else "unhealthy")
    )

    return results


@router.get("/lookup/duty-rate", tags=["Lookup"], summary="Duty rate lookup")
async def lookup_duty_rate(
    hs_code: str,
    origin_country: str = "XX",
    effective_date: str | None = None,
    db=Depends(get_db),
) -> Dict[str, Any]:
    date_str = effective_date or datetime.utcnow().strftime("%Y-%m-%d")
    rates = db.get_duty_rates(hs_code=hs_code, origin_country=origin_country, effective_date=date_str)
    hs_info = db.get_hs_code_info(hs_code)

    if not rates:
        return {
            "found": False,
            "hs_code": hs_code,
            "origin_country": origin_country,
            "effective_date": date_str,
        }

    return {
        "found": True,
        "hs_code": hs_code,
        "origin_country": origin_country,
        "effective_date": date_str,
        "rates": rates,
        "hs_info": hs_info,
        "source": "duty_rates_table",
    }


@router.get("/lookup/hs-info", tags=["Lookup"], summary="HS code info")
async def lookup_hs_info(hs_code: str, db=Depends(get_db)) -> Dict[str, Any]:
    info = db.get_hs_code_info(hs_code)
    return {"found": bool(info), "hs_code": hs_code, "hs_info": info}


@router.get("/lookup/exchange-rate", tags=["Lookup"], summary="Exchange rate lookup")
async def lookup_exchange_rate(
    currency: str,
    effective_date: str | None = None,
    db=Depends(get_db),
) -> Dict[str, Any]:
    date_str = effective_date or datetime.utcnow().strftime("%Y-%m-%d")
    rate = db.get_exchange_rate(currency_code=currency.upper(), effective_date=date_str)
    return {
        "found": rate is not None,
        "currency": currency.upper(),
        "effective_date": date_str,
        "khr_rate": rate,
        "source": "exchange_rates_table",
    }


@router.get("/lookup/vat-formula", tags=["Lookup"], summary="VAT formula description")
async def lookup_vat_formula() -> Dict[str, str]:
    return {
        "formula": "VOP = (Customs Value + COP + SOP) x 10% (taxable goods); if SOP=0 then VOP = (Customs Value + COP) x 10%",
        "source": "calculator_formula_registry",
    }


@router.post(
    "/lookup/hs-code-from-product",
    tags=["Lookup"],
    summary="HS code from product description",
)
async def lookup_hs_code_from_product(
    request: HSCodeLookupRequest,
    db=Depends(get_db),
) -> Dict[str, Any]:
    """
    Resolve a product description to one or more HS code candidates.

    Uses semantic search (Qdrant when available) or CSV fuzzy fallback.
    Returns candidates sorted by confidence. If no candidates found,
    the caller should fail fast rather than ask the user to confirm.
    """
    description = request.product_description
    top_k = request.top_k

    # Try semantic search first (Qdrant)
    candidates: list[dict] = []
    qdrant_results = db.search_hs_by_description(description, top_k=top_k)
    if qdrant_results:
        for item in qdrant_results:
            hs = item.get("hs_code") or item.get("code")
            if hs:
                candidates.append({
                    "hs_code": hs,
                    "description": item.get("description", ""),
                    "confidence": item.get("score", item.get("confidence", 0.0)),
                    "source": "qdrant",
                })

    # Fallback to CSV / legacy search if Qdrant returned nothing
    if not candidates:
        result = db.search_by_description(description)
        if result:
            hs_code, confidence = result
            info = db.get_hs_code_info(hs_code)
            candidates.append({
                "hs_code": hs_code,
                "description": info.get("description", "") if info else "",
                "confidence": confidence,
                "source": "csv_description_search",
            })

    if not candidates:
        return {
            "found": False,
            "product_description": description,
            "candidates": [],
            "message": "Could not determine HS code for this product.",
        }

    # Enrich top candidate with duty rates for convenience
    top = candidates[0]
    rates = db.get_duty_rates(
        hs_code=top["hs_code"],
        origin_country="XX",
        effective_date=datetime.utcnow().strftime("%Y-%m-%d"),
    )
    if rates:
        top["duty_rates"] = rates

    return {
        "found": True,
        "product_description": description,
        "candidates": candidates,
        "message": None,
    }


@router.post(
    "/lookup/hs-code-candidates",
    tags=["Lookup"],
    summary="Get HS code candidate suggestions",
)
async def get_hs_code_candidates(
    query: str,
    limit: int = 5,
    db=Depends(get_db),
) -> Dict[str, Any]:
    """
    Get candidate HS codes for a query (description or partial code).
    
    Used for fallback scenarios where HS code is not provided or is unknown.
    Returns a list of matching HS codes with descriptions and confidence scores.
    
    Args:
        query: Search query (product description or partial HS code)
        limit: Maximum number of candidates (default: 5)
        
    Returns:
        Dict with list of candidates containing: hs_code, description, score
    """
    try:
        calculator = ImportTaxCalculator(db)
        candidates = calculator.get_hs_code_candidates(query, limit=limit)
        
        return {
            "found": len(candidates) > 0,
            "query": query,
            "limit": limit,
            "count": len(candidates),
            "candidates": candidates,
            "source": "hs_code_lookup",
        }
    except Exception as exc:
        return {
            "found": False,
            "query": query,
            "error": str(exc),
            "candidates": [],
        }


@router.post(
    "/lookup/extract-hs-code",
    tags=["Lookup"],
    summary="Extract and normalize HS code from free text (LLM + regex)",
    response_model=HSCodeExtractResponse,
)
async def extract_hs_code_from_text(
    request: HSCodeExtractRequest,
    db=Depends(get_db),
) -> HSCodeExtractResponse:
    """
    Extract an HS code from free-form user text.

    Tries LLM first (if enabled) to intelligently find and normalize HS codes,
    especially bare 8-digit numbers like '12345678' → '1234.56.78'.
    Falls back to deterministic regex if LLM is disabled or fails.
    """
    text = request.text

    # --- Try LLM first ---
    formatter = LLMFormatter()
    if formatter.enabled:
        try:
            llm_result = await formatter.extract_hs_code(text)
            if llm_result:
                return HSCodeExtractResponse(
                    found=True,
                    hs_code=llm_result,
                    raw_input=text,
                    source="llm",
                    message=f"LLM extracted and normalized HS code from text",
                )
        except Exception as e:
            logger.warning(f"LLM HS code extraction failed: {e}")

    # --- Fallback: deterministic regex ---
    if request.fallback_to_regex:
        # Match dotted or bare 6/8 digit codes
        pattern = r"\b(\d{4}(?:\.\d{2}){0,2}|\d{6}|\d{8})\b"
        match = re.search(pattern, text)
        if match:
            raw = match.group(1)
            calculator = ImportTaxCalculator(db)
            normalized = calculator.hs_code_handler.normalize_code(raw)
            if normalized:
                return HSCodeExtractResponse(
                    found=True,
                    hs_code=normalized,
                    raw_input=raw,
                    source="regex",
                    message=f"Regex extracted and normalized HS code",
                )

    return HSCodeExtractResponse(
        found=False,
        hs_code=None,
        raw_input=text,
        source="none",
        message="No HS code found in text",
    )


def _build_calc_request(
    request: CalculateImportTaxesRequest,
    calculator: ImportTaxCalculator
) -> tuple[CalculationRequest, str | None, str | None, str | None]:
    """Build core CalculationRequest with currency, CIF, and HS resolution."""
    resolved_currency = request.valuation.currency
    currency_assumption = None
    cif_assumption = None
    hs_assumption = None

    # --- Currency resolution ---
    if not resolved_currency:
        origin = request.goods.origin_country
        if origin:
            inferred = calculator.currency_handler.infer_currency_from_country(origin)
            if inferred:
                resolved_currency = inferred
                currency_assumption = (
                    f"Currency not specified - inferred as {inferred} "
                    f"from origin country '{origin}'"
                )
                logger.info(f" {currency_assumption}")
        if not resolved_currency:
            resolved_currency = "KHR"
            currency_assumption = (
                "Currency not specified and no origin country provided - "
                "defaulting to KHR (Cambodian Riel)"
            )
            logger.info(f" {currency_assumption}")

    # --- CIF default: when user provides no value, default to 8000 ---
    customs_value = request.valuation.customs_value
    if customs_value is None or customs_value <= 0:
        customs_value = 8000.0
        cif_assumption = (
            "CIF value was not provided by the user. "
            "A default value of 8,000.00 USD has been set for estimation purposes. "
            "Please provide the actual CIF value for an accurate calculation."
        )
        logger.info(f" CIF value defaulted to 8000 USD (user did not provide)")

    goods_dict = request.goods.dict(exclude_none=True)

    # --- HS code resolution from commercial description (JSON/text endpoints) ---
    # If no HS code was provided but a product description was, attempt to resolve
    if not goods_dict.get("hs_code") and goods_dict.get("description"):
        desc = goods_dict.get("description", "").strip()
        if desc and desc not in ("General merchandise", "Petroleum products", "Rubber products"):
            resolved_hs, resolved_source, _ = calculator.resolve_hs_from_description(desc)
            if resolved_hs:
                goods_dict["hs_code"] = resolved_hs
                hs_assumption = (
                    f"⚠️  HS code {resolved_hs} was auto-resolved from the product description "
                    f"'{desc}' via {resolved_source} search. This HS code may not be fully correct "
                    f"because you did not provide a clear description or an explicit HS code. "
                    f"Please verify the HS code with customs or provide the exact HS code for an accurate calculation."
                )
                logger.info(f" JSON endpoint auto-resolved HS {resolved_hs} from description '{desc}'")

    valuation_dict = request.valuation.dict(exclude_none=True)
    valuation_dict["currency"] = resolved_currency
    valuation_dict["customs_value"] = customs_value

    calc_request = CalculationRequest(
        calculation_date=request.calculation_date,
        regime=request.regime,
        goods=goods_dict,
        valuation=valuation_dict,
        flags=request.flags.dict(exclude_none=True) if request.flags else {},
        requested_breakdown=request.requested_breakdown,
    )

    # Normalize HS code
    if calc_request.hs_code:
        try:
            normalized_hs = calculator.hs_code_handler.normalize_code(calc_request.hs_code)
            calc_request.goods["hs_code"] = normalized_hs
            logger.debug(f"HS code normalized: {calc_request.hs_code} -> {normalized_hs}")
        except Exception as e:
            logger.warning(f"Failed to normalize HS code '{calc_request.hs_code}': {e}")

    return calc_request, currency_assumption, cif_assumption, hs_assumption


@router.post(
    "/calculate_import_taxes",
    tags=["Calculation"],
    response_model=CalculateImportTaxesResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def calculate_import_taxes(
    request: CalculateImportTaxesRequest,
    db=Depends(get_db),
    fastapi_request: Request = None,
) -> CalculateImportTaxesResponse:
    """
    Main calculation endpoint (JSON response).

    Automatically generates a human-readable report via LLM if available,
    otherwise uses the fast programmatic formatter.

    Args:
        request: Calculation request with goods, valuation, and flags
        db: Database connection dependency

    Returns:
        CalculateImportTaxesResponse with calculation results and human-readable report
    """
    try:
        rules_provider = (
            getattr(fastapi_request.app.state, "rules_provider", None)
            if fastapi_request else None
        )
        formula_engine = (
            getattr(fastapi_request.app.state, "formula_engine", None)
            if fastapi_request else None
        )
        calculator = ImportTaxCalculator(db, rules_provider=rules_provider, formula_engine=formula_engine)

        calc_request, currency_assumption, cif_assumption, hs_assumption = _build_calc_request(request, calculator)
        result = calculator.calculate(calc_request)
        result_dict = _enrich_result(result.to_dict(), calc_request, request, calculator, currency_assumption, cif_assumption, hs_assumption)

        # Generate human-readable report (LLM first, then programmatic fallback)
        llm_text = await _try_llm_human_readable(calc_request, result_dict, calculator)
        if llm_text:
            result_dict["human_readable"] = llm_text
        else:
            try:
                result_dict["human_readable"] = format_human_readable(calc_request, result_dict)
            except Exception as e:
                logger.debug(f"Programmatic human-readable formatting failed: {e}")

        return CalculateImportTaxesResponse(**result_dict)

    except ValueError as exc:  # validation errors from core
        error_msg = f"Validation error: {str(exc)}"
        logger.error(f" {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg) from exc
    except KeyError as exc:  # missing required fields
        error_msg = f"Missing required field: {str(exc)}"
        logger.error(f" {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg) from exc
    except Exception as exc:  # catch-all
        error_msg = f"Internal server error: {str(exc)}"
        logger.exception(f" {error_msg}")
        raise HTTPException(status_code=500, detail="Internal server error during calculation") from exc


# ============================================================================
# Shared enrichment helper
# ============================================================================

def _enrich_result(
    result_dict: Dict[str, Any],
    calc_request: CalculationRequest,
    request: CalculateImportTaxesRequest,
    calculator: ImportTaxCalculator,
    currency_assumption: str | None,
    cif_assumption: str | None = None,
    hs_assumption: str | None = None,
) -> Dict[str, Any]:
    """Add currency notes, CIF notes, HS resolution warnings, HS code info, and human-readable text to result."""
    if "assumptions" not in result_dict or result_dict["assumptions"] is None:
        result_dict["assumptions"] = []

    if hs_assumption:
        result_dict["assumptions"].insert(0, hs_assumption)

    if cif_assumption:
        result_dict["assumptions"].insert(0, cif_assumption)

    if currency_assumption:
        result_dict["assumptions"].insert(0, currency_assumption)

    # Currency note
    input_currency = calc_request.currency
    output_currency = result_dict.get("currency", "KHR")
    if input_currency and input_currency != output_currency:
        result_dict["currency_note"] = calculator.currency_handler.get_currency_note(
            input_currency, output_currency,
            exchange_rate=result_dict.get("exchange_rate_usd_to_khr"),
            calculation_date=request.calculation_date,
        )

    # HS code info
    hs_code_to_lookup = calc_request.hs_code
    if hs_code_to_lookup:
        try:
            hs_code_info = calculator.hs_code_handler.get_code_info(hs_code_to_lookup)
            if hs_code_info:
                result_dict["hs_code_info"] = HSCodeInfoModel(
                    hs_code=hs_code_info["hs_code"],
                    description=hs_code_info.get("description"),
                    unit=hs_code_info.get("unit"),
                    level=calculator.hs_code_handler.get_child_level(hs_code_to_lookup),
                ).dict(exclude_none=True)
        except Exception as e:
            logger.debug(f"Failed to get HS code info for '{hs_code_to_lookup}': {e}")

    return result_dict


# ============================================================================
# Text-only endpoint
# ============================================================================

@router.post(
    "/calculate_import_taxes/text",
    tags=["Calculation"],
    response_class=PlainTextResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def calculate_import_taxes_text(
    request: CalculateImportTaxesRequest,
    db=Depends(get_db),
    fastapi_request: Request = None,
) -> PlainTextResponse:
    """
    Same calculation as /calculate_import_taxes but returns plain text.

    Useful for CLI tools, chat bots, or any client that just wants
    the human-readable report without parsing JSON.
    """
    try:
        rules_provider = (
            getattr(fastapi_request.app.state, "rules_provider", None)
            if fastapi_request else None
        )
        formula_engine = (
            getattr(fastapi_request.app.state, "formula_engine", None)
            if fastapi_request else None
        )
        calculator = ImportTaxCalculator(db, rules_provider=rules_provider, formula_engine=formula_engine)

        calc_request, currency_assumption, cif_assumption, hs_assumption = _build_calc_request(request, calculator)
        result = calculator.calculate(calc_request)
        result_dict = _enrich_result(result.to_dict(), calc_request, request, calculator, currency_assumption, cif_assumption, hs_assumption)

        # Generate human-readable report (LLM first, then programmatic fallback)
        llm_text = await _try_llm_human_readable(calc_request, result_dict, calculator)
        if llm_text:
            text = llm_text
        else:
            try:
                text = format_human_readable(calc_request, result_dict)
            except Exception as e:
                logger.debug(f"Programmatic human-readable formatting failed: {e}")
                # Fallback: return raw JSON as pretty-printed text
                import json
                text = json.dumps(result_dict, indent=2, default=str)

        return PlainTextResponse(content=text, media_type="text/plain; charset=utf-8")

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Validation error: {exc}") from exc
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Missing required field: {exc}") from exc
    except Exception as exc:
        logger.exception(f"Internal server error: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error during calculation") from exc


# ============================================================================
# Natural-language endpoint (LLM intent extraction)
# ============================================================================

@router.post(
    "/calculate_import_taxes/nl",
    tags=["Calculation"],
    response_model=NaturalLanguageResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation or extraction error"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def calculate_import_taxes_nl(
    request: NaturalLanguageRequest,
    db=Depends(get_db),
    fastapi_request: Request = None,
) -> NaturalLanguageResponse | PlainTextResponse:
    """
    Accept natural-language text, extract intent via LLM/regex, then calculate.

    If `output_format="text"`, returns a `PlainTextResponse` with the human-readable report.
    Otherwise returns a `NaturalLanguageResponse` JSON containing the full result,
    the extracted structured request, and metadata about the intent extraction.
    """
    try:
        # --- 1. Extract intent ---
        extractor = IntentExtractor(
            enabled=request.use_llm,
            timeout=10.0,
        )
        intent_result = await extractor.extract(request.text)

        if intent_result.source == "none":
            return NaturalLanguageResponse(
                success=False,
                error="Could not extract calculation parameters from the provided text.",
                source="none",
                confidence=0.0,
            )

        # --- 2. Build CalculateImportTaxesRequest ---
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Ensure description is present — LLM sometimes omits it or returns whitespace
        goods_dict = intent_result.goods or {}
        if not (goods_dict.get("description") or "").strip():
            hs = goods_dict.get("hs_code", "")
            if hs and str(hs).startswith("27"):
                goods_dict["description"] = "Petroleum products"
            elif hs and str(hs).startswith("40"):
                goods_dict["description"] = "Rubber products"
            else:
                goods_dict["description"] = "General merchandise"

        # Resolve HS code from description when user gave a commercial description
        # but no HS code. Uses Qdrant semantic search (one best match), then falls
        # back to CSV keyword search if Qdrant is unavailable.
        resolved_hs_from_description = None
        if not goods_dict.get("hs_code") and (goods_dict.get("description") or "").strip():
            desc = goods_dict["description"].strip()
            try:
                candidates = db.search_hs_by_description(desc, top_k=1)
                if candidates:
                    top = candidates[0]
                    resolved_hs = top.get("hs_code")
                    if resolved_hs:
                        goods_dict["hs_code"] = resolved_hs
                        resolved_hs_from_description = resolved_hs
                        # Enrich description with the official tariff description if available
                        qdrant_desc = top.get("description", "")
                        if qdrant_desc and qdrant_desc != desc:
                            goods_dict["description"] = qdrant_desc
                        logger.info(
                            f"Resolved HS code {resolved_hs} from description '{desc}' "
                            f"via Qdrant semantic search (score={top.get('score', 0):.3f})"
                        )
                if not goods_dict.get("hs_code"):
                    # Fallback to CSV keyword search
                    csv_result = db.search_by_description(desc)
                    if csv_result:
                        resolved_hs, confidence = csv_result
                        goods_dict["hs_code"] = resolved_hs
                        resolved_hs_from_description = resolved_hs
                        logger.info(
                            f"Resolved HS code {resolved_hs} from description '{desc}' "
                            f"via CSV keyword search (confidence={confidence:.3f})"
                        )
            except Exception as e:
                logger.warning(f"Could not resolve HS code from description '{desc}': {e}")

        structured_request = CalculateImportTaxesRequest(
            calculation_date=today,
            regime=intent_result.regime,
            goods=GoodsModel(**goods_dict),
            valuation=ValuationModel(**intent_result.valuation),
            flags=FlagsModel(**intent_result.flags) if intent_result.flags else None,
        )

        # --- 3. Run calculation (reuse existing logic) ---
        rules_provider = (
            getattr(fastapi_request.app.state, "rules_provider", None)
            if fastapi_request else None
        )
        formula_engine = (
            getattr(fastapi_request.app.state, "formula_engine", None)
            if fastapi_request else None
        )
        calculator = ImportTaxCalculator(db, rules_provider=rules_provider, formula_engine=formula_engine)

        calc_request, currency_assumption, cif_assumption, _ = _build_calc_request(structured_request, calculator)
        result = calculator.calculate(calc_request)
        result_dict = _enrich_result(result.to_dict(), calc_request, structured_request, calculator, currency_assumption, cif_assumption)

        # Add assumption when HS code was inferred from description (NL endpoint path)
        if resolved_hs_from_description:
            if "assumptions" not in result_dict or result_dict["assumptions"] is None:
                result_dict["assumptions"] = []
            result_dict["assumptions"].insert(
                0,
                f"⚠️  HS code {resolved_hs_from_description} was auto-resolved from the product description "
                f"'{structured_request.goods.description}' via semantic search. "
                f"This HS code may not be fully correct because you did not provide a clear description or an explicit HS code. "
                f"Please verify the HS code with customs or provide the exact HS code for an accurate calculation."
            )

        # Generate human-readable report
        llm_text = await _try_llm_human_readable(calc_request, result_dict, calculator)
        if llm_text:
            result_dict["human_readable"] = llm_text
        else:
            try:
                result_dict["human_readable"] = format_human_readable(calc_request, result_dict)
            except Exception as e:
                logger.debug(f"Programmatic human-readable formatting failed: {e}")

        calc_response = CalculateImportTaxesResponse(**result_dict)

        # --- 4. Return based on output_format ---
        if request.output_format == "text":
            text = calc_response.human_readable or ""
            if not text:
                import json
                text = json.dumps(result_dict, indent=2, default=str)
            return PlainTextResponse(content=text, media_type="text/plain; charset=utf-8")

        return NaturalLanguageResponse(
            success=True,
            result=calc_response,
            extracted_request=structured_request,
            intent={
                "case_type": intent_result.case_type,
                "confidence": intent_result.confidence,
                "reasoning": intent_result.reasoning,
            },
            source=intent_result.source,
            confidence=intent_result.confidence,
        )

    except ValueError as exc:
        logger.error(f"NL extraction/calculation validation error: {exc}")
        raise HTTPException(status_code=400, detail=f"Validation error: {exc}") from exc
    except KeyError as exc:
        logger.error(f"NL extraction missing field: {exc}")
        raise HTTPException(status_code=400, detail=f"Missing required field: {exc}") from exc
    except Exception as exc:
        logger.exception(f"NL extraction/calculation internal error: {exc}")
        raise HTTPException(status_code=500, detail="Internal server error during NL calculation") from exc


# ============================================================================
# Direct Query endpoint — ultra-simple interface
# ============================================================================

@router.post(
    "/query",
    tags=["Calculation"],
    response_model=DirectQueryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation or extraction error"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def direct_query(
    request: DirectQueryRequest,
    db=Depends(get_db),
    fastapi_request: Request = None,
) -> DirectQueryResponse:
    """
    Ask the calculator a natural-language question, get a human-readable answer.

    This is a thin wrapper over the NL pipeline that always returns
    a plain-English (or Khmer-English) report in `answer`.

    Example payload:
        {"question": "Calculate tax for HS 0102.29.11 CIF $800 from Thailand"}

    The response always contains:
        - answer   → human-readable report (or error message)
        - success  → true if calculation succeeded
        - source   → 'llm' or 'regex'
        - confidence → 0..1 extraction confidence
        - result   → full structured result (omitted on failure)
    """
    try:
        extractor = IntentExtractor(enabled=True, timeout=10.0)
        intent_result = await extractor.extract(request.question)

        if intent_result.source == "none":
            return DirectQueryResponse(
                success=False,
                answer="I couldn't understand your question. Please provide the HS code, CIF value, currency, and origin country.",
                error="Could not extract calculation parameters.",
                source="none",
                confidence=0.0,
            )

        today = datetime.utcnow().strftime("%Y-%m-%d")

        # Ensure description
        goods_dict = intent_result.goods or {}
        if not (goods_dict.get("description") or "").strip():
            hs = goods_dict.get("hs_code", "")
            if hs and str(hs).startswith("27"):
                goods_dict["description"] = "Petroleum products"
            elif hs and str(hs).startswith("40"):
                goods_dict["description"] = "Rubber products"
            else:
                goods_dict["description"] = "General merchandise"

        # Resolve HS from description if needed
        resolved_hs_from_description = None
        if not goods_dict.get("hs_code") and (goods_dict.get("description") or "").strip():
            desc = goods_dict["description"].strip()
            try:
                candidates = db.search_hs_by_description(desc, top_k=1)
                if candidates:
                    top = candidates[0]
                    resolved_hs = top.get("hs_code")
                    if resolved_hs:
                        goods_dict["hs_code"] = resolved_hs
                        resolved_hs_from_description = resolved_hs
                        qdrant_desc = top.get("description", "")
                        if qdrant_desc and qdrant_desc != desc:
                            goods_dict["description"] = qdrant_desc
                if not goods_dict.get("hs_code"):
                    csv_result = db.search_by_description(desc)
                    if csv_result:
                        resolved_hs, confidence = csv_result
                        goods_dict["hs_code"] = resolved_hs
                        resolved_hs_from_description = resolved_hs
            except Exception as e:
                logger.warning(f"Could not resolve HS code from description '{desc}': {e}")

        structured_request = CalculateImportTaxesRequest(
            calculation_date=today,
            regime=intent_result.regime,
            goods=GoodsModel(**goods_dict),
            valuation=ValuationModel(**intent_result.valuation),
            flags=FlagsModel(**intent_result.flags) if intent_result.flags else None,
        )

        rules_provider = (
            getattr(fastapi_request.app.state, "rules_provider", None)
            if fastapi_request else None
        )
        formula_engine = (
            getattr(fastapi_request.app.state, "formula_engine", None)
            if fastapi_request else None
        )
        calculator = ImportTaxCalculator(
            db, rules_provider=rules_provider, formula_engine=formula_engine
        )

        calc_request, currency_assumption, cif_assumption, _ = _build_calc_request(
            structured_request, calculator
        )
        result = calculator.calculate(calc_request)
        result_dict = _enrich_result(
            result.to_dict(), calc_request, structured_request, calculator,
            currency_assumption, cif_assumption
        )

        if resolved_hs_from_description:
            if "assumptions" not in result_dict or result_dict["assumptions"] is None:
                result_dict["assumptions"] = []
            result_dict["assumptions"].insert(
                0,
                f"⚠️  HS code {resolved_hs_from_description} was auto-resolved from the product description "
                f"'{structured_request.goods.description}' via semantic search. "
                f"Please verify the HS code with customs or provide the exact HS code for an accurate calculation."
            )

        llm_text = await _try_llm_human_readable(calc_request, result_dict, calculator)
        if llm_text:
            result_dict["human_readable"] = llm_text
        else:
            try:
                result_dict["human_readable"] = format_human_readable(calc_request, result_dict)
            except Exception as e:
                logger.debug(f"Programmatic human-readable formatting failed: {e}")

        calc_response = CalculateImportTaxesResponse(**result_dict)

        return DirectQueryResponse(
            success=True,
            answer=calc_response.human_readable or "Calculation completed but no report was generated.",
            source=intent_result.source,
            confidence=intent_result.confidence,
            result=calc_response,
            extracted_request=structured_request,
        )

    except ValueError as exc:
        logger.error(f"Direct query validation error: {exc}")
        return DirectQueryResponse(
            success=False,
            answer=f"Validation error: {exc}",
            error=str(exc),
            source="none",
            confidence=0.0,
        )
    except Exception as exc:
        logger.exception(f"Direct query internal error: {exc}")
        return DirectQueryResponse(
            success=False,
            answer="An internal error occurred while processing your question.",
            error=str(exc),
            source="none",
            confidence=0.0,
        )


# ============================================================================
# Rich LLM prompt builder + human-readable generator
# ============================================================================

def _build_llm_prompt(calc_request: CalculationRequest, result_dict: Dict[str, Any]) -> str:
    """Build a rich prompt for the LLM with exact step-by-step values."""
    bd = result_dict.get("breakdown", {})
    li = result_dict.get("line_items", [])
    exchange_rate = float(result_dict.get("exchange_rate_usd_to_khr", 4022) or 4022)
    total = float(result_dict.get("total", 0) or 0)
    cif_usd = float(result_dict.get("cif_value_usd", 0) or 0)
    cif_khr = float(bd.get("cif_value", 0) or 0)

    hs_code = calc_request.hs_code or "N/A"
    origin = calc_request.origin_country or "Unknown"
    description = calc_request.goods.get("description", "N/A")
    regime = calc_request.regime or "import"
    is_petroleum = (calc_request.flags or {}).get("petroleum_case", False)
    is_rubber = (calc_request.flags or {}).get("rubber_case", False)
    is_fta = (calc_request.flags or {}).get("fta_applicable", False)
    is_export = str(regime).lower() == "export"
    calc_date = calc_request.calculation_date or "N/A"

    def _find_item(name_substring: str) -> Dict[str, Any]:
        for item in li:
            if name_substring.lower() in str(item.get("name", "")).lower():
                return item
        return {}

    def _fmt(n) -> str:
        try:
            return f"{float(n):,.2f}"
        except Exception:
            return str(n)

    def _fmt_whole(n) -> str:
        try:
            return f"{int(float(n)):,}"
        except Exception:
            return str(n)

    case_label = "Normal import"
    if is_petroleum:
        case_label = "Petroleum (two-phase)"
    elif is_rubber and is_export:
        case_label = "Rubber export"
    elif is_fta:
        case_label = "Preferential (FTA)"
    elif is_export:
        case_label = "Export"

    lines = [
        "You are a Cambodian customs expert. Format the following import tax calculation into a clean, professional, human-readable report.",
        "",
        "Formatting rules:",
        "- Use dashed-line separators (like -----).",
        "- Show step-by-step calculations with exact formulas and numbers.",
        "- Use comma-separated thousands (e.g., 1,234,567).",
        "- Do NOT use markdown code blocks.",
        "- Do NOT abbreviate tax terms on first mention.",
        "- Display the ATP rate explicitly as $/L (e.g., 0.02 $/L).",
        "",
        "=== RAW DATA ===",
        f"HS Code: {hs_code}",
        f"Product: {description}",
        f"Origin: {origin}",
        f"CIF Value: {_fmt(cif_usd)} USD",
        f"Exchange Rate: 1 USD = {_fmt(exchange_rate)} KHR",
        f"CIF in KHR: {_fmt_whole(cif_khr)} KHR",
        f"Calculation Date: {calc_date}",
        f"Regime: {case_label}",
        "",
    ]

    if is_petroleum:
        cpp_base_p1 = float(bd.get("cpp_base", 0) or 0)
        cpp_p1 = float(bd.get("cpp_amount", 0) or 0)
        atp = float(bd.get("atp_amount", 0) or 0)
        spp_p1 = float(bd.get("spp_amount", 0) or 0)
        vpp_p1 = float(bd.get("vpp_amount", 0) or 0)
        dpp = float(bd.get("dpp_amount", 0) or 0)
        p2_cpp = float(bd.get("phase2_cpp_amount", 0) or 0)
        p2_atp = float(bd.get("phase2_atp_amount", 0) or 0)
        p2_spp = float(bd.get("phase2_spp_amount", 0) or 0)
        p2_vpp = float(bd.get("phase2_vpp_amount", 0) or 0)
        p2_total = float(bd.get("phase2_total", 0) or 0)
        vol = float(calc_request.volume_liter or 0)
        net_mass = float(calc_request.net_mass_kg_normalized or 0)
        dv = float(calc_request.declared_value or 0)

        # Extract exact rates from line items
        cpp_item = _find_item("CPP")
        atp_item = _find_item("ATP")
        spp_item = _find_item("SPP")
        vpp_item = _find_item("VPP")
        cd_rate = float(cpp_item.get("rate", 0) or 0)
        atp_rate_khr = float(atp_item.get("rate", 0) or 0)
        atp_rate_usd = atp_rate_khr / exchange_rate if exchange_rate else 0
        st_rate = float(spp_item.get("rate", 0) or 0)
        vat_rate = float(vpp_item.get("rate", 0) or 0)

        lines.extend([
            "=== PETROLEUM TWO-PHASE CALCULATION ===",
            "",
            "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
            f"Formula: CIF Value (USD) x Exchange Rate",
            f"= {_fmt(cif_usd)} x {_fmt(exchange_rate)}",
            f"= {_fmt_whole(cif_khr)} KHR",
            "",
            "STEP 2: PHASE 1 -- PETROLEUM TAX (Declared Value Basis)",
            f"DV = {dv} USD per metric ton",
            f"Net mass = {net_mass} kg",
            f"CPP base = DV/ton x exchange_rate x net_mass_kg / 1000 = {_fmt_whole(cpp_base_p1)} KHR",
            f"CPP = CPP base x CD rate ({cd_rate}%) = {_fmt_whole(cpp_p1)} KHR",
            f"ATP = volume_liter x {atp_rate_usd:.2f} $/L x exchange_rate = {_fmt_whole(atp)} KHR",
            f"SPP = (CPP base + CPP + ATP) x ST rate ({st_rate}%) = {_fmt_whole(spp_p1)} KHR",
            f"VPP = (CPP base + CPP + ATP + SPP) x VAT rate ({vat_rate}%) = {_fmt_whole(vpp_p1)} KHR",
            f"Phase 1 Total = {_fmt_whole(cpp_p1 + atp + spp_p1 + vpp_p1)} KHR",
            "",
            "STEP 3: PHASE 2 -- PETROLEUM TAX (Customs Value / CIF Basis)",
            f"CPP base = CIF value = {_fmt_whole(cif_khr)} KHR",
            f"CPP = CPP base x CD rate ({cd_rate}%) = {_fmt_whole(p2_cpp)} KHR",
            f"ATP = same as Phase 1 = {_fmt_whole(p2_atp)} KHR",
            f"SPP = (CPP base + CPP + ATP) x ST rate ({st_rate}%) = {_fmt_whole(p2_spp)} KHR",
            f"VPP = (CPP base + CPP + ATP + SPP) x VAT rate ({vat_rate}%) = {_fmt_whole(p2_vpp)} KHR",
            f"Phase 2 Total = {_fmt_whole(p2_total)} KHR",
            "",
            "STEP 4: DIFFERENCE / PARTIAL SUBSIDY (DPP)",
            f"DPP = Phase 1 Total - Phase 2 Total",
            f"= {_fmt_whole(cpp_p1 + atp + spp_p1 + vpp_p1)} - {_fmt_whole(p2_total)}",
            f"= {_fmt_whole(dpp)} KHR",
            "",
        ])
    elif is_rubber and is_export:
        etr = float(bd.get("etr_amount", 0) or 0)
        net_mass = float(calc_request.net_mass_kg_normalized or 0)
        et_item = _find_item("ETR")
        et_rate = float(et_item.get("rate", 0) or 0)
        lines.extend([
            "=== RUBBER EXPORT CALCULATION ===",
            "",
            "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
            f"= {_fmt_whole(cif_khr)} KHR",
            "",
            "STEP 2: EXPORT TAX ON RUBBER (ETR)",
            f"ETR = (CIF_KHR / net_mass_kg) x ET rate ({et_rate}%)",
            f"= {_fmt_whole(etr)} KHR",
            "",
        ])
    else:
        cop = float(bd.get("cop_amount", 0) or 0)
        sop = float(bd.get("sop_amount", 0) or 0)
        vop = float(bd.get("vop_amount", 0) or 0)
        vvf = float(bd.get("vvf_amount", 0) or 0)

        cd_item = _find_item("COP")
        st_item = _find_item("SOP")
        vat_item = _find_item("VOP")
        cd_rate = float(cd_item.get("rate", 0) or 0)
        st_rate = float(st_item.get("rate", 0) or 0)
        vat_rate = float(vat_item.get("rate", 0) or 0)

        lines.extend([
            "=== NORMAL IMPORT CALCULATION ===",
            "",
            "STEP 1: CURRENCY CONVERSION (USD -> KHR)",
            f"= {_fmt_whole(cif_khr)} KHR",
            "",
            "STEP 2: IMPORT TAXES (COP)",
            f"Formula: CIF Value x CD rate ({cd_rate}%)",
            f"= {_fmt_whole(cop)} KHR",
            "",
            "STEP 3: SPECIAL TARIFF (SOP)",
            f"Formula: (CIF Value + COP) x ST rate ({st_rate}%)",
            f"= {_fmt_whole(sop)} KHR",
            "",
            "STEP 4: VALUE ADDED TAX (VOP)",
        ])
        if sop == 0:
            lines.append(f"Formula: (CIF Value + COP) x VAT rate ({vat_rate}%)")
            lines.append(f"= {_fmt_whole(cif_khr + cop)} x {vat_rate}%")
        else:
            lines.append(f"Formula: (CIF Value + COP + SOP) x VAT rate ({vat_rate}%)")
            lines.append(f"= {_fmt_whole(cif_khr + cop + sop)} x {vat_rate}%")
        lines.append(f"= {_fmt_whole(vop)} KHR")
        lines.append("")
        if vvf > 0:
            lines.extend([
                "STEP 5: VEHICLE VALUATION FEE (VVF)",
                f"Fee = 60,000 KHR per vehicle unit",
                f"= {_fmt_whole(vvf)} KHR",
                "",
            ])
        if is_fta:
            lines.append("NOTE: FTA preferential rates applied where available.")
            lines.append("")

    # Breakdown table
    lines.extend([
        "=== FINAL TAX BREAKDOWN TABLE ===",
        "| Tax Component | Tax base (KHR) | Rate | Amount (KHR) |",
    ])
    for item in li:
        name = str(item.get("name", ""))[:38]
        base = _fmt_whole(item.get("base", 0))
        rate = item.get("rate")
        amount = _fmt_whole(item.get("amount", 0))
        tax_type = item.get("tax_type", "")

        # ATP: rate is per-liter in KHR; show as USD/L
        if tax_type == "ATP" and rate is not None and exchange_rate:
            try:
                rate_usd = float(rate) / float(exchange_rate)
                rate_str = f"{rate_usd:.2f} $/L"
            except Exception:
                rate_str = str(rate)
        elif rate is not None:
            try:
                rate_str = f"{float(rate):.2f}"
            except Exception:
                rate_str = str(rate)
        else:
            rate_str = "0.00"
        lines.append(f"| {name} | {base} | {rate_str} | {amount} |")
    lines.append(f"| TOTAL | | | {_fmt_whole(total)} |")
    lines.append("")

    # Summary
    lines.extend([
        "=== SUMMARY ===",
        f"To import {description} ({hs_code}) valued at {_fmt(cif_usd)} USD CIF from {origin},",
        f"you must pay {_fmt_whole(total)} KHR in import taxes.",
    ])

    return "\n".join(lines)


async def _try_llm_human_readable(
    calc_request: CalculationRequest,
    result_dict: Dict[str, Any],
    calculator: ImportTaxCalculator,
) -> str | None:
    """
    Try to generate human-readable text via LLM. Returns None if unavailable.
    """
    try:
        from ..core.llm_formatter import LLMFormatter

        formatter = LLMFormatter()
        if not formatter.is_available():
            return None

        prompt = _build_llm_prompt(calc_request, result_dict)
        text = await formatter.generate(prompt)
        return text.strip() if text else None
    except Exception as e:
        logger.warning(f"LLM human-readable generation failed: {e}")
        return None
