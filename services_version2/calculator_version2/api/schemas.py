"""
GDCE Calculator Service - API Schemas
=====================================
Pydantic request/response models for HTTP validation and serialization.
Framework-agnostic domain models live in core.models instead.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Literal, Any

from pydantic import BaseModel, Field, validator

# Import currency handler for unified validation (avoid redundancy)
from ..core.currency_handler import CurrencyHandler

_currency_handler = CurrencyHandler()  # Singleton for validation


class GoodsModel(BaseModel):
    """Goods information."""

    description: str = Field(..., min_length=2, max_length=500)
    hs_code: Optional[str] = Field(
        None, pattern=r"^\d{4}(\d{2})?(\d{2})?$|^\d{4}(\.\d{2})?(\.\d{2})?$",
        description="HS code: 4, 6, or 8 digits with or without dots (e.g., 0102, 010229, 01022911, 0102.29.11)"
    )
    origin_country: Optional[str] = None
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = None
    net_mass_kg: Optional[float] = Field(None, ge=0)
    net_mass_tons: Optional[float] = Field(
        None,
        ge=0,
        description="Weight in metric tons. Internally converted to kg (x1000).",
    )
    volume_liter: Optional[float] = Field(None, ge=0)
    container_type: Optional[str] = None


class ValuationModel(BaseModel):
    """Valuation information."""

    customs_value: float = Field(
        ..., ge=0, description="Numeric amount; display to users with $ prefix when USD (e.g., $40000)."
    )
    currency: Optional[str] = Field(
        None,
        description=(
            "ISO 4217 currency code (e.g., 'USD', 'KHR'), symbol (e.g., '$', '៛'), "
            "or currency name (e.g., 'dollar', 'baht'). "
            "If omitted, inferred from origin_country or defaults to KHR."
        ),
    )
    exchange_rate_to_khr: Optional[float] = Field(None, gt=0)
    declared_value: Optional[float] = Field(
        None,
        ge=0,
        description=(
            "DV override. For mass-based cases such as petroleum and rubber, "
            "use with declared_value_basis='per_ton' when DV is price per metric ton."
        ),
    )
    declared_value_basis: Literal["total", "per_ton"] = Field(
        "total",
        description="How declared_value should be interpreted: total value or price per metric ton.",
    )
    dq_factor: Optional[float] = Field(
        None,
        ge=0,
        description=(
            "User-provided DQ adjustment factor. Applied to SOP/SPP when dq_applicable is true. "
            "No backend registry — user must supply the factor directly."
        ),
    )

    @validator("currency", pre=True, always=True)
    def validate_and_normalize_currency(cls, v):
        """
        Validate and normalize currency using CurrencyHandler.
        
        Supports:
        - ISO codes: "USD", "usd" → normalized to "USD"
        - Symbols: "$", "៛", "HK$", "A$" → converted to ISO codes
        - Currency names: "dollar", "baht", "euro" → converted
        - Symbol+number: "$800", "€5000" → extracts currency
        - Code+number (no space): "usd800", "800usd" → extracts currency
        - None / empty → returns None (endpoint applies fallback chain)
        """
        # Allow None to pass through — endpoint handles the fallback
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        try:
            return _currency_handler.parse_currency_input(str(v))
        except ValueError as e:
            raise ValueError(str(e)) from e


class FlagsModel(BaseModel):
    """Calculation flags."""

    fta_applicable: bool = False
    fta_certificate_type: Optional[str] = None
    duty_quota_applicable: bool = False
    dq_applicable: bool = False
    dq_factor: Optional[float] = Field(
        None,
        ge=0,
        description="User-provided DQ adjustment factor. No backend registry.",
    )
    petroleum_case: bool = False
    rubber_case: bool = False
    qip_exemption: bool = False
    sez_applicable: bool = False
    diplomatic_exemption: bool = False
    ngo_humanitarian: bool = False
    educational_exemption: bool = False
    medical_exemption: bool = False
    passenger_allowance: bool = False
    preferential_cd_rate: Optional[float] = Field(
        None,
        ge=0,
        description="User-provided preferential CD rate override (percentage, e.g., 0 for 0%). Used when the claimed FTA rate is not in the database.",
    )


class CalculateImportTaxesRequest(BaseModel):
    """Request model for supported customs tax calculations."""

    calculation_date: str = Field(
        ..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date is mandatory (YYYY-MM-DD)."
    )
    regime: str
    goods: GoodsModel
    valuation: ValuationModel
    flags: Optional[FlagsModel] = None
    requested_breakdown: Optional[List[str]] = None

    @validator("regime")
    def validate_regime(cls, v):
        allowed = [
            "import",
            "export",
            "transit",
            "temporary_admission",
            "bonded_warehouse",
            "duty_free",
            "qip",
            "sez",
            "diplomatic",
            "ngo_humanitarian",
            "passenger_personal",
            "other",
        ]
        if v not in allowed:
            raise ValueError(f"Regime must be one of {allowed}")
        return v

    class Config:
        schema_extra = {
            "example": {
                "calculation_date": "2026-03-04",
                "regime": "import",
                "goods": {
                    "description": "Live Oxen",
                    "hs_code": None,
                    "origin_country": "Thailand",
                    "quantity": 10,
                    "unit": "head",
                },
                "valuation": {"customs_value": 50000, "currency": "USD"},
                "flags": {"fta_applicable": False},
            },
        }


class TaxLineItemModel(BaseModel):
    """Tax line item in response."""

    name: str
    tax_type: str
    amount: float = Field(..., description="Numeric; display with currency symbol for UI (e.g., $7500).")
    currency: str
    base: Optional[float] = Field(
        None, description="Taxable base; display with currency symbol for UI."
    )
    rate: Optional[float] = None


class TaxReferenceModel(BaseModel):
    """Reference to source document."""

    doc_id: str
    title: str
    effective_start_date: Optional[str] = None
    effective_end_date: Optional[str] = None
    source_url: Optional[str] = None
    section_title: Optional[str] = None


class HSCodeInfoModel(BaseModel):
    """HS code metadata and information."""
    
    hs_code: str = Field(..., description="Normalized HS code (e.g., '0102.10.00')")
    description: Optional[str] = Field(None, description="Product description for the HS code")
    unit: Optional[str] = Field(None, description="Unit of measure (e.g., 'kg', 'head')")
    level: Optional[str] = Field(
        None,
        description="HS code hierarchy level: 'section' (4 digits), 'chapter' (6 digits), or 'subchapter' (8 digits)"
    )


class CalculateImportTaxesResponse(BaseModel):
    """Response model for supported customs tax calculations."""

    calculation_id: str
    currency: str
    total: float = Field(..., description="Grand total; render with currency symbol for display (e.g., $75,250).")
    breakdown: Dict[str, float] = Field(
        ..., description="Keyed amounts; render with currency symbol for display."
    )
    line_items: List[TaxLineItemModel]
    assumptions: List[str]
    references: List[TaxReferenceModel]
    exchange_rate_usd_to_khr: Optional[float] = None
    cif_value_usd: Optional[float] = None
    currency_note: Optional[str] = Field(
        None,
        description="Human-readable note about currency conversion (e.g., 'Input was in USD, converted to KHR at rate...')"
    )
    hs_code_info: Optional[HSCodeInfoModel] = Field(
        None,
        description="HS code metadata including description, unit, and hierarchical level"
    )
    preferential_rate_missing: Optional[bool] = Field(
        None,
        description="True when an FTA/exemption was claimed but no preferential rate was provided by the user (DV or preferential_cd_rate)."
    )
    requested_agreement: Optional[str] = Field(
        None,
        description="The FTA agreement code or exemption type that was requested but needs a user-provided rate (e.g., ACFTA, QIP)."
    )

    class Config:
        schema_extra = {
            "example": {
                "calculation_id": "calc_2026-03-04_001234",
                "currency": "KHR",
                "total": 75250.00,
                "breakdown": {
                    "cif_value": 50000.00,
                    "customs_duty": 7500.00,
                    "special_tax": 0.00,
                    "vat": 5750.00,
                    "fees": 0.00,
                },
                "line_items": [
                    {
                        "name": "Customs Duty (CD)",
                        "tax_type": "CD",
                        "amount": 7500.00,
                        "currency": "KHR",
                        "base": 50000.00,
                        "rate": 15.0,
                    },
                    {
                        "name": "Value Added Tax (VAT)",
                        "tax_type": "VAT",
                        "amount": 5750.00,
                        "currency": "KHR",
                        "base": 57500.00,
                        "rate": 10.0,
                    },
                ],
                "assumptions": [
                    "HS Code: 0102.10.00",
                    "Origin: Thailand",
                    "Customs Duty: 15% applied",
                    "VAT: 10% applied",
                ],
                "references": [
                    {
                        "doc_id": "duty_rates.csv:hs_0102.10.00",
                        "title": "HS Code 0102.10.00 - Duty Rates",
                        "effective_start_date": "2026-01-01",
                    }
                ],
                "exchange_rate_usd_to_khr": 4022.0,
                "cif_value_usd": 50000.0,
            }
        }


class QueryRequest(BaseModel):
    """
    POST /query request body.
    Supports a natural language question or structured parameter overrides.

    GUIDE FOR CASES:
    ----------------
    1. **Normal Case**: Standard calculations with standard CIF values and origin countries.
       -> Recommended fields: `question` OR (`hs_code`, `cif_value`, `currency`, `origin_country`)

    2. **FTA DV Case**: FTA certificate with custom Declared Value (DV) limit.
       -> Recommended fields: `fta_applicable` (true), `fta_certificate_type` (e.g. 'ACFTA'), `declared_value` (e.g. 0.0), `hs_code`, `cif_value`, `origin_country`

    3. **FTA DV DQ Case**: FTA + Declared Value (DV) + Duty Quota (DQ) ratio.
       -> Recommended fields: `fta_applicable` (true), `fta_certificate_type`, `declared_value`, `dq_applicable` (true), `dq_factor` (e.g. 0.40), `hs_code`, `cif_value`

    4. **Petroleum Case**: Petroleum products requiring net mass (kg), volume (liters), and basis value.
       -> Recommended fields: `petroleum_case` (true), `net_mass`, `volume`, `declared_value` (DV), `hs_code`, `cif_value`, `origin_country`
    """

    # --- Natural Language Query ---
    question: Optional[str] = Field(
        None,
        max_length=5000,
        description="Natural language question to calculate import duties/taxes (e.g. 'calculate import tax for hs code 8703.80.99 cif 40000USD from china').",
    )

    # --- Core Calculation Parameters ---
    hs_code: Optional[str] = Field(
        None,
        description="HS code (e.g., '8703.80.99'). Dotted or raw format. Required for all cases.",
    )
    cif_value: Optional[float] = Field(
        None,
        description="CIF value in the specified currency (e.g., 40000.0). Required for all cases.",
    )
    currency: Optional[str] = Field(
        None,
        description="Currency code (e.g., 'USD', 'KHR'). Defaults to KHR if country is missing.",
    )
    origin_country: Optional[str] = Field(
        None,
        description="Origin country name or code (e.g., 'China', 'Vietnam').",
    )
    quantity: Optional[float] = Field(
        None,
        description="Quantity of goods.",
    )
    unit: Optional[str] = Field(
        None,
        description="Unit of goods (e.g., 'pcs', 'kg', 'liter').",
    )

    # --- FTA / Exemption Parameters ---
    fta_applicable: Optional[bool] = Field(
        None,
        description="Whether FTA (Free Trade Agreement) is applicable. Required for FTA DV & FTA DV DQ cases.",
    )
    fta_certificate_type: Optional[str] = Field(
        None,
        description="FTA certificate type (e.g., 'ACFTA', 'ATIGA'). Required for FTA DV & FTA DV DQ cases.",
    )
    preferential_cd_rate: Optional[float] = Field(
        None,
        description="User-provided preferential CD rate override (percentage, e.g., 0 for 0%).",
    )

    # --- Duty Quota (DQ) Parameters ---
    dq_applicable: Optional[bool] = Field(
        None,
        description="Whether Duty Quota is applicable. Required for FTA DV DQ cases.",
    )
    dq_factor: Optional[float] = Field(
        None,
        description="Duty Quota (DQ) adjustment factor (e.g., 0.40 for 40%). Required for FTA DV DQ cases.",
    )

    # --- Declared Value & Petroleum/Rubber Metrics ---
    declared_value: Optional[float] = Field(
        None,
        description="Declared Value (DV) override / basis value (e.g., 700.0 or 0.0). Required for FTA DV, FTA DV DQ, and Petroleum cases.",
    )
    net_mass: Optional[float] = Field(
        None,
        description="Net mass of the goods in kg. Required for Petroleum and Rubber cases.",
    )
    volume: Optional[float] = Field(
        None,
        description="Volume of the goods in liters. Required for Petroleum cases.",
    )
    petroleum_case: Optional[bool] = Field(
        None,
        description="Explicit override to flag this as a petroleum calculation case. Enables fuel-specific taxes (BUR, VVF). Required for Petroleum case.",
    )
    rubber_case: Optional[bool] = Field(
        None,
        description="Explicit override to flag this as a rubber calculation case.",
    )

    # --- Advanced / System Parameters ---
    exchange_rate_to_khr: Optional[float] = Field(
        None,
        description="Exchange rate override to KHR (e.g. 4100.0).",
    )
    qip_exemption: Optional[bool] = Field(
        None,
        description="Whether QIP exemption is applicable.",
    )
    sez_applicable: Optional[bool] = Field(
        None,
        description="Whether SEZ is applicable.",
    )
    diplomatic_exemption: Optional[bool] = Field(
        None,
        description="Whether diplomatic exemption is applicable.",
    )
    ngo_humanitarian: Optional[bool] = Field(
        None,
        description="Whether NGO/Humanitarian exemption is applicable.",
    )
    educational_exemption: Optional[bool] = Field(
        None,
        description="Whether educational exemption is applicable.",
    )
    medical_exemption: Optional[bool] = Field(
        None,
        description="Whether medical exemption is applicable.",
    )
    passenger_allowance: Optional[bool] = Field(
        None,
        description="Whether passenger allowance is applicable.",
    )
    regime: Optional[str] = Field(
        None,
        description="Customs regime type (e.g., 'import', 'export'). Defaults to 'import'.",
    )
    calculation_date: Optional[str] = Field(
        None,
        description="Calculation date (YYYY-MM-DD). Defaults to today.",
    )
    extracted_params: Optional[Dict[str, Any]] = Field(
        None,
        description="Advanced: pre-extracted parameters dictionary from LLM/orchestrator.",
    )

    class Config:
        schema_extra = {
            "examples": {
                "Normal": {
                    "summary": "Normal Calculation Example",
                    "description": "Standard import tax calculation using HS code and CIF value.",
                    "value": {
                        "question": "calculate import tax for hs code 8703.80.99 cif 40000USD from china",
                        "hs_code": "8703.80.99",
                        "cif_value": 40000.0,
                        "currency": "USD",
                        "origin_country": "China"
                    }
                },
                "FTA_DV": {
                    "summary": "FTA with Declared Value (DV) Example",
                    "description": "Import tax calculation under an FTA (ACFTA) with a Declared Value override.",
                    "value": {
                        "question": "calculate import tax for hs code 8703.22.59 cif 10500USD dv = 0.00 ACFTA from china",
                        "hs_code": "8703.22.59",
                        "cif_value": 10500.0,
                        "currency": "USD",
                        "origin_country": "China",
                        "fta_applicable": True,
                        "fta_certificate_type": "ACFTA",
                        "declared_value": 0.0
                    }
                },
                "FTA_DV_DQ": {
                    "summary": "FTA with Declared Value & Duty Quota (DQ) Example",
                    "description": "Import tax calculation combining FTA, Declared Value, and a Duty Quota adjustment.",
                    "value": {
                        "question": "calculate import tax for hs code 8703.80.99 cif 40000USD DV = 0.00 DQ = 40% ACFTA from china",
                        "hs_code": "8703.80.99",
                        "cif_value": 40000.0,
                        "currency": "USD",
                        "origin_country": "China",
                        "fta_applicable": True,
                        "fta_certificate_type": "ACFTA",
                        "declared_value": 0.0,
                        "dq_applicable": True,
                        "dq_factor": 0.40
                    }
                },
                "Petroleum": {
                    "summary": "Petroleum Calculation Example",
                    "description": "Calculation for petroleum products requiring net mass (kg), volume (L), and Declared Value.",
                    "value": {
                        "question": "calculate import tax for hs code 2710.12.26 cif 393684.59USD DV = 700 net mass 505423kg 675789L from vietnam",
                        "hs_code": "2710.12.26",
                        "cif_value": 393684.59,
                        "currency": "USD",
                        "origin_country": "Vietnam",
                        "declared_value": 700.0,
                        "net_mass": 505423.0,
                        "volume": 675789.0,
                        "petroleum_case": True
                    }
                }
            }
        }


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str
    detail: Optional[str] = None
    error_code: Optional[str] = None


__all__ = [
    "GoodsModel",
    "ValuationModel",
    "FlagsModel",
    "CalculateImportTaxesRequest",
    "CalculateImportTaxesResponse",
    "TaxLineItemModel",
    "TaxReferenceModel",
    "HSCodeInfoModel",
    "QueryRequest",
    "ErrorResponse",
]
