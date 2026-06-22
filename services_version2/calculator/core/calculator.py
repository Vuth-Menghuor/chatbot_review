"""
GDCE Calculator Service - Orchestration Layer
==============================================
Orchestrates complete import tax calculations by:
- Validating inputs
- Querying database for rates and exchange rates
- Calling formulas.py calculation functions
- Formatting responses per API contract
- Logging calculations for audit trail

Version: 2.0
Last Updated: 2026-04-22

Integrated Handlers:
- CurrencyHandler: Currency validation, normalization, conversion, exchange rates
- HSCodeHandler: HS code validation, normalization, lookup, candidates
- Settings: Typed configuration from environment variables
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from . import formulas
from .currency_handler import CurrencyHandler
from .formula_engine import FormulaEngine
from .hs_code_handler import HSCodeHandler
from .models import (
    CalculationRequest,
    CalculationResult,
    TaxLineItem,
    TaxReference,
)
from .rules_provider import RulesProvider
from ..config import get_settings

# Configure logging
logger = logging.getLogger(__name__)


# ================================================================
# DATABASE ACCESS (Interface)
# ================================================================

class DatabaseInterface:
    """
    Interface for database operations.
    Implement this with actual DB connection (PostgreSQL, SQLite, etc.)
    """
    
    def get_duty_rates(
        self,
        hs_code: str,
        origin_country: str,
        effective_date: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get normal/MFN duty rates for HS code.

        Returns dict with:
            - cd_rate: Customs duty rate (decimal)
            - st_rate: Special tax rate (decimal)
            - vat_rate: VAT rate (decimal)
            - et_rate: Export Tax on Rubber rate (decimal)
        """
        raise NotImplementedError("Implement database query for duty rates")
    
    def get_exchange_rate(
        self,
        currency_code: str,
        effective_date: str
    ) -> Optional[Decimal]:
        """
        Get exchange rate to KHR for the given currency and date.
        
        Returns:
            Exchange rate as Decimal (e.g., 4022.0 for USD)
        """
        raise NotImplementedError("Implement database query for exchange rates")
    
    def get_hs_code_info(self, hs_code: str) -> Optional[Dict[str, Any]]:
        """
        Get HS code description and unit.
        
        Returns dict with:
            - description: HS code description
            - unit: Unit of measure
        """
        raise NotImplementedError("Implement database query for HS code info")
    
    def get_declared_value(
        self,
        hs_code: str,
        effective_date: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get government-declared fair market value per metric ton for an HS code.

        Returns dict with:
            - dv_per_metric_ton: Decimal
            - currency: str (e.g., 'USD')
            - source: str (e.g., 'MEF-2026-May')
        """
        raise NotImplementedError("Implement database query for declared values")

    def save_calculation(self, calculation_result: CalculationResult) -> None:
        """Save calculation result for audit trail."""
        raise NotImplementedError("Implement calculation logging")


# ================================================================
# CALCULATOR
# ================================================================

class ImportTaxCalculator:
    """
    Main calculator class that orchestrates the calculation workflow.
    
    Integrated with:
    - CurrencyHandler: Handles currency validation and conversion
    - HSCodeHandler: Handles HS code validation and lookup
    - Settings: Loaded configuration from environment
    """
    
    def __init__(
        self,
        db: DatabaseInterface,
        rules_provider: Optional[RulesProvider] = None,
        formula_engine: Optional[FormulaEngine] = None,
    ):
        self.db = db
        self.settings = get_settings()
        
        # Initialize integrated handlers
        self.currency_handler = CurrencyHandler(db)
        self.hs_code_handler = HSCodeHandler(db)
        
        # Dynamic rules engine (optional — falls back to hardcoded formulas)
        self.rules_provider = rules_provider
        self.formula_engine = formula_engine or FormulaEngine()
    
    def calculate(self, request: CalculationRequest) -> CalculationResult:
        """
        Main calculation entry point.

        IMPORTANT: Uses KHR-FIRST methodology
        - Step 1: Convert CIF to KHR (currency conversion FIRST)
        - Step 2-8: ALL calculations in KHR (not USD)
        - Step 9: CEILING rounding to 100 KHR for final payment

        Args:
            request: Calculation request with all inputs

        Returns:
            Complete calculation result with all values in KHR

        Raises:
            ValueError: If required inputs are missing or invalid
        """
        # Generate calculation ID
        calc_id = self._generate_calculation_id(request.calculation_date)

        # --- HS code resolution from commercial description ---
        # If user provided a description but no HS code, attempt to resolve it
        # before validation so the calculator can proceed.
        resolved_hs_info: tuple[Optional[str], Optional[str], list] = (None, None, [])
        if not request.hs_code and request.goods.get("description"):
            desc = request.goods.get("description", "").strip()
            if desc and desc not in ("General merchandise", "Petroleum products", "Rubber products"):
                resolved_hs_info = self.resolve_hs_from_description(desc)
                resolved_hs, resolved_source, _ = resolved_hs_info
                if resolved_hs:
                    request.goods["hs_code"] = resolved_hs
                    logger.info(
                        f"Auto-resolved HS code {resolved_hs} from description '{desc}' "
                        f"via {resolved_source} for calculation"
                    )

        # Validate inputs
        self._validate_request(request)
        
        # =====================================================================
        # STEP 1: CURRENCY CONVERSION - Convert to KHR FIRST
        # =====================================================================
        exchange_rate_khr = self._get_exchange_rate_khr(
            request.currency,
            request.calculation_date,
            request.exchange_rate_to_khr,
        )
        cif_value_khr = formulas.round_to_whole_number(
            Decimal(str(request.customs_value)) * exchange_rate_khr
        )
        logger.debug(f"Step 1: CIF {request.currency} {request.customs_value} → KHR {cif_value_khr}")

        # =====================================================================
        # STEP 2: Load duty rates from Qdrant/CSV (already as decimals)
        # =====================================================================
        rates = self._get_rates(request)
        logger.debug(f"Step 2: Rates loaded - CD:{rates['cd_rate']}, ST:{rates['st_rate']}, VAT:{rates['vat_rate']}")

        # If the user claimed a special rate (FTA or exemption) but did not
        # provide the rate, return early so the orchestrator can ask back.
        if rates.get("preferential_rate_missing"):
            return CalculationResult(
                calculation_id=calc_id,
                currency="KHR",
                total=Decimal("0"),
                breakdown={"cif_value": cif_value_khr, "cop_amount": Decimal("0"), "sop_amount": Decimal("0"), "vop_amount": Decimal("0"), "fees": Decimal("0")},
                line_items=[],
                assumptions=[
                    f"Special rate claimed: {rates.get('requested_agreement', 'Unknown')}",
                    "Pending user to provide the applicable CD rate.",
                ],
                references=[],
                exchange_rate_usd_to_khr=exchange_rate_khr,
                cif_value_usd=Decimal(str(request.customs_value)) if request.currency == "USD" else None,
                preferential_rate_missing=True,
                requested_agreement=rates.get("requested_agreement"),
            )

        # Determine calculation case
        calc_case = self._determine_calculation_case(request)
        
        # =====================================================================
        # STEP 3-8: Perform calculations based on case (ALL IN KHR)
        # =====================================================================
        if calc_case == "petroleum":
            result = self._calculate_petroleum_case(request, cif_value_khr, rates, exchange_rate_khr)
        elif calc_case == "rubber":
            result = self._calculate_rubber_case(request, cif_value_khr, rates, exchange_rate_khr)
        elif calc_case == "fta_dv_dq":
            result = self._calculate_fta_dv_dq_case(request, cif_value_khr, rates, exchange_rate_khr)
        elif calc_case == "fta_dv":
            result = self._calculate_fta_dv_case(request, cif_value_khr, rates, exchange_rate_khr)
        else:  # normal case
            result = self._calculate_normal_case(request, cif_value_khr, rates, exchange_rate_khr)

        # Inject auto-resolved HS warning into assumptions if applicable
        resolved_hs, resolved_source, _ = resolved_hs_info
        if resolved_hs and resolved_source:
            desc = request.goods.get("description", "").strip()
            warning = (
                f"⚠️  HS code {resolved_hs} was auto-resolved from the product description "
                f"'{desc}' via {resolved_source} search. This HS code may not be fully correct "
                f"because you did not provide a clear description or an explicit HS code. "
                f"Please verify the HS code with customs or provide the exact HS code for an accurate calculation."
            )
            result["assumptions"].insert(0, warning)

        # All results display in KHR (tax payers must pay in KHR)
        output_currency = "KHR"
        
        # Create calculation result
        calculation_result = CalculationResult(
            calculation_id=calc_id,
            currency=output_currency,
            total=result["total"],
            breakdown=result["breakdown"],
            line_items=result["line_items"],
            assumptions=result["assumptions"],
            references=result["references"],
            exchange_rate_usd_to_khr=exchange_rate_khr,
            cif_value_usd=Decimal(str(request.customs_value)) if request.currency == "USD" else None,
            preferential_rate_missing=rates.get("preferential_rate_missing"),
            requested_agreement=rates.get("requested_agreement"),
        )
        
        # Save to database for audit
        try:
            self.db.save_calculation(calculation_result)
        except Exception as e:
            logger.warning(f"Failed to save calculation: {e}")
        
        return calculation_result
    
    def _generate_calculation_id(self, calculation_date: str) -> str:
        """Generate unique calculation ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"calc_{calculation_date}_{timestamp}"
    
    def _validate_request(self, request: CalculationRequest) -> None:
        """Validate calculation request."""
        flags = request.flags or {}

        # Check required fields
        # HS code is required UNLESS:
        #   - passenger allowance applies
        #   - a commercial description was provided (resolution attempted before this call)
        has_desc = bool(
            request.goods.get("description", "").strip()
            and request.goods.get("description") not in ("General merchandise", "Petroleum products", "Rubber products")
        )
        if not request.hs_code and not flags.get("passenger_allowance"):
            if has_desc:
                raise ValueError(
                    "No HS code was provided and we could not resolve one from the product description. "
                    "Please provide a clearer product description or an explicit HS code."
                )
            raise ValueError(
                "hs_code is required. Please provide either an HS code (e.g., '8703.22.59') "
                "or a clear product description (e.g., 'toyota camry 2024')."
            )

        if request.customs_value <= 0:
            raise ValueError("customs_value must be positive")

        if not request.currency:
            raise ValueError("currency is required")

        # Validate HS code format
        if request.hs_code and not self._is_valid_hs_code(request.hs_code):
            raise ValueError(f"Invalid HS code format: {request.hs_code}")

        regime = (request.regime or "").lower()

        if regime == "export":
            if not flags.get("rubber_case"):
                raise ValueError(
                    "Export calculations currently support rubber_case only. "
                    "Other export formulas are not configured yet."
                )
            if flags.get("petroleum_case") or flags.get("fta_applicable"):
                raise ValueError("Petroleum and FTA/DV cases are import-only and cannot use regime='export'")
        elif flags.get("rubber_case"):
            raise ValueError("rubber_case is an export calculation and requires regime='export'")

        if request.declared_value is not None and request.declared_value_basis not in ("total", "per_ton"):
            raise ValueError("declared_value_basis must be either 'total' or 'per_ton'")

        if request.dq_factor <= 0:
            raise ValueError("dq_factor must be positive when provided")

    def _is_valid_hs_code(self, hs_code: str) -> bool:
        """Check if HS code has valid format."""
        # Remove dots for validation
        clean_code = hs_code.replace(".", "")
        # Must be 4, 6, or 8 digits
        return clean_code.isdigit() and len(clean_code) in [4, 6, 8]

    def get_hs_code_candidates(
        self,
        query: str,
        limit: Optional[int] = None
    ) -> list[Dict[str, Any]]:
        """
        Get candidate HS codes for a query (description or partial code).
        
        Used for fallback scenarios where HS code is not provided or is unknown.
        Queries the database for matching descriptions.
        
        Args:
            query: Search query (description or partial HS code)
            limit: Maximum number of candidates (default from settings)
            
        Returns:
            List of dicts with keys: hs_code, description, score
        """
        if limit is None:
            limit = self.settings.hs_code_candidate_limit
        
        return self.hs_code_handler.get_candidates(
            query,
            limit=limit,
            fuzzy=self.settings.enable_hs_fuzzy_search
        )

    def resolve_hs_from_description(
        self,
        description: str,
        top_k: int = 1
    ) -> tuple[Optional[str], Optional[str], list[Dict[str, Any]]]:
        """
        Resolve an HS code from a commercial product description.

        Resolution order (most accurate first):
          1. Semantic search via Qdrant (best for natural-language descriptions)
          2. CSV keyword search fallback
          3. HSCodeHandler fuzzy candidate search

        Args:
            description: Commercial product description (e.g., "iphone 15", "toyota camry")
            top_k: How many candidates to fetch from semantic search

        Returns:
            Tuple of (resolved_hs_code, source, candidates_list)
            - resolved_hs_code: Best-match HS code or None
            - source: Where it came from ("qdrant", "csv", "fuzzy", or None)
            - candidates_list: Full list of candidates for user review
        """
        if not description or not description.strip():
            return None, None, []

        desc = description.strip()
        candidates: list[dict] = []

        # 1. Semantic search (Qdrant) — best for commercial descriptions
        if hasattr(self.db, "search_hs_by_description"):
            try:
                qdrant_results = self.db.search_hs_by_description(desc, top_k=top_k)
                if qdrant_results:
                    for item in qdrant_results:
                        hs = item.get("hs_code") or item.get("code")
                        if hs:
                            candidates.append({
                                "hs_code": hs,
                                "description": item.get("description", ""),
                                "score": item.get("score", item.get("confidence", 0.0)),
                                "source": "qdrant",
                            })
                    if candidates:
                        top = candidates[0]
                        logger.info(
                            f"Resolved HS {top['hs_code']} from description '{desc}' "
                            f"via Qdrant (score={top.get('score', 0):.3f})"
                        )
                        return top["hs_code"], "qdrant", candidates
            except Exception as e:
                logger.warning(f"Qdrant semantic search failed for '{desc}': {e}")

        # 2. CSV keyword search fallback
        if hasattr(self.db, "search_by_description"):
            try:
                csv_result = self.db.search_by_description(desc)
                if csv_result:
                    resolved_hs, confidence = csv_result
                    candidates.append({
                        "hs_code": resolved_hs,
                        "description": "",
                        "score": confidence,
                        "source": "csv",
                    })
                    logger.info(
                        f"Resolved HS {resolved_hs} from description '{desc}' "
                        f"via CSV keyword search (confidence={confidence:.3f})"
                    )
                    return resolved_hs, "csv", candidates
            except Exception as e:
                logger.warning(f"CSV keyword search failed for '{desc}': {e}")

        # 3. HSCodeHandler fuzzy candidate search
        try:
            handler_candidates = self.hs_code_handler.get_candidates(desc, limit=top_k)
            if handler_candidates:
                for c in handler_candidates:
                    c["source"] = "fuzzy"
                    candidates.append(c)
                top = candidates[0]
                logger.info(
                    f"Resolved HS {top['hs_code']} from description '{desc}' "
                    f"via fuzzy search (score={top.get('score', 0):.3f})"
                )
                return top["hs_code"], "fuzzy", candidates
        except Exception as e:
            logger.warning(f"Fuzzy HS search failed for '{desc}': {e}")

        return None, None, []

    def _get_exchange_rate_khr(
        self,
        currency: str,
        calculation_date: str,
        explicit_rate: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Get exchange rate to KHR using CurrencyHandler.
        If currency is already KHR, returns 1.0
        """
        if currency == "KHR":
            return Decimal("1.0")

        if explicit_rate is not None:
            rate = Decimal(str(explicit_rate))
            if rate <= 0:
                raise ValueError("exchange_rate_to_khr must be positive")
            logger.info(f"Using explicit exchange rate for {currency}: {rate}")
            return rate

        if currency == "USD" and self.settings.usd_to_khr_rate is not None:
            rate = Decimal(str(self.settings.usd_to_khr_rate))
            logger.info(f"Using configured USD fallback rate: 1 USD = {rate} KHR")
            return rate

        try:
            rate = self.currency_handler.get_exchange_rate(
                currency,
                target_currency="KHR",
                calculation_date=calculation_date,
                use_fallback=True
            )
            return rate
        except ValueError as e:
            logger.error(f"Failed to get exchange rate for {currency}: {e}")
            raise
    
    def _get_rates(self, request: CalculationRequest) -> Dict[str, Decimal]:
        """
        Get duty rates from database.

        The database ONLY stores normal/MFN rates. Preferential rates (FTA,
        exemption) are provided by the user via DV or preferential_cd_rate.
        """
        # Load normal/MFN rates from database (origin='XX')
        rates_data = self.db.get_duty_rates(
            request.hs_code,
            "XX",
            request.calculation_date,
        )

        if rates_data is None:
            raise ValueError(f"Duty rates not found for HS code {request.hs_code}")

        def _rate(data, key, default):
            return Decimal(str(data.get(key, default))) if data else Decimal(str(default))

        result = {
            "cd_rate": _rate(rates_data, "cd_rate", 0),
            "st_rate": _rate(rates_data, "st_rate", 0),
            "vat_rate": _rate(rates_data, "vat_rate", 0.10),
            "et_rate": _rate(rates_data, "et_rate", 0),
            # Normal / MFN rates (for Original Amount cumulative base in FTA cases)
            "cd_rate_normal": _rate(rates_data, "cd_rate", 0),
            "st_rate_normal": _rate(rates_data, "st_rate", 0),
            "vat_rate_normal": _rate(rates_data, "vat_rate", 0.10),
        }

        # ATP rate for petroleum products
        if "atp_rate" in rates_data:
            result["atp_rate"] = Decimal(str(rates_data["atp_rate"]))

        # Check if any exemption applies.
        flags = request.flags or {}
        exemption_map = {
            "qip_exemption": "QIP",
            "sez_applicable": "SEZ",
            "diplomatic_exemption": "Diplomatic",
            "ngo_humanitarian": "NGO / Humanitarian",
            "educational_exemption": "Educational",
            "medical_exemption": "Medical",
            "passenger_allowance": "Passenger",
        }
        active_exemption = None
        for flag, label in exemption_map.items():
            if flags.get(flag):
                active_exemption = label
                break

        agreement_code = request.flags.get("fta_certificate_type") if request.flags else None

        # Default FTA rates for agreements that are typically 0% for most goods.
        # Agreements with variable rates (AKFTA, AJCEP, RCEP) still require explicit rate.
        FTA_ZERO_RATE_AGREEMENTS = {"ACFTA", "ATIGA", "AANZFTA"}

        # Apply user-provided preferential CD rate override (e.g., from orchestrator ask-back)
        user_pref_cd = request.preferential_cd_rate
        if user_pref_cd is not None:
            result["cd_rate"] = user_pref_cd / Decimal("100")
            result["preferential_rate_missing"] = False
            logger.info(
                f"Applied user-provided preferential CD rate {float(user_pref_cd)}% "
                f"for {request.hs_code}"
            )

        # Cambodian customs convention: when exemption/FTA applies,
        # the declared_value field IS the COP rate percentage (not a valuation).
        # DV = 0.00 means 0% duty-free; DV = 5.00 means 5% rate.
        # Exception: petroleum cases use DV as real declared value per ton.
        is_petroleum = (request.flags or {}).get("petroleum_case") or (request.hs_code or "").startswith("27")
        if request.declared_value is not None and (active_exemption or agreement_code) and not is_petroleum:
            result["cd_rate"] = Decimal(str(request.declared_value)) / Decimal("100")
            result["preferential_rate_missing"] = False
            logger.info(
                f"Exemption/FTA with DV={request.declared_value}; "
                f"using DV as COP rate: {float(result['cd_rate'] * 100):.2f}%"
            )

        # DV = 0 in any non-petroleum case → duty-free (same as zero-rate FTA)
        elif request.declared_value is not None and request.declared_value == 0 and not is_petroleum:
            result["cd_rate"] = Decimal("0")
            result["preferential_rate_missing"] = False
            logger.info(
                f"DV=0 provided for {request.hs_code}; "
                f"applying 0% CD rate (duty-free)."
            )

        # Auto-apply 0% for known zero-rate FTAs (ACFTA, ATIGA, AANZFTA)
        elif agreement_code and agreement_code.upper() in FTA_ZERO_RATE_AGREEMENTS and request.preferential_cd_rate is None:
            result["cd_rate"] = Decimal("0")
            result["preferential_rate_missing"] = False
            logger.info(
                f"Auto-applied 0% preferential CD rate for {agreement_code} "
                f"on HS {request.hs_code}"
            )

        # Ask back when FTA/exemption claimed but no rate provided (DV missing, no preferential_cd_rate)
        elif agreement_code and request.preferential_cd_rate is None:
            result["preferential_rate_missing"] = True
            result["requested_agreement"] = agreement_code
            logger.info(
                f"FTA {agreement_code} claimed for {request.hs_code}; "
                f"requesting user to provide the applicable CD rate."
            )

        elif active_exemption and request.preferential_cd_rate is None:
            result["preferential_rate_missing"] = True
            result["requested_agreement"] = active_exemption
            logger.info(
                f"Exemption {active_exemption} claimed for {request.hs_code}; "
                f"requesting user to provide the applicable CD rate."
            )

        # ATP rate is loaded from the untartab / DB first.  If a petroleum HS code
        # lacks an ATP entry we fall back to the standard 0.02 $/L so the calculator
        # does not hard-fail on incomplete DB rows, but we log a loud warning.
        atp_from_data = rates_data.get("atp_rate") if rates_data else None
        if atp_from_data is not None:
            result["atp_rate"] = Decimal(str(atp_from_data))
        elif (request.hs_code or "").startswith("27"):
            result["atp_rate"] = Decimal("0.02")
            logger.warning(
                f"ATP rate missing in DB for {request.hs_code}; "
                f"using fallback 0.02 $/L. Add this HS code to untartab."
            )

        return result
    
    def _determine_calculation_case(self, request: CalculationRequest) -> str:
        """Determine which calculation case to use."""
        flags = request.flags or {}
        hs = request.hs_code or ""
        is_petroleum = (request.flags or {}).get("petroleum_case") or (request.hs_code or "").startswith("27")
        dv_zero = request.declared_value is not None and request.declared_value == 0

        if request.regime == "export" and flags.get("rubber_case"):
            return "rubber"
        if flags.get("petroleum_case") or (hs.startswith("27") and request.volume_liter):
            return "petroleum"
        elif (flags.get("fta_applicable") or dv_zero) and request.dq_applicable and not is_petroleum:
            return "fta_dv_dq"
        elif (flags.get("fta_applicable") or dv_zero) and not is_petroleum:
            return "fta_dv"
        else:
            return "normal"

    def _get_declared_value_per_ton(
        self,
        request: CalculationRequest,
        fallback_total_value: Decimal
    ) -> tuple[Decimal, str]:
        """Return DV as price per metric ton in the request currency.

        Resolution order:
          1. Government DB lookup by HS code + date (if available)
          2. User-provided declared_value in request (override)
          3. Fallback: derive from customs_value / metric tons
        """
        net_mass_kg = request.net_mass_kg_normalized
        if not net_mass_kg or net_mass_kg <= 0:
            raise ValueError(
                "Declared Value per ton requires net mass "
                "(net_mass_kg, net_mass_tons, or net_mass_kg with net_mass_unit='ton')"
            )

        metric_tons = net_mass_kg / Decimal("1000")

        # 1. Try government DB lookup
        if request.hs_code:
            dv_record = self.db.get_declared_value(
                request.hs_code,
                request.calculation_date
            )
            if dv_record:
                dv = Decimal(str(dv_record["dv_per_metric_ton"]))
                source = f"government DV ({dv_record.get('source', 'DB')})"
                if request.declared_value is not None:
                    source += " — overridden by request"
                    return request.declared_value, source
                return dv, source

        # 2. User-provided declared_value
        if request.declared_value is not None:
            if request.declared_value_basis == "per_ton":
                return request.declared_value, "provided as declared_value per metric ton"
            return request.declared_value / metric_tons, "provided as total declared_value"

        # 3. Fallback: derive from customs_value
        return fallback_total_value / metric_tons, "derived from customs_value"

    def _get_declared_value_khr(
        self,
        request: CalculationRequest,
        fallback_value_khr: Decimal,
        exchange_rate_khr: Decimal
    ) -> tuple[Decimal, str]:
        """Return DV total value in KHR.

        Safety: a declared_value of 0 is never a real customs valuation.
        Treat it as "not provided" and fall back to the customs value.
        """
        if request.declared_value is None or request.declared_value == 0:
            return fallback_value_khr, "derived from customs_value"

        if request.declared_value_basis == "per_ton":
            if not request.net_mass_kg_normalized or request.net_mass_kg_normalized <= 0:
                raise ValueError("declared_value_basis='per_ton' requires net_mass_kg")
            total = request.declared_value * (Decimal(str(request.net_mass_kg_normalized)) / Decimal("1000"))
        else:
            total = request.declared_value

        return formulas.round_to_whole_number(total * exchange_rate_khr), f"provided declared_value ({request.declared_value_basis})"

    def _apply_dq_factor(self, amount: Decimal, request: CalculationRequest) -> Decimal:
        """Apply user-provided DQ factor when dq_applicable is true."""
        if not request.dq_applicable:
            return amount
        return amount * request.dq_factor

    def _dq_assumptions(self, request: CalculationRequest) -> list[str]:
        """Human-readable DQ context for calculation traces."""
        if not request.dq_applicable:
            return []

        discount_pct = float(request.dq_factor * Decimal("100"))
        payable_pct = float((Decimal("1") - request.dq_factor) * Decimal("100"))
        lines = [
            f"DQ factor: {float(request.dq_factor):.4f}",
            f"DQ discount: {discount_pct:.2f}% (payable = {payable_pct:.2f}% of tax)",
        ]
        return lines

    def _is_vehicle(self, request: CalculationRequest) -> bool:
        """Check if HS code belongs to vehicles (Chapter 87)."""
        hs = request.hs_code or ""
        return hs.startswith("87")

    def _calculate_vvf(self, request: CalculationRequest) -> Decimal:
        """Vehicle Valuation Fee (VVF) — fixed 60,000 KHR per vehicle unit."""
        if not self._is_vehicle(request):
            return Decimal("0")
        qty = request.quantity if request.quantity is not None else Decimal("1")
        return Decimal("60000") * qty
    
    def _apply_dynamic_rounding(self, amount: Decimal, field_name: str) -> Decimal:
        """
        Apply rounding using dynamic rules if available, else use hardcoded default.
        
        Falls back to CEILING_100 for tax components and total_payable,
        or the original formulas.py functions.
        """
        if self.rules_provider:
            rule = self.rules_provider.get_rounding_rule(field_name)
            return self.formula_engine.apply_rounding(amount, rule=rule)
        
        # Fallback: use hardcoded rounding from formulas.py
        if field_name in ("total_payable",):
            return formulas.round_up_to_hundred(amount)
        elif field_name in ("cop_amount", "sop_amount", "vop_amount", "total_duties_and_taxes"):
            return formulas.round_up_to_hundred(amount)
        return amount
    
    def _calculate_vop_dynamic(
        self,
        customs_value: Decimal,
        cop_amount: Decimal,
        sop_amount: Decimal,
        vat_rate: Decimal,
    ) -> Decimal:
        """
        Calculate VOP using dynamic formula if available, else hardcoded logic.
        
        The conditional base logic (taxable vs non-taxable) is handled by:
        1. Dynamic formula with IF/ELSE expression (if loaded from DB)
        2. Hardcoded conditional in formulas.py (fallback)
        """
        # Try dynamic formula
        if self.rules_provider:
            vop_formula = self.rules_provider.get_formula("VOP_001")
            if vop_formula and vop_formula.expression:
                try:
                    variables = {
                        "customs_value": customs_value,
                        "cop_amount": cop_amount,
                        "sop_amount": sop_amount,
                        "vat_rate": vat_rate,
                    }
                    result = self.formula_engine.evaluate(vop_formula.expression, variables)
                    result = formulas.round_to_whole_number(result)
                    return self._apply_dynamic_rounding(result, "vop_amount")
                except Exception as e:
                    logger.warning(f"Dynamic VOP formula failed, using fallback: {e}")
        
        # Fallback: hardcoded conditional logic
        if sop_amount == 0:
            vat_base = customs_value + cop_amount
        else:
            vat_base = customs_value + cop_amount + sop_amount
        
        vop_amount = formulas.round_to_whole_number(vat_base * vat_rate)
        return self._apply_dynamic_rounding(vop_amount, "vop_amount")
    
    def _calculate_normal_case(
        self,
        request: CalculationRequest,
        cif_value_khr: Decimal,
        rates: Dict[str, Decimal],
        exchange_rate_khr: Decimal
    ) -> Dict[str, Any]:
        """
        Calculate using normal case formula.
        
        Args:
            request: Calculation request
            cif_value_khr: CIF value already converted to KHR
            rates: Duty rates (as decimals)
            exchange_rate_khr: Exchange rate to KHR (already applied to CIF)
        """
        # KHR-FIRST: Values are already in KHR, no need to fetch exchange rate or convert
        # All calculations below work directly with KHR values
        
        # Step 2/3: Calculate Import Taxes (COP)
        cop_amount = formulas.round_to_whole_number(cif_value_khr * rates["cd_rate"])
        cop_amount = self._apply_dynamic_rounding(cop_amount, "cop_amount")
        
        # Step 4: Calculate Special Tariff (SOP) on (Customs Value + COP)
        st_base = cif_value_khr + cop_amount
        flags = request.flags or {}
        if flags.get("fta_applicable"):
            sop_amount = formulas.round_to_whole_number(
                self._apply_dq_factor(st_base * rates["st_rate"], request)
            )
        else:
            sop_amount = formulas.round_to_whole_number(st_base * rates["st_rate"])
        sop_amount = self._apply_dynamic_rounding(sop_amount, "sop_amount")
        
        # Step 5: Calculate VAT - Base is conditional on whether special tax exists
        # Dynamic VOP formula (if available) handles the conditional base
        vop_amount = self._calculate_vop_dynamic(
            cif_value_khr, cop_amount, sop_amount, rates["vat_rate"]
        )
        
        # Step 9: Calculate Total
        vvf = self._calculate_vvf(request)
        total_before_rounding = cop_amount + sop_amount + vop_amount + vvf
        total_payable = self._apply_dynamic_rounding(total_before_rounding, "total_payable")
        
        # Compute vat_base for display purposes (matches the VOP calculation logic)
        if sop_amount == 0:
            vat_base = cif_value_khr + cop_amount
        else:
            vat_base = cif_value_khr + cop_amount + sop_amount
        
        # Build line items (always include all steps so users see 0-amount components)
        line_items = [
            TaxLineItem(
                name="Import Taxes (COP)",
                tax_type="CD",
                amount=cop_amount,
                currency="KHR",
                base=cif_value_khr,
                rate=rates["cd_rate"] * Decimal('100')
            ),
            TaxLineItem(
                name="Special Tariff (SOP)",
                tax_type="ST",
                amount=sop_amount,
                currency="KHR",
                base=st_base,
                rate=rates["st_rate"] * Decimal('100')
            ),
            TaxLineItem(
                name="VOP (VAT of Payment)",
                tax_type="VAT",
                amount=vop_amount,
                currency="KHR",
                base=vat_base,
                rate=rates["vat_rate"] * Decimal('100')
            ),
        ]
        if vvf > 0:
            line_items.append(
                TaxLineItem(
                    name="Vehicle Valuation Fee (VVF)",
                    tax_type="VVF",
                    amount=vvf,
                    currency="KHR",
                    base=request.quantity or Decimal("1"),
                    rate=Decimal("60000"),
                )
            )
        
        # Build assumptions - include exchange rate
        assumptions = [
            f"HS Code: {request.hs_code}",
            f"Product: {request.goods.get('description', 'N/A')}",
            f"Origin country: {request.origin_country or 'General rates'}",
        ]
        if request.declared_value is not None:
            basis_label = request.declared_value_basis or "total"
            assumptions.append(f"DV: {float(request.declared_value):,.2f} USD ({basis_label})")
        assumptions.extend([
            "",
            "=== APPLICABLE RATES ===",
            f"Import Tax (COP) rate: {float(rates['cd_rate'] * 100):.2f}%",
            f"Special Tariff (SOP) rate: {float(rates['st_rate'] * 100):.2f}%",
            f"VAT rate: {float(rates['vat_rate'] * 100):.2f}%",
            f"Exchange rate: 1 {request.currency} = {float(exchange_rate_khr):,.2f} KHR",
            "Source: duty_rates.csv"
        ])
        assumptions.extend(self._dq_assumptions(request))
        
        # Build references with official citation sources
        references = [
            TaxReference(
                doc_id=f"gdce_calculator.duty_rates:{request.hs_code}",
                title=f"HS Code {request.hs_code} - Duty Rates (CD, ST, VAT)",
                effective_start_date=request.calculation_date,
                source_url="https://gdce.gov.kh/tariff-search",
                section_title="Official Tariff Website"
            ),
            TaxReference(
                doc_id="gdce_calculator.exchange_rates:USD",
                title="Exchange Rate USD to KHR",
                effective_start_date=request.calculation_date,
                source_url="https://nbc.gov.kh/",
                section_title="National Bank of Cambodia"
            ),
        ]
        
        # Calculate original USD amount if not already provided
        cif_value_usd = Decimal(str(request.customs_value)) if request.currency == "USD" else None
        
        return {
            "total": total_payable,
            "currency": "KHR",
            "exchange_rate_usd_to_khr": exchange_rate_khr,
            "cif_value_usd": cif_value_usd,
            "breakdown": {
                "cif_value": cif_value_khr,
                "cop_amount": cop_amount,
                "sop_amount": sop_amount,
                "vop_amount": vop_amount,
                "vvf_amount": vvf,
                "fees": vvf,
            },
            "line_items": line_items,
            "assumptions": assumptions,
            "references": references
        }
    
    def _calculate_petroleum_case(
        self,
        request: CalculationRequest,
        cif_value_khr: Decimal,
        rates: Dict[str, Decimal],
        exchange_rate_khr: Decimal
    ) -> Dict[str, Any]:
        """
        Calculate using petroleum case (two-phase calculation).
        
        Args:
            request: Calculation request with net_mass_kg and volume_liter
            cif_value_khr: CIF value already converted to KHR
            rates: Duty rates (as decimals)
            exchange_rate_khr: Exchange rate to KHR (already applied to CIF)
        """
        
        # KHR-FIRST: All calculations work directly with KHR values
        # Requires DV (Declared Value), net mass, and volume
        # net_mass_kg_normalized handles tons → kg conversion automatically
        net_mass_kg = request.net_mass_kg_normalized
        if not net_mass_kg or not request.volume_liter:
            raise ValueError(
                "Petroleum case requires net mass (net_mass_kg, net_mass_tons, or "
                "net_mass_kg with net_mass_unit='ton') and volume_liter"
            )

        cif_value_usd = Decimal(str(request.customs_value))

        # Phase 1: Calculate using CPP base (Declared Value)
        # DV = fair market price per metric TON in request currency
        # CPP base = (DV_per_ton × exchange_rate × net_mass_kg) / 1000
        dv_per_ton, dv_source = self._get_declared_value_per_ton(request, cif_value_usd)

        # Calculate CPP base in KHR
        cpp_base_khr = formulas.round_to_whole_number(
            (dv_per_ton * exchange_rate_khr * net_mass_kg) / Decimal('1000')
        )

        # CPP (Customs duty on Petroleum)
        cpp = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(cpp_base_khr * rates["cd_rate"])
        )

        # ATP (Additional Tax on Petroleum) — volume-based, not value-based
        if "atp_rate" not in rates:
            raise ValueError(
                f"ATP rate not found for HS code {request.hs_code}. "
                f"Petroleum products must have an ATP rate defined in untartab."
            )
        atp = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(
                Decimal(str(request.volume_liter)) * rates["atp_rate"] * exchange_rate_khr
            )
        )

        # SPP (Special Tax on Petroleum)
        # SPP base = CPP base + CPP amount + ATP amount
        spp_base = cpp_base_khr + cpp + atp
        spp = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(self._apply_dq_factor(spp_base * rates["st_rate"], request))
        )

        # VPP (VAT on Petroleum)
        # VPP base = CPP base + CPP amount + ATP amount + SPP amount
        # (explicitly expanded — NOT written as "spp_base + spp" to avoid confusion)
        vpp_base = cpp_base_khr + cpp + atp + spp
        vpp = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(vpp_base * rates["vat_rate"])
        )
        
        total_payable = cpp + atp + spp + vpp
        
        # Phase 2: Recalculate using actual Customs Value (CIF_KHR) as CPP base
        phase2_cpp_base = cif_value_khr
        phase2_cpp = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(phase2_cpp_base * rates["cd_rate"])
        )
        phase2_atp = atp  # ATP is volume-based — identical in both phases

        # Phase 2 SPP base = Phase2 CPP base + Phase2 CPP + ATP
        phase2_spp_base = phase2_cpp_base + phase2_cpp + phase2_atp
        phase2_spp = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(self._apply_dq_factor(phase2_spp_base * rates["st_rate"], request))
        )

        # Phase 2 VPP base = Phase2 CPP base + Phase2 CPP + ATP + Phase2 SPP
        phase2_vpp_base = phase2_cpp_base + phase2_cpp + phase2_atp + phase2_spp
        phase2_vpp = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(phase2_vpp_base * rates["vat_rate"])
        )
        
        phase2_total = phase2_cpp + phase2_atp + phase2_spp + phase2_vpp

        # Cambodian customs rule for petroleum: importer ALWAYS pays Phase 1.
        # DPP (difference between Phase 1 and Phase 2) is handled separately
        # by the state — either as an additional charge (when Phase 2 > Phase 1)
        # or as a subsidy (when Phase 1 > Phase 2). It is NOT added to/subtracted
        # from the importer's payable amount.
        phase1_total = cpp + atp + spp + vpp
        total_payable = phase1_total  # always Phase 1
        phase2_wins = phase2_total > phase1_total

        # Customs-correct DPP = subsidy only when Phase 1 is higher
        dpp = formulas.calculate_petroleum_dpp(phase1_total, phase2_total)
        # Absolute gap for informational display (always positive)
        dpp_gap = abs(phase1_total - phase2_total)

        # Build line items from Phase 1 — that's what the importer actually pays.
        atp_rate_khr_per_liter = rates["atp_rate"] * exchange_rate_khr
        line_items = [
            TaxLineItem("Customs Duty (CPP)", "CD", cpp, "KHR", cpp_base_khr, rates["cd_rate"] * Decimal('100')),
            TaxLineItem("Additional Tax (ATP)", "ATP", atp, "KHR", Decimal(str(request.volume_liter)), atp_rate_khr_per_liter),
            TaxLineItem("Special Tax (SPP)", "ST", spp, "KHR", spp_base, rates["st_rate"] * Decimal('100')),
            TaxLineItem("VAT (VPP)", "VAT", vpp, "KHR", vpp_base, rates["vat_rate"] * Decimal('100'))
        ]

        # DPP (Difference / Partial Subsidy) — informational row only.
        # Amount is ALWAYS the absolute gap (positive) so it never reads as negative or zero.
        # Label switches based on direction for clarity on the SAD.
        dpp_positive = abs(phase1_total - phase2_total)
        if phase2_wins:
            line_items.append(TaxLineItem("Additional charge (DPP)", "DPP", dpp_positive, "KHR", Decimal('0'), Decimal('0')))
        elif phase1_total > phase2_total:
            line_items.append(TaxLineItem("Subsidy by the state (DPP)", "DPP", dpp_positive, "KHR", Decimal('0'), Decimal('0')))
        else:
            line_items.append(TaxLineItem("No difference between phases (DPP)", "DPP", Decimal('0'), "KHR", Decimal('0'), Decimal('0')))

        assumptions = [
            f"HS Code: {request.hs_code}",
            f"Product: {request.goods.get('description', 'N/A')}",
            f"Origin country: {request.origin_country or 'N/A'}",
            f"Net mass: {float(net_mass_kg):,.2f} kg (provided as: {request.goods.get('net_mass_tons', request.goods.get('net_mass_kg'))} {request.net_mass_unit})",
            f"Volume: {request.volume_liter} liters",
            f"DV: {float(dv_per_ton):,.4f} {request.currency} per metric ton ({dv_source})",
            "=== APPLICABLE RATES (PETROLEUM) ===",
            f"Customs Petroleum Payment (CPP) rate: {float(rates['cd_rate'] * 100):.2f}%",
            f"Additional Tax Petroleum (ATP) rate: {float(rates['atp_rate']):.2f} $/L",
            f"Special Petroleum Payment (SPP) rate: {float(rates['st_rate'] * 100):.2f}%",
            f"VAT Petroleum Payment (VPP) rate: {float(rates['vat_rate'] * 100):.2f}%",
            f"Exchange rate: 1 USD = {float(exchange_rate_khr):,.2f} KHR",
            "Source: duty_rates.csv"
        ]
        assumptions.extend(self._dq_assumptions(request))
        
        references = [
            TaxReference(
                doc_id="gdce_calculator.duty_rates:petroleum",
                title=f"HS Code {request.hs_code} - Petroleum Rates (CPP, ATP, SPP, VPP)",
                effective_start_date=request.calculation_date,
                source_url="https://gdce.gov.kh/tariff-search",
                section_title="Official Tariff Website"
            ),
            TaxReference(
                doc_id="gdce_calculator.exchange_rates:USD",
                title="Exchange Rate USD to KHR",
                effective_start_date=request.calculation_date,
                source_url="https://nbc.gov.kh/",
                section_title="National Bank of Cambodia"
            ),
            TaxReference(
                doc_id="formula_registry.json:petroleum_case",
                title="Petroleum Calculation Formula",
                source_url="https://gdce.gov.kh/tariff-search",
                section_title="Calculator Formula Registry"
            ),
        ]
        
        return {
            "total": total_payable,
            "currency": "KHR",
            "exchange_rate_usd_to_khr": exchange_rate_khr,
            "cif_value_usd": cif_value_usd,
            "breakdown": {
                "cif_value": cif_value_khr,
                "cpp_base": cpp_base_khr,
                "cpp_amount": cpp,
                "atp_amount": atp,
                "spp_amount": spp,
                "vpp_amount": vpp,
                "dpp_amount": dpp,
                "dpp_gap": dpp_gap,
                "phase2_cpp_amount": phase2_cpp,
                "phase2_atp_amount": phase2_atp,
                "phase2_spp_amount": phase2_spp,
                "phase2_vpp_amount": phase2_vpp,
                "phase2_total": phase2_total,
                "fees": Decimal('0')
            },
            "line_items": line_items,
            "assumptions": assumptions,
            "references": references
        }
        
    
    def _calculate_rubber_case(
        self,
        request: CalculationRequest,
        cif_value_khr: Decimal,
        rates: Dict[str, Decimal],
        exchange_rate_khr: Decimal
    ) -> Dict[str, Any]:
        """
        Calculate using rubber case (Export Tax on Rubber based on mass).
        
        Args:
            request: Calculation request with net_mass_kg
            cif_value_khr: CIF value already converted to KHR
            rates: Duty rates (as decimals)
            exchange_rate_khr: Exchange rate to KHR (already applied to CIF)
        """
        
        if not request.net_mass_kg_normalized:
            raise ValueError("Rubber case requires net_mass_kg")
        
        # KHR-FIRST: All calculations in KHR
        # ETR = (Declared Value in KHR / Net Mass) × Export Tax rate
        # = (CIF_KHR / net_mass_kg) × et_rate
        
        cif_value_usd = Decimal(str(request.customs_value))
        
        # Calculate ETR directly in KHR
        dv_khr, dv_source = self._get_declared_value_khr(request, cif_value_khr, exchange_rate_khr)
        net_mass_kg = request.net_mass_kg_normalized
        etr_base = dv_khr / Decimal(str(net_mass_kg))
        etr_amount = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(
                self._apply_dq_factor(etr_base * rates.get("et_rate", Decimal('0')), request)
            )
        )

        # ETR is the only tax for rubber export — no VAT applies on exports
        total_payable = etr_amount
        
        # Build line items
        line_items = [
            TaxLineItem("Export Tax on Rubber (ETR)", "ST", etr_amount, "KHR", net_mass_kg, rates.get("et_rate", Decimal('0')) * Decimal('100')),
        ]

        assumptions = [
            f"HS Code: {request.hs_code}",
            f"Product: {request.goods.get('description', 'N/A')}",
            f"Origin country: {request.origin_country or 'N/A'}",
            f"Net mass: {float(net_mass_kg):,.2f} kg",
            f"DV total: {float(dv_khr):,.2f} KHR ({dv_source})",
            "",
            "=== APPLICABLE RATES (RUBBER) ===",
            f"Export Tax on Rubber (ETR) rate: {float(rates.get('et_rate', 0) * 100):.2f}%",
            f"Exchange rate: 1 USD = {float(exchange_rate_khr):,.2f} KHR",
            "Source: duty_rates.csv"
        ]
        assumptions.extend(self._dq_assumptions(request))
        
        references = [
            TaxReference(
                doc_id="gdce_calculator.duty_rates:rubber",
                title=f"HS Code {request.hs_code} - Rubber Export Rates (ETR)",
                effective_start_date=request.calculation_date,
                source_url="https://gdce.gov.kh/tariff-search",
                section_title="Official Tariff Website"
            ),
            TaxReference(
                doc_id="gdce_calculator.exchange_rates:USD",
                title="Exchange Rate USD to KHR",
                effective_start_date=request.calculation_date,
                source_url="https://nbc.gov.kh/",
                section_title="National Bank of Cambodia"
            ),
            TaxReference(
                doc_id="formula_registry.json:rubber_case",
                title="Rubber Calculation Formula",
                source_url="https://gdce.gov.kh/tariff-search",
                section_title="Calculator Formula Registry"
            ),
        ]
        
        return {
            "total": total_payable,
            "currency": "KHR",
            "exchange_rate_usd_to_khr": exchange_rate_khr,
            "cif_value_usd": cif_value_usd,
            "breakdown": {
                "cif_value": cif_value_khr,
                "etr_amount": etr_amount,
                "fees": Decimal('0')
            },
            "line_items": line_items,
            "assumptions": assumptions,
            "references": references
        }
    
    def _calculate_fta_dv_case(
        self,
        request: CalculationRequest,
        cif_value_khr: Decimal,
        rates: Dict[str, Decimal],
        exchange_rate_khr: Decimal
    ) -> Dict[str, Any]:
        """
        Calculate using FTA/DV case.

        ASYCUDA behavior:
        - Original Amounts use normal/MFN rates for cumulative base build-up.
        - Payable/Display amounts use preferential FTA rates.
        - Even when COP payable is 0%, the Original COP still feeds into SOP/VOP base.

        Args:
            request: Calculation request
            cif_value_khr: CIF value already converted to KHR
            rates: Duty rates (as decimals) — includes both preferential and normal rates
            exchange_rate_khr: Exchange rate to KHR (already applied to CIF)
        """

        fta_cert = request.flags.get("fta_certificate_type", "Unknown") if request.flags else "Unknown"

        cif_value_usd = Decimal(str(request.customs_value))
        # When exemption/FTA applies and DV > 0, DV is the COP rate, not a valuation.
        # Customs basis remains CIF in that case.
        if request.declared_value is not None and request.declared_value > 0:
            customs_basis_khr = cif_value_khr
            dv_source = "CIF (DV used as COP rate)"
        else:
            customs_basis_khr, dv_source = self._get_declared_value_khr(request, cif_value_khr, exchange_rate_khr)

        # Normal rates for Original Amount (cumulative base)
        cd_rate_normal = rates.get("cd_rate_normal", rates["cd_rate"])
        st_rate_normal = rates.get("st_rate_normal", rates["st_rate"])
        vat_rate_normal = rates.get("vat_rate_normal", rates["vat_rate"])

        # Step 2: Original COP (uses normal rate for base build-up)
        original_cop_amount = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(customs_basis_khr * cd_rate_normal)
        )
        # Payable COP (uses preferential FTA rate)
        payable_cop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(customs_basis_khr * rates["cd_rate"])
        )

        # Step 4: SOP base = Customs Value + Original COP Amount
        st_base = customs_basis_khr + original_cop_amount
        # Original SOP (normal rate) for next base
        original_sop_amount = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(st_base * st_rate_normal)
        )
        # Payable SOP (preferential rate)
        payable_sop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(st_base * rates["st_rate"])
        )

        # Step 5: VOP base = Customs Value + Original COP + Original SOP
        vat_base = customs_basis_khr + original_cop_amount + original_sop_amount
        # Original VOP (normal rate) — same as payable when VAT is not reduced
        original_vop_amount = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(vat_base * vat_rate_normal)
        )
        payable_vop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(vat_base * rates["vat_rate"])
        )

        # Step 9: Total = sum of payable amounts + VVF
        vvf = self._calculate_vvf(request)
        total_before_rounding = payable_cop + payable_sop + payable_vop + vvf
        total_payable = formulas.round_up_to_hundred(total_before_rounding)

        # Build line items
        line_items = [
            TaxLineItem(
                "COP (Customs of Payment - FTA)", "CD",
                payable_cop, "KHR",
                customs_basis_khr,
                rates["cd_rate"] * Decimal('100')
            ),
            TaxLineItem(
                "SOP (Special of Payment - FTA)", "ST",
                payable_sop, "KHR", st_base, rates["st_rate"] * Decimal('100')
            ),
            TaxLineItem(
                "VOP (VAT of Payment - FTA)", "VAT",
                payable_vop, "KHR", vat_base, rates["vat_rate"] * Decimal('100')
            ),
        ]
        if vvf > 0:
            line_items.append(
                TaxLineItem(
                    "Vehicle Valuation Fee (VVF)", "VVF",
                    vvf, "KHR",
                    request.quantity or Decimal("1"),
                    Decimal("60000")
                )
            )

        assumptions = [
            f"HS Code: {request.hs_code}",
            f"Product: {request.goods.get('description', 'N/A')}",
            f"Origin country: {request.origin_country or 'N/A'}",
            f"FTA Certificate: {fta_cert}",
            f"DV basis: {float(customs_basis_khr):,.2f} KHR ({dv_source})",
            "",
            "=== APPLICABLE RATES (FTA) ===",
            f"Customs Duty (CD) preferential rate: {float(rates['cd_rate'] * 100):.2f}%",
            f"Customs Duty (CD) normal rate: {float(cd_rate_normal * 100):.2f}%",
            f"Special Tax (ST) preferential rate: {float(rates['st_rate'] * 100):.2f}%",
            f"Special Tax (ST) normal rate: {float(st_rate_normal * 100):.2f}%",
            f"VAT rate: {float(rates['vat_rate'] * 100):.2f}%",
            f"Exchange rate: 1 USD = {float(exchange_rate_khr):,.2f} KHR",
            "Source: duty_rates.csv (FTA rates)"
        ]

        references = [
            TaxReference(
                doc_id=f"gdce_calculator.duty_rates:{request.hs_code}",
                title=f"HS Code {request.hs_code} - FTA Preferential Rates ({fta_cert})",
                effective_start_date=request.calculation_date,
                source_url="https://gdce.gov.kh/tariff-search",
                section_title="Official Tariff Website"
            ),
            TaxReference(
                doc_id="gdce_calculator.exchange_rates:USD",
                title="Exchange Rate USD to KHR",
                effective_start_date=request.calculation_date,
                source_url="https://nbc.gov.kh/",
                section_title="National Bank of Cambodia"
            ),
            TaxReference(
                doc_id=f"fta_rates:{fta_cert}",
                title=f"{fta_cert} - Preferential Rates",
                source_url="https://gdce.gov.kh/tariff-search",
                section_title="FTA Certificate Registry"
            ),
        ]

        return {
            "total": total_payable,
            "currency": "KHR",
            "exchange_rate_usd_to_khr": exchange_rate_khr,
            "cif_value_usd": cif_value_usd,
            "breakdown": {
                "cif_value": cif_value_khr,
                "customs_basis": customs_basis_khr,
                "cop_amount": payable_cop,
                "original_cop_amount": original_cop_amount,
                "sop_amount": payable_sop,
                "original_sop_amount": original_sop_amount,
                "vop_amount": payable_vop,
                "original_vop_amount": original_vop_amount,
                "vvf_amount": vvf,
                "fees": vvf,
            },
            "line_items": line_items,
            "assumptions": assumptions,
            "references": references
        }

    def _calculate_fta_dv_dq_case(
        self,
        request: CalculationRequest,
        cif_value_khr: Decimal,
        rates: Dict[str, Decimal],
        exchange_rate_khr: Decimal
    ) -> Dict[str, Any]:
        """
        Calculate FTA/DV case with DQ Deal/Trade Agreement adjustment.

        Matches the Excel formula behaviour:
        - Original Amounts use normal/MFN rates for cumulative base build-up.
        - Payable/Display amounts use preferential FTA rates.
        - DQ factor applies to ALL taxes (COP, SOP, VOP).
        - BUR (Build-Up Rebate / DQ portion) is calculated from Before-DQ amounts.
        """

        fta_cert = request.flags.get("fta_certificate_type", "Unknown") if request.flags else "Unknown"
        cif_value_usd = Decimal(str(request.customs_value))
        # When exemption/FTA applies and DV > 0, DV is the COP rate, not a valuation.
        # Customs basis remains CIF in that case.
        if request.declared_value is not None and request.declared_value > 0:
            customs_basis_khr = cif_value_khr
            dv_source = "CIF (DV used as COP rate)"
        else:
            customs_basis_khr, dv_source = self._get_declared_value_khr(request, cif_value_khr, exchange_rate_khr)
        dq_factor = request.dq_factor

        # Normal rates for Original Amount (cumulative base)
        cd_rate_normal = rates.get("cd_rate_normal", rates["cd_rate"])
        st_rate_normal = rates.get("st_rate_normal", rates["st_rate"])
        vat_rate_normal = rates.get("vat_rate_normal", rates["vat_rate"])

        # ---------- COP ----------
        # Original COP (normal/MFN rate) — feeds cumulative base for SOP/VOP
        original_cop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(customs_basis_khr * cd_rate_normal)
        )
        # Before-DQ COP (preferential/DV rate) — used for BUR calculation
        before_dq_cop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(customs_basis_khr * rates["cd_rate"])
        )
        # System/Display COP = Before-DQ COP with DQ discount applied
        # (ASYCUDA shows preferential rate; amount = before_dq × (1-DQ))
        payable_cop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(before_dq_cop * (Decimal("1") - dq_factor))
        )

        # ---------- SOP ----------
        # SOP base uses Original COP for cumulative build-up (per Excel)
        sop_base = customs_basis_khr + original_cop
        # Original SOP (normal/MFN rate)
        original_sop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(sop_base * st_rate_normal)
        )
        # Before-DQ SOP (preferential/DV rate)
        before_dq_sop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(sop_base * rates["st_rate"])
        )
        # System/Display SOP = Before-DQ SOP with DQ discount applied
        payable_sop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(before_dq_sop * (Decimal("1") - dq_factor))
        )

        # ---------- VOP ----------
        # VOP base uses Original COP + Original SOP (per Excel)
        vat_base = customs_basis_khr + original_cop + original_sop
        # Original VOP (normal/MFN rate)
        original_vop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(vat_base * vat_rate_normal)
        )
        # Before-DQ VOP (preferential/DV rate)
        before_dq_vop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(vat_base * rates["vat_rate"])
        )
        # System/Display VOP = Before-DQ VOP with DQ discount applied
        payable_vop = formulas.round_up_to_hundred(
            formulas.round_to_whole_number(before_dq_vop * (Decimal("1") - dq_factor))
        )

        # ---------- BUR ----------
        # BUR = SUM(Before-DQ amounts) * DQ discount percentage
        before_dq_total = before_dq_cop + before_dq_sop + before_dq_vop
        bur = formulas.round_to_whole_number(before_dq_total * dq_factor)

        # ---------- VVF (Vehicle Valuation Fee) ----------
        vvf = self._calculate_vvf(request)

        # Total = sum of payable amounts + VVF
        total_payable = payable_cop + payable_sop + payable_vop + vvf

        line_items = [
            TaxLineItem(
                "COP (Customs of Payment - FTA/DQ)", "CD",
                payable_cop, "KHR",
                customs_basis_khr,
                rates["cd_rate"] * Decimal("100")
            ),
            TaxLineItem(
                "SOP (Special of Payment - FTA/DQ)", "ST",
                payable_sop, "KHR", sop_base,
                rates["st_rate"] * Decimal("100")
            ),
            TaxLineItem(
                "VOP (VAT of Payment - FTA/DQ)", "VAT",
                payable_vop, "KHR", vat_base, rates["vat_rate"] * Decimal("100")
            ),
            TaxLineItem(
                "BUR (Build-Up Rebate / DQ Portion)", "BUR",
                bur, "KHR", Decimal('0'),
                Decimal("0")
            ),
        ]
        if vvf > 0:
            line_items.append(
                TaxLineItem(
                    "Vehicle Valuation Fee (VVF)", "VVF",
                    vvf, "KHR",
                    request.quantity or Decimal("1"),
                    Decimal("60000")
                )
            )

        assumptions = [
            f"HS Code: {request.hs_code}",
            f"Product: {request.goods.get('description', 'N/A')}",
            f"Origin country: {request.origin_country or 'N/A'}",
            f"FTA Certificate: {fta_cert}",
            f"DV basis: {float(customs_basis_khr):,.2f} KHR ({dv_source})",
            "",
            "=== APPLICABLE RATES (FTA/DV/DQ) ===",
            f"Customs Duty (CD) preferential rate: {float(rates['cd_rate'] * 100):.2f}%",
            f"Customs Duty (CD) normal rate: {float(cd_rate_normal * 100):.2f}%",
            f"Special Tax (ST) preferential rate: {float(rates['st_rate'] * 100):.2f}%",
            f"Special Tax (ST) normal rate: {float(st_rate_normal * 100):.2f}%",
            f"VAT rate: {float(rates['vat_rate'] * 100):.2f}%",
            f"Exchange rate: 1 USD = {float(exchange_rate_khr):,.2f} KHR",
            "Source: duty_rates.csv (FTA rates)"
        ]
        assumptions.extend(self._dq_assumptions(request))

        references = [
            TaxReference(
                doc_id=f"gdce_calculator.duty_rates:{request.hs_code}",
                title=f"HS Code {request.hs_code} - FTA/DQ Rates ({fta_cert})",
                effective_start_date=request.calculation_date,
                source_url="https://gdce.gov.kh/tariff-search",
                section_title="Official Tariff Website"
            ),
            TaxReference(
                doc_id="gdce_calculator.exchange_rates:USD",
                title="Exchange Rate USD to KHR",
                effective_start_date=request.calculation_date,
                source_url="https://nbc.gov.kh/",
                section_title="National Bank of Cambodia"
            ),
            TaxReference(
                doc_id=f"fta_rates:{fta_cert}:dq",
                title=f"{fta_cert} - Preferential Rates with DQ",
                source_url="https://gdce.gov.kh/tariff-search",
                section_title="FTA/DQ Certificate Registry"
            ),
        ]

        return {
            "total": total_payable,
            "currency": "KHR",
            "exchange_rate_usd_to_khr": exchange_rate_khr,
            "cif_value_usd": cif_value_usd,
            "breakdown": {
                "cif_value": cif_value_khr,
                "customs_basis": customs_basis_khr,
                "cop_amount": payable_cop,
                "original_cop_amount": original_cop,
                "before_dq_cop": before_dq_cop,
                "sop_amount": payable_sop,
                "original_sop_amount": original_sop,
                "before_dq_sop": before_dq_sop,
                "vop_amount": payable_vop,
                "original_vop_amount": original_vop,
                "before_dq_vop": before_dq_vop,
                "bur_amount": bur,
                "dq_factor": dq_factor,
                "vvf_amount": vvf,
                "fees": vvf,
                "cd_rate_normal": float(cd_rate_normal * Decimal("100")),
                "st_rate_normal": float(st_rate_normal * Decimal("100")),
                "vat_rate_normal": float(vat_rate_normal * Decimal("100")),
            },
            "line_items": line_items,
            "assumptions": assumptions,
            "references": references
        }


# ================================================================
# CONVENIENCE FUNCTIONS
# ================================================================

def calculate_import_taxes(
    request_data: Dict[str, Any],
    db: DatabaseInterface
) -> Dict[str, Any]:
    """
    Convenience function to calculate import taxes.
    
    Args:
        request_data: Request data matching CalculateImportTaxesRequest schema
        db: Database interface instance
        
    Returns:
        Calculation result as dict
    """
    # Parse request
    request = CalculationRequest(
        calculation_date=request_data["calculation_date"],
        regime=request_data["regime"],
        goods=request_data["goods"],
        valuation=request_data["valuation"],
        flags=request_data.get("flags"),
        requested_breakdown=request_data.get("requested_breakdown")
    )
    
    # Calculate
    calculator = ImportTaxCalculator(db)
    result = calculator.calculate(request)
    
    return result.to_dict()
