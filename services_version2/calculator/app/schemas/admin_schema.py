"""
GDCE Calculator Service - Admin API Schemas
=============================================
Pydantic models for the admin CRUD endpoints.

Version: 1.0
Created: 2026-05-04
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# FORMULA SCHEMAS
# ------------------------------------------------------------------

class FormulaCreate(BaseModel):
    """Schema for creating/updating a formula."""
    formula_id: str = Field(..., description="Unique formula identifier (e.g. COP_001)")
    formula_name: str = Field(..., description="Human-readable name")
    formula_type: str = Field(..., description="Type: duty, vat, total, cif, etc.")
    expression: str = Field(..., description="Safe arithmetic expression")
    description: str = ""
    variables: List[str] = Field(default_factory=list, description="Required variable names")
    effective_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "formula_id": "COP_001",
                "formula_name": "Customs of Payment",
                "formula_type": "duty",
                "expression": "customs_value * duty_rate",
                "variables": ["customs_value", "duty_rate"],
            }
        }


class FormulaResponse(BaseModel):
    formula_id: str
    formula_name: str
    formula_type: str
    expression: str
    description: str = ""
    variables: List[str] = []
    version: int = 1
    effective_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: bool = True


# ------------------------------------------------------------------
# ROUNDING RULE SCHEMAS
# ------------------------------------------------------------------

class RoundingRuleCreate(BaseModel):
    rule_id: str
    rule_name: str
    applies_to: List[str] = Field(..., description="Field names this rule applies to")
    rounding_method: str = Field(..., description="CEILING_100, ROUND_WHOLE, or NONE")
    precision: int = 100
    priority: str = "HIGH"
    description: str = ""
    is_active: bool = True


class RoundingRuleResponse(BaseModel):
    rule_id: str
    rule_name: str
    applies_to: List[str]
    rounding_method: str
    precision: int = 100
    priority: str = "HIGH"
    description: str = ""


# ------------------------------------------------------------------
# POLICY SCHEMAS
# ------------------------------------------------------------------

class PolicyCreate(BaseModel):
    policy_id: str
    policy_name: str
    policy_type: str = Field(..., description="duty, vat, exemption, fta, dv, dq")
    conditions: Dict[str, Any] = Field(default_factory=dict)
    actions: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    description: str = ""
    is_active: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "policy_id": "POL_VAT_RATE",
                "policy_name": "Standard VAT Rate",
                "policy_type": "vat",
                "conditions": {},
                "actions": {"set_rate": {"vat_rate": 0.10}},
                "priority": 100,
            }
        }


class PolicyResponse(BaseModel):
    policy_id: str
    policy_name: str
    policy_type: str
    conditions: Dict[str, Any] = {}
    actions: Any = {}
    priority: int = 100
    description: str = ""
    is_active: bool = True


# ------------------------------------------------------------------
# EXEMPTION SCHEMAS
# ------------------------------------------------------------------

class ExemptionCreate(BaseModel):
    exemption_code: str
    regime_name: str
    exemption_type: str = Field(..., description="full, partial_cd, partial_vat, conditional")
    cd_exempt: bool = False
    st_exempt: bool = False
    vat_exempt: bool = False
    et_exempt: bool = False
    cd_reduction_pct: float = 0.0
    vat_reduction_pct: float = 0.0
    conditions: str = ""
    is_active: bool = True


class ExemptionResponse(BaseModel):
    exemption_code: str
    regime_name: str
    exemption_type: str
    cd_exempt: bool = False
    st_exempt: bool = False
    vat_exempt: bool = False
    et_exempt: bool = False
    cd_reduction_pct: float = 0.0
    vat_reduction_pct: float = 0.0
    conditions: str = ""
    is_active: bool = True


# ------------------------------------------------------------------
# CACHE / PREVIEW SCHEMAS
# ------------------------------------------------------------------

class CacheRefreshResponse(BaseModel):
    status: str = "ok"
    message: str = "Cache refreshed"


class RulesPreviewRequest(BaseModel):
    hs_code: str
    origin_country: str = "XX"
    agreement_code: Optional[str] = None
    exemption_code: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "hs_code": "22041000",
                "origin_country": "TH",
                "agreement_code": "ATIGA",
            }
        }


class AuditLogResponse(BaseModel):
    id: int
    table_name: str
    record_id: str
    action: str
    old_value: Optional[Dict[str, Any]] = None
    new_value: Dict[str, Any] = {}
    changed_by: str = ""
    changed_at: Optional[str] = None
    reason: str = ""
