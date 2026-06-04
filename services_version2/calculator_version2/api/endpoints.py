"""
GDCE Calculator Service - API Endpoints
=======================================
HTTP layer for calculator microservice. Uses FastAPI, depends on core
business logic (ImportTaxCalculator) and CSV-backed infrastructure.

Integrated with:
- CurrencyHandler: For flexible currency input/output
- HSCodeHandler: For HS code lookup and candidates
- LLMFormatter: For user-friendly response formatting
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from .deps import get_db
from .schemas import (
    CalculateImportTaxesRequest,
    CalculateImportTaxesResponse,
    HSCodeInfoModel,
    ErrorResponse,
    QueryRequest,
    GoodsModel,
    ValuationModel,
    FlagsModel,
)
from ..core.calculator import CalculationRequest, ImportTaxCalculator
from ..core.models import TaxReference
from ..infrastructure.retrieval_client import RetrievalClient
from ..core.parser import parse_question_for_calculation

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
            "query": "/query",
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
    product_description: str,
    db=Depends(get_db),
) -> Dict[str, Any]:
    result = db.search_by_description(product_description)
    if not result:
        return {
            "found": False,
            "product_description": product_description,
            "message": "Could not determine HS code for this product.",
        }

    hs_code, confidence = result
    rates = db.get_duty_rates(hs_code=hs_code, origin_country="XX", effective_date=datetime.utcnow().strftime("%Y-%m-%d"))
    return {
        "found": True,
        "product_description": product_description,
        "hs_code": hs_code,
        "confidence": confidence,
        "duty_rates": rates,
        "source": "csv_description_search",
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


async def calculate_import_taxes(
    request: CalculateImportTaxesRequest,
    format_with_llm: bool = False,
    db=Depends(get_db),
    fastapi_request: Request = None,
) -> CalculateImportTaxesResponse:
    """
    Main calculation endpoint.
    
    Args:
        request: Calculation request with goods, valuation, and flags
        format_with_llm: If true, uses LLM to format calculation steps (experimental)
        db: Database connection dependency
        
    Returns:
        CalculateImportTaxesResponse with calculation results and optional LLM formatting
    """
    try:
        # Wire up dynamic rules engine from app state (initialized in app.py)
        rules_provider = (
            getattr(fastapi_request.app.state, "rules_provider", None)
            if fastapi_request else None
        )
        formula_engine = (
            getattr(fastapi_request.app.state, "formula_engine", None)
            if fastapi_request else None
        )
        calculator = ImportTaxCalculator(
            db,
            rules_provider=rules_provider,
            formula_engine=formula_engine,
        )

        # =====================================================================
        # CURRENCY FALLBACK CHAIN
        # =====================================================================
        # Priority: explicit currency → origin country inference → KHR default
        resolved_currency = request.valuation.currency  # Already normalized by schema validator
        currency_assumption = None

        if not resolved_currency:
            # Try to infer from origin country
            origin = request.goods.origin_country
            if origin:
                inferred = calculator.currency_handler.infer_currency_from_country(origin)
                if inferred:
                    resolved_currency = inferred
                    currency_assumption = (
                        f"Currency not specified — inferred as {inferred} "
                        f"from origin country '{origin}'"
                    )
                    logger.info(f"💱 {currency_assumption}")

            # Final fallback: KHR
            if not resolved_currency:
                resolved_currency = "KHR"
                currency_assumption = (
                    "Currency not specified and no origin country provided — "
                    "defaulting to KHR (Cambodian Riel)"
                )
                logger.info(f"💱 {currency_assumption}")

        # Build valuation/goods dicts with resolved values
        valuation_dict = request.valuation.dict(exclude_none=True)
        valuation_dict["currency"] = resolved_currency

        goods_dict = request.goods.dict(exclude_none=True)
        hs_code_assumption = None

        if not goods_dict.get("hs_code") and goods_dict.get("description"):
            try:
                retrieval_client = RetrievalClient()
                resolved_hs = await retrieval_client.lookup_hs_code(goods_dict["description"])
                if resolved_hs:
                    goods_dict["hs_code"] = resolved_hs
                    hs_code_assumption = (
                        f"HS code not specified — resolved as {resolved_hs} "
                        f"via retrieval from product description '{goods_dict['description']}'"
                    )
                    logger.info(f"🔍 {hs_code_assumption}")
                else:
                    # Try local DB search fallback
                    local_match = db.search_by_description(goods_dict["description"])
                    if local_match:
                        local_hs = local_match[0]
                        goods_dict["hs_code"] = local_hs
                        hs_code_assumption = (
                            f"HS code not specified — resolved as {local_hs} "
                            f"via local search from product description '{goods_dict['description']}'"
                        )
                        logger.info(f"🔍 {hs_code_assumption}")
            except Exception as e:
                logger.warning(f"Error during HS code lookup from product description: {e}")
                try:
                    local_match = db.search_by_description(goods_dict["description"])
                    if local_match:
                        local_hs = local_match[0]
                        goods_dict["hs_code"] = local_hs
                        hs_code_assumption = (
                            f"HS code not specified — resolved as {local_hs} "
                            f"via local search fallback from product description '{goods_dict['description']}'"
                        )
                        logger.info(f"🔍 {hs_code_assumption}")
                except Exception as inner_e:
                    logger.warning(f"Local fallback search failed: {inner_e}")

        calc_request = CalculationRequest(
            calculation_date=request.calculation_date,
            regime=request.regime,
            goods=goods_dict,
            valuation=valuation_dict,
            flags=request.flags.dict(exclude_none=True) if request.flags else {},
            requested_breakdown=request.requested_breakdown,
        )

        # Normalize HS code in the request if provided
        if calc_request.hs_code:
            try:
                normalized_hs = calculator.hs_code_handler.normalize_code(calc_request.hs_code)
                calc_request.goods['hs_code'] = normalized_hs
                logger.debug(f"HS code normalized: {calc_request.hs_code} → {normalized_hs}")
            except Exception as e:
                logger.warning(f"Failed to normalize HS code '{calc_request.hs_code}': {e}")
        
        result = calculator.calculate(calc_request)
        
        # Convert to response dict
        result_dict = result.to_dict()

        # Add assumptions if applicable
        if "assumptions" in result_dict and isinstance(result_dict["assumptions"], list):
            if hs_code_assumption:
                result_dict["assumptions"].insert(0, hs_code_assumption)
            if currency_assumption:
                result_dict["assumptions"].insert(0, currency_assumption)
        
        # Populate new fields: currency_note and hs_code_info
        # Currency note — only when input currency differs from output
        input_currency = resolved_currency
        output_currency = result_dict.get("currency", "KHR")
        if input_currency and input_currency != output_currency:
            result_dict["currency_note"] = calculator.currency_handler.get_currency_note(
                input_currency,
                output_currency,
                exchange_rate=result_dict.get("exchange_rate_usd_to_khr"),
                calculation_date=request.calculation_date
            )
        
        # HS code info - use normalized code from calc_request
        hs_code_to_lookup = calc_request.hs_code
        if hs_code_to_lookup:
            try:
                hs_code_info = calculator.hs_code_handler.get_code_info(hs_code_to_lookup)
                if hs_code_info:
                    result_dict["hs_code_info"] = HSCodeInfoModel(
                        hs_code=hs_code_info["hs_code"],
                        description=hs_code_info.get("description"),
                        unit=hs_code_info.get("unit"),
                        level=calculator.hs_code_handler.get_child_level(hs_code_to_lookup)
                    ).dict(exclude_none=True)
            except Exception as e:
                # Log but don't fail if HS info lookup fails
                logger.debug(f"Failed to get HS code info for '{hs_code_to_lookup}': {e}")
        
        # Try to format with LLM if requested
        if format_with_llm:
            try:
                result_dict = await _format_calculation_with_llm(
                    result_dict,
                    request,
                    calculator
                )
            except Exception as e:
                logger.warning(f"LLM formatting failed, using default format: {e}")
                # Continue with unformatted response on LLM error
        
        return CalculateImportTaxesResponse(**result_dict)

    except ValueError as exc:  # validation errors from core
        error_msg = f"Validation error: {str(exc)}"
        logger.error(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg) from exc
    except KeyError as exc:  # missing required fields
        error_msg = f"Missing required field: {str(exc)}"
        logger.error(f"❌ {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg) from exc
    except Exception as exc:  # catch-all
        error_msg = f"Internal server error: {str(exc)}"
        logger.exception(f"❌ {error_msg}")
        raise HTTPException(status_code=500, detail="Internal server error during calculation") from exc


async def _format_calculation_with_llm(
    result_dict: Dict[str, Any],
    request: CalculateImportTaxesRequest,
    calculator: ImportTaxCalculator
) -> Dict[str, Any]:
    """
    Format calculation response using LLM for educational step-by-step breakdown.
    
    Integrates with existing LLM formatter in orchestrator.
    """
    try:
        # Try to import LLM formatter from orchestrator
        try:
            from ...orchestrator.core.llm_formatter import (
                LLMFormatter, FormatterIntent, HSCodeInfo
            )
        except ImportError:
            # Fallback: try importing from relative orchestrator path
            try:
                import sys
                from pathlib import Path
                orchestrator_path = Path(__file__).parent.parent.parent / "orchestrator"
                if orchestrator_path.exists():
                    sys.path.insert(0, str(orchestrator_path.parent))
                    from orchestrator.core.llm_formatter import (
                        LLMFormatter, FormatterIntent, HSCodeInfo
                    )
                else:
                    raise ImportError("Orchestrator path not found")
            except Exception as e:
                logger.debug(f"LLM formatter not available: {e}")
                return result_dict
        
        formatter = LLMFormatter()
        
        # Prepare context for LLM
        context = {
            'exchange_rate': result_dict.get('exchange_rate_usd_to_khr', 4022),
            'cif_value': request.valuation.customs_value,
            'cif_currency': request.valuation.currency,
            'origin_country': request.goods.origin_country or 'Unknown',
            'rates': {
                # Try to extract rates from assumptions
                'cd_rate': 0,
                'st_rate': 0,
                'vat_rate': 0.10,
                'et_rate': 0
            }
        }
        
        # Add HS code info if available
        if request.goods.hs_code:
            try:
                hs_info = calculator.hs_code_handler.get_code_info(request.goods.hs_code)
                if hs_info:
                    context['hs_code_info'] = HSCodeInfo(
                        hs_code=hs_info['hs_code'],
                        description=hs_info.get('description', ''),
                        category=''
                    )
            except Exception as e:
                logger.debug(f"Failed to get HS code info for LLM context: {e}")
        
        # Format breakdown
        breakdown_text = f"Total: {result_dict.get('total')} KHR. Breakdown: " \
                        f"CD={result_dict.get('breakdown', {}).get('cop_amount', 0)}, " \
                        f"ST={result_dict.get('breakdown', {}).get('sop_amount', 0)}, " \
                        f"VAT={result_dict.get('breakdown', {}).get('vop_amount', 0)}, " \
                        f"BUR={result_dict.get('breakdown', {}).get('bur_amount', 0)}, " \
                        f"VVF={result_dict.get('breakdown', {}).get('vvf_amount', result_dict.get('breakdown', {}).get('fees', 0))}, " \
                        f"ET={result_dict.get('breakdown', {}).get('fees', 0)}"
        
        original_question = f"Calculate {request.regime} customs tax for HS {request.goods.hs_code} " \
                           f"value {request.valuation.customs_value} {request.valuation.currency} " \
                           f"from {request.goods.origin_country or 'Unknown'}"
        
        # Call LLM formatter (may be sync or async)
        try:
            formatted_text = await formatter.format_response(
                response_text=breakdown_text,
                intent=FormatterIntent.CALCULATION,
                original_question=original_question,
                context=context
            )
            
            # Add LLM formatted breakdown to assumptions
            if formatted_text and formatted_text != breakdown_text:
                result_dict['assumptions'].insert(0, "=== LLM-FORMATTED BREAKDOWN ===")
                result_dict['assumptions'].insert(1, formatted_text)
                logger.info(f"✅ Calculation formatted with LLM")
        except Exception as e:
            logger.debug(f"LLM formatting async call failed: {e}")
            # Try sync fallback if available
            if hasattr(formatter, 'format_response_sync'):
                try:
                    formatted_text = formatter.format_response_sync(
                        response_text=breakdown_text,
                        intent=FormatterIntent.CALCULATION,
                        original_question=original_question,
                        context=context
                    )
                    if formatted_text and formatted_text != breakdown_text:
                        result_dict['assumptions'].insert(0, "=== LLM-FORMATTED BREAKDOWN ===")
                        result_dict['assumptions'].insert(1, formatted_text)
                        logger.info(f"✅ Calculation formatted with LLM (sync)")
                except Exception as e2:
                    logger.debug(f"LLM sync formatting also failed: {e2}")
        
        return result_dict
        
    except Exception as e:
        logger.warning(f"⚠️  Error in LLM formatting: {e}. Continuing with unformatted response.")
        return result_dict


@router.post(
    "/query",
    tags=["Calculation"],
    response_model=CalculateImportTaxesResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
async def query_import_taxes(
    query_request: QueryRequest,
    format_with_llm: bool = False,
    db=Depends(get_db),
    fastapi_request: Request = None,
) -> CalculateImportTaxesResponse:
    """
    Calculate import taxes from a natural language question.
    """
    try:
        question = query_request.question.strip() if query_request.question else None
        parsed_params = {}
        if question:
            parsed_params = parse_question_for_calculation(question)

        # Merge direct attributes from query_request if they are not None
        direct_overrides = {
            "hs_code": query_request.hs_code,
            "cif_value": query_request.cif_value,
            "currency": query_request.currency,
            "origin_country": query_request.origin_country,
            "quantity": query_request.quantity,
            "unit": query_request.unit,
            "fta_applicable": query_request.fta_applicable,
            "fta_certificate_type": query_request.fta_certificate_type,
            "preferential_cd_rate": query_request.preferential_cd_rate,
            "dq_applicable": query_request.dq_applicable,
            "dq_factor": query_request.dq_factor,
            "petroleum_case": query_request.petroleum_case,
            "rubber_case": query_request.rubber_case,
            "regime": query_request.regime,
            "calculation_date": query_request.calculation_date,
            "declared_value": query_request.declared_value,
            "net_mass": query_request.net_mass,
            "volume": query_request.volume,
            "exchange_rate_to_khr": query_request.exchange_rate_to_khr,
            "qip_exemption": query_request.qip_exemption,
            "sez_applicable": query_request.sez_applicable,
            "diplomatic_exemption": query_request.diplomatic_exemption,
            "ngo_humanitarian": query_request.ngo_humanitarian,
            "educational_exemption": query_request.educational_exemption,
            "medical_exemption": query_request.medical_exemption,
            "passenger_allowance": query_request.passenger_allowance,
        }
        for k, v in direct_overrides.items():
            if v is not None:
                parsed_params[k] = v

        # Override with extracted_params if explicitly provided
        if query_request.extracted_params:
            for k, v in query_request.extracted_params.items():
                if v is not None:
                    parsed_params[k] = v

        # Build the CalculateImportTaxesRequest payload
        calculation_date = parsed_params.get("calculation_date") or datetime.utcnow().strftime("%Y-%m-%d")

        goods = GoodsModel(
            description=parsed_params.get("description") or question or "Direct input calculation",
            hs_code=parsed_params.get("hs_code"),
            origin_country=parsed_params.get("origin_country"),
            quantity=parsed_params.get("quantity"),
            unit=parsed_params.get("unit"),
            net_mass_kg=parsed_params.get("net_mass"),
            volume_liter=parsed_params.get("volume"),
        )

        valuation = ValuationModel(
            customs_value=parsed_params.get("cif_value") or 0.0,
            currency=parsed_params.get("currency"),
            exchange_rate_to_khr=parsed_params.get("exchange_rate_to_khr"),
            declared_value=parsed_params.get("declared_value"),
            declared_value_basis="per_ton" if parsed_params.get("petroleum_case") else "total",
            dq_factor=parsed_params.get("dq_factor"),
        )

        flags = FlagsModel(
            fta_applicable=parsed_params.get("fta_applicable", False),
            fta_certificate_type=parsed_params.get("fta_certificate_type"),
            preferential_cd_rate=parsed_params.get("preferential_cd_rate"),
            dq_applicable=parsed_params.get("dq_applicable", False),
            dq_factor=parsed_params.get("dq_factor"),
            petroleum_case=parsed_params.get("petroleum_case", False),
            rubber_case=parsed_params.get("rubber_case", False),
            qip_exemption=parsed_params.get("qip_exemption", False),
            sez_applicable=parsed_params.get("sez_applicable", False),
            diplomatic_exemption=parsed_params.get("diplomatic_exemption", False),
            ngo_humanitarian=parsed_params.get("ngo_humanitarian", False),
            educational_exemption=parsed_params.get("educational_exemption", False),
            medical_exemption=parsed_params.get("medical_exemption", False),
            passenger_allowance=parsed_params.get("passenger_allowance", False),
        )

        calc_request = CalculateImportTaxesRequest(
            calculation_date=calculation_date,
            regime=parsed_params.get("regime", "import"),
            goods=goods,
            valuation=valuation,
            flags=flags,
        )

        # Invoke the existing calculate_import_taxes function
        return await calculate_import_taxes(
            request=calc_request,
            format_with_llm=format_with_llm,
            db=db,
            fastapi_request=fastapi_request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Error during query calculation")
        raise HTTPException(status_code=500, detail="Internal server error during query calculation")
