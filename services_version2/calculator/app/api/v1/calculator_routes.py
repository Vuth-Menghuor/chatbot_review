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

from fastapi import APIRouter, Depends, HTTPException, Request

from ..deps import get_db
from ...data.redis_exchange_rate_client import RedisExchangeRateClient
from ...schemas.calculator_schema import (
    CalculateImportTaxesRequest,
    CalculateImportTaxesResponse,
    DirectQueryRequest,
    DirectQueryResponse,
    FlagsModel,
    GoodsModel,
    HSCodeInfoModel,
    ValuationModel,
    ErrorResponse,
)
from ...services.calculator import CalculationRequest, ImportTaxCalculator
from ...ai.intent_extractor import IntentExtractor
from ...ai.llm_formatter import format_human_readable
from ...services.ask_back_policy import ConflictDetector

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Health Check endpoint
# ============================================================================

@router.get(
    "/health",
    tags=["Health"],
    response_model=dict,
    summary="Service health check",
)
async def health_check(db=Depends(get_db)) -> dict:
    """
    Returns service health status including Redis and PostgreSQL connectivity.
    """
    import os
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    status = "ok"
    details: dict[str, Any] = {}

    # --- Redis check ---
    redis_info: dict[str, Any] = {"connected": False}
    try:
        redis_client = RedisExchangeRateClient()
        redis_health = redis_client.check_health()
        redis_info["connected"] = redis_health.get("ok", False)
        redis_info["last_updated"] = redis_health.get("last_updated")
        redis_info["server"] = redis_health.get("server")

        # Determine if rates are fresh (within last 24h)
        if redis_health.get("last_updated"):
            try:
                lu = datetime.fromisoformat(redis_health["last_updated"])
                if lu.tzinfo is None:
                    lu = lu.replace(tzinfo=timezone.utc)
                age_hours = (now - lu).total_seconds() / 3600
                redis_info["rates_fresh"] = age_hours < 24
                redis_info["age_hours"] = round(age_hours, 2)
            except Exception:
                redis_info["rates_fresh"] = False
        else:
            redis_info["rates_fresh"] = False
    except Exception as e:
        redis_info["error"] = str(e)
        status = "degraded"

    details["redis"] = redis_info

    # --- PostgreSQL check ---
    pg_info: dict[str, Any] = {"connected": False}
    try:
        unified_health = db.check_health()
        pg_health = unified_health.get("calculator_db", {})
        pg_info["connected"] = pg_health.get("ok", False)
        pg_info["server"] = pg_health.get("server")
        pg_info["database"] = pg_health.get("database")
        pg_info["record_count"] = pg_health.get("record_count")
        pg_info["message"] = pg_health.get("message")
    except Exception as e:
        pg_info["error"] = str(e)
        status = "degraded"

    details["postgres"] = pg_info

    # --- Overall ---
    if not redis_info.get("connected") or not pg_info.get("connected"):
        status = "degraded" if (redis_info.get("connected") or pg_info.get("connected")) else "down"

    return {
        "status": status,
        "timestamp": now.isoformat(),
        "service": "gdce-calculator",
        "version": "2.0.0",
        "details": details,
    }


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
        origin = request.goods.origin_country.strip() if request.goods.origin_country else None
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

    # --- HS code prefix + description resolution ---
    # If user provided a bare prefix (e.g. "7204") with a description,
    # attempt to resolve a full 8-digit HS code.
    hs = goods_dict.get("hs_code")
    desc = goods_dict.get("description", "").strip()
    prefix_failed = False
    if hs and calculator.hs_code_handler.is_prefix_code(hs) and desc:
        if desc not in ("General merchandise", "Petroleum products", "Rubber products"):
            resolved_hs, resolved_source, candidates = calculator.resolve_hs_from_prefix_and_description(
                hs, desc
            )
            if resolved_hs:
                # Check for chapter mismatch between original prefix and resolved code
                orig_ch = calculator._extract_chapter(hs)
                resolved_ch = calculator._extract_chapter(resolved_hs)
                if orig_ch and resolved_ch and orig_ch != resolved_ch:
                    resolved_desc = ""
                    if candidates and candidates[0].get("description"):
                        resolved_desc = f" ({candidates[0]['description']})"
                    raise ValueError(
                        f"There seems to be a mismatch in your request.\n\n"
                        f"You mentioned HS code {hs}, but your description "
                        f"'{desc}' matches HS {resolved_hs}{resolved_desc}, which is a "
                        f"different product category.\n\n"
                        f"Please rewrite your request with either:\n"
                        f"  1) the correct product description, or\n"
                        f"  2) the correct HS code."
                    )
                goods_dict["hs_code"] = resolved_hs
                hs_assumption = (
                    f"⚠️  HS code {resolved_hs} was resolved from prefix {hs} combined with "
                    f"description '{desc}' via {resolved_source} search. "
                    f"Please verify this HS code with customs or provide the exact 8-digit HS code for an accurate calculation."
                )
                logger.info(f" JSON endpoint resolved HS {resolved_hs} from prefix {hs} + description")
            else:
                # Prefix did not match — clear it and let calculator core handle description fallback
                goods_dict.pop("hs_code", None)
                prefix_failed = True
                hs_assumption = (
                    f"⚠️  HS prefix {hs} did not match any known HS codes in our database. "
                    f"The calculation will use the description '{desc}' instead. "
                    f"Please verify the HS prefix or provide the exact 8-digit HS code for an accurate calculation."
                )
                logger.warning(f" JSON endpoint: prefix {hs} did not match any codes, falling back to description")

    # --- HS code resolution from commercial description (JSON/text endpoints) ---
    # If no HS code was provided but a product description was, attempt to resolve.
    # Skip this when a prefix already failed — the calculator core handles it.
    if not prefix_failed and not goods_dict.get("hs_code") and desc:
        if desc not in ("General merchandise", "Petroleum products", "Rubber products"):
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

        # JSON endpoint returns pure structured data; presentation is handled by the consumer
        result_dict.pop("human_readable", None)

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

        # ------------------------------------------------------------------
        # Build calculator early — needed for conflict detection & resolution
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # ASK-BACK: description vs HS code conflict detection
        # If the user gave both a description and an explicit HS code that
        # resolve to different chapters, ask them to rewrite the question.
        # ------------------------------------------------------------------
        detector = ConflictDetector(calculator)
        conflict = detector.check(intent_result)
        if conflict:
            return DirectQueryResponse(
                success=False,
                needs_clarification=True,
                answer=conflict.message,
                source="conflict_detector",
                confidence=0.0,
            )

        # Resolve HS from prefix + description if user provided a bare prefix
        resolved_hs_from_prefix = None
        hs = goods_dict.get("hs_code")
        desc = (goods_dict.get("description") or "").strip()
        if hs and desc and len(hs.replace(".", "")) == 4:
            try:
                candidates = db.search_hs_by_prefix_and_description(hs, desc, top_k=1)
                if candidates:
                    top = candidates[0]
                    resolved_hs = top.get("hs_code")
                    if resolved_hs:
                        goods_dict["hs_code"] = resolved_hs
                        resolved_hs_from_prefix = resolved_hs
            except Exception as e:
                logger.warning(f"Could not resolve HS from prefix {hs} + description '{desc}': {e}")

        # Resolve HS from description if needed (no HS code at all)
        resolved_hs_from_description = None
        if not goods_dict.get("hs_code") and desc:
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
                    db_result = db.search_by_description(desc)
                    if db_result:
                        resolved_hs, confidence = db_result
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

        calc_request, currency_assumption, cif_assumption, _ = _build_calc_request(
            structured_request, calculator
        )
        result = calculator.calculate(calc_request)
        result_dict = _enrich_result(
            result.to_dict(), calc_request, structured_request, calculator,
            currency_assumption, cif_assumption
        )

        if resolved_hs_from_prefix:
            if "assumptions" not in result_dict or result_dict["assumptions"] is None:
                result_dict["assumptions"] = []
            result_dict["assumptions"].insert(
                0,
                f"⚠️  HS code {resolved_hs_from_prefix} was resolved from prefix {hs} combined with "
                f"description '{structured_request.goods.description}' via semantic search. "
                f"Please verify this HS code with customs or provide the exact 8-digit HS code for an accurate calculation."
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

        # Generate human-readable report for the chat/query endpoint
        human_readable = None
        try:
            human_readable = format_human_readable(calc_request, result_dict)
        except Exception as e:
            logger.debug(f"Human-readable formatting failed: {e}")

        # Remove presentation fields from the structured result so the schema stays clean
        result_dict.pop("human_readable", None)
        calc_response = CalculateImportTaxesResponse(**result_dict)

        return DirectQueryResponse(
            success=True,
            answer=human_readable or "Calculation completed but no report was generated.",
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


