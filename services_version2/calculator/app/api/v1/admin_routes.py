"""
GDCE Calculator Service - Admin API Endpoints
===============================================
REST endpoints for managing dynamic rules without code changes.
Protected by API key authentication.

Endpoints:
  /admin/formulas         — CRUD for calculation formulas
  /admin/rounding-rules   — CRUD for rounding rules
  /admin/policies         — CRUD for business policies
  /admin/exemptions       — CRUD for exemption regimes
  /admin/cache/refresh    — Force cache refresh
  /admin/rules/preview    — Preview applicable rules for a scenario
  /admin/audit-log        — View audit trail

Version: 1.0
Created: 2026-05-04
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException

from ...schemas.admin_schema import (
    CacheRefreshResponse,
    ExemptionCreate,
    ExemptionResponse,
    FormulaCreate,
    FormulaResponse,
    PolicyCreate,
    PolicyResponse,
    RoundingRuleCreate,
    RoundingRuleResponse,
    RulesPreviewRequest,
)

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["Admin"])

# ------------------------------------------------------------------
# Singleton holders (set during app startup)
# ------------------------------------------------------------------
_rules_db = None
_rules_provider = None
_formula_engine = None


def init_admin(rules_db, rules_provider, formula_engine=None):
    """Initialize admin module with dependencies. Called from app.py startup."""
    global _rules_db, _rules_provider, _formula_engine
    _rules_db = rules_db
    _rules_provider = rules_provider
    _formula_engine = formula_engine


# ------------------------------------------------------------------
# API KEY AUTH
# ------------------------------------------------------------------

def verify_admin_key(x_admin_key: str = Header(None, alias="X-Admin-Key")):
    """Verify the admin API key from request header."""
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected:
        # No key configured — allow access (dev mode)
        logger.warning("  ADMIN_API_KEY not set — admin endpoints are unprotected!")
        return True
    if x_admin_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing admin API key")
    return True


def get_rules_db():
    if _rules_db is None:
        raise HTTPException(status_code=503, detail="Rules database not available")
    return _rules_db


def get_rules_provider():
    if _rules_provider is None:
        raise HTTPException(status_code=503, detail="Rules provider not initialized")
    return _rules_provider


# ==================================================================
# FORMULA ENDPOINTS
# ==================================================================

@admin_router.get("/formulas", response_model=List[FormulaResponse], summary="List all formulas")
async def list_formulas(
    _auth=Depends(verify_admin_key),
    provider=Depends(get_rules_provider),
) -> List[Dict[str, Any]]:
    return [f.to_dict() for f in provider.get_all_formulas()]


@admin_router.get("/formulas/{formula_id}", response_model=FormulaResponse, summary="Get formula")
async def get_formula(
    formula_id: str,
    _auth=Depends(verify_admin_key),
    provider=Depends(get_rules_provider),
) -> Dict[str, Any]:
    f = provider.get_formula(formula_id)
    if not f:
        raise HTTPException(404, f"Formula '{formula_id}' not found")
    return f.to_dict()


@admin_router.post("/formulas", response_model=FormulaResponse, summary="Create/update formula")
async def upsert_formula(
    body: FormulaCreate,
    _auth=Depends(verify_admin_key),
    db=Depends(get_rules_db),
    provider=Depends(get_rules_provider),
) -> Dict[str, Any]:
    # Validate expression safety
    if _formula_engine:
        try:
            _formula_engine.validate_expression(body.expression)
        except Exception as e:
            raise HTTPException(400, f"Unsafe expression: {e}")

    db.upsert_formula(body.dict())
    provider.refresh_cache()

    f = provider.get_formula(body.formula_id)
    return f.to_dict() if f else body.dict()


@admin_router.put("/formulas/{formula_id}/deactivate", summary="Deactivate formula")
async def deactivate_formula(
    formula_id: str,
    _auth=Depends(verify_admin_key),
    db=Depends(get_rules_db),
    provider=Depends(get_rules_provider),
) -> Dict[str, str]:
    success = db.deactivate_formula(formula_id)
    if not success:
        raise HTTPException(404, f"Formula '{formula_id}' not found")
    provider.refresh_cache()
    return {"status": "deactivated", "formula_id": formula_id}


# ==================================================================
# ROUNDING RULE ENDPOINTS
# ==================================================================

@admin_router.get("/rounding-rules", response_model=List[RoundingRuleResponse], summary="List rounding rules")
async def list_rounding_rules(
    _auth=Depends(verify_admin_key),
    provider=Depends(get_rules_provider),
) -> List[Dict[str, Any]]:
    return [r.to_dict() for r in provider.get_all_rounding_rules()]


@admin_router.post("/rounding-rules", response_model=RoundingRuleResponse, summary="Create/update rounding rule")
async def upsert_rounding_rule(
    body: RoundingRuleCreate,
    _auth=Depends(verify_admin_key),
    db=Depends(get_rules_db),
    provider=Depends(get_rules_provider),
) -> Dict[str, Any]:
    valid_methods = {"CEILING_100", "ROUND_WHOLE", "NONE"}
    if body.rounding_method not in valid_methods:
        raise HTTPException(400, f"Invalid method. Allowed: {valid_methods}")
    db.upsert_rounding_rule(body.dict())
    provider.refresh_cache()
    return body.dict()


# ==================================================================
# POLICY ENDPOINTS
# ==================================================================

@admin_router.get("/policies", response_model=List[PolicyResponse], summary="List policies")
async def list_policies(
    policy_type: str = None,
    _auth=Depends(verify_admin_key),
    provider=Depends(get_rules_provider),
) -> List[Dict[str, Any]]:
    if policy_type:
        policies = provider.get_policies(policy_type)
    else:
        # Get all by collecting all types
        all_policies = []
        for ptype in ["duty", "vat", "exemption", "fta", "dv", "dq", "validation"]:
            all_policies.extend(provider.get_policies(ptype))
        policies = all_policies
    return [p.to_dict() for p in policies]


@admin_router.post("/policies", response_model=PolicyResponse, summary="Create/update policy")
async def upsert_policy(
    body: PolicyCreate,
    _auth=Depends(verify_admin_key),
    db=Depends(get_rules_db),
    provider=Depends(get_rules_provider),
) -> Dict[str, Any]:
    db.upsert_policy(body.dict())
    provider.refresh_cache()
    return body.dict()


# ==================================================================
# EXEMPTION ENDPOINTS
# ==================================================================

@admin_router.get("/exemptions", response_model=List[ExemptionResponse], summary="List exemptions")
async def list_exemptions(
    _auth=Depends(verify_admin_key),
    provider=Depends(get_rules_provider),
) -> List[Dict[str, Any]]:
    return [e.to_dict() for e in provider.get_all_exemptions()]


@admin_router.post("/exemptions", response_model=ExemptionResponse, summary="Create/update exemption")
async def upsert_exemption(
    body: ExemptionCreate,
    _auth=Depends(verify_admin_key),
    db=Depends(get_rules_db),
    provider=Depends(get_rules_provider),
) -> Dict[str, Any]:
    db.upsert_exemption(body.dict())
    provider.refresh_cache()
    return body.dict()


# ==================================================================
# CACHE & PREVIEW
# ==================================================================

@admin_router.post("/cache/refresh", response_model=CacheRefreshResponse, summary="Refresh rules cache")
async def refresh_cache(
    _auth=Depends(verify_admin_key),
    provider=Depends(get_rules_provider),
) -> Dict[str, str]:
    provider.refresh_cache()
    return {"status": "ok", "message": "Rules cache refreshed successfully"}


@admin_router.post("/rules/preview", summary="Preview applicable rules")
async def preview_rules(
    body: RulesPreviewRequest,
    _auth=Depends(verify_admin_key),
    provider=Depends(get_rules_provider),
) -> Dict[str, Any]:
    """Preview what rules, rates, and exemptions would apply for a given HS code."""
    context = {
        "hs_code": body.hs_code,
        "origin_country": body.origin_country,
    }
    if body.agreement_code:
        context["agreement_code"] = body.agreement_code

    # Collect applicable rules
    result: Dict[str, Any] = {"hs_code": body.hs_code, "origin_country": body.origin_country}

    # Exemption
    if body.exemption_code:
        ex = provider.get_exemption(body.exemption_code)
        result["exemption"] = ex.to_dict() if ex else None

    # Matching policies
    for ptype in ["duty", "vat", "fta", "dv", "dq"]:
        matching = provider.get_matching_policies(ptype, context)
        if matching:
            result[f"policies_{ptype}"] = [p.to_dict() for p in matching]

    # Rounding rules
    result["rounding_rules"] = {
        field: provider.get_rounding_rule(field).to_dict()
        for field in ["cop_amount", "sop_amount", "vop_amount", "total_payable"]
    }

    # VAT rate
    result["vat_rate"] = float(provider.get_vat_rate())

    return result


# ==================================================================
# AUDIT LOG
# ==================================================================

@admin_router.get("/audit-log", summary="View rules audit log")
async def get_audit_log(
    table_name: str = None,
    limit: int = 50,
    _auth=Depends(verify_admin_key),
    db=Depends(get_rules_db),
) -> List[Dict[str, Any]]:
    rows = db.get_audit_log(table_name=table_name, limit=limit)
    # Convert datetime objects to strings
    for row in rows:
        if row.get("changed_at"):
            row["changed_at"] = str(row["changed_at"])
    return rows
