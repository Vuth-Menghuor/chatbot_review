"""
GDCE Calculator Service - Rules Provider
==========================================
Central rules engine that loads calculation rules from:
  1. PostgreSQL database (primary)
  2. JSON config files (fallback)
  3. Hardcoded defaults (last resort)

Features:
  - Cached with configurable TTL (default 5 minutes)
  - Thread-safe cache refresh
  - Versioned rules with effective_date / end_date
  - Graceful degradation — always returns a usable rule

Version: 1.0
Created: 2026-05-04
"""

from __future__ import annotations

import json
import logging
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from .rules_models import (
    ExemptionRule,
    FormulaDefinition,
    PolicyAction,
    PolicyRule,
    RoundingRule,
)

logger = logging.getLogger(__name__)


# ================================================================
# DEFAULT ROUNDING RULES (hardcoded fallback from rounding_rules.json)
# ================================================================
_DEFAULT_ROUNDING = {
    "exchange_rate":        RoundingRule("RULE_001", "Exchange Rate Precision", ["exchange_rate"], "NONE", 1),
    "cif_value_khr":        RoundingRule("RULE_002", "Currency Conversion Result", ["cif_value_khr"], "ROUND_WHOLE", 1),
    "cop_amount":           RoundingRule("RULE_003a", "COP Rounding", ["cop_amount"], "CEILING_100", 100),
    "sop_amount":           RoundingRule("RULE_003b", "SOP Rounding", ["sop_amount"], "CEILING_100", 100),
    "vop_amount":           RoundingRule("RULE_003c", "VOP Rounding", ["vop_amount"], "CEILING_100", 100),
    "total_duties_and_taxes": RoundingRule("RULE_003d", "Total D&T Rounding", ["total_duties_and_taxes"], "CEILING_100", 100),
    "total_payable":        RoundingRule("RULE_004", "Final Payment Rounding", ["total_payable"], "CEILING_100", 100),
}


class RulesProvider:
    """
    Central provider for dynamic calculation rules.
    
    Usage:
        provider = RulesProvider(rules_db=rules_db_adapter)
        formula = provider.get_formula("COP_001")
        rounding = provider.get_rounding_rule("cop_amount")
        vat = provider.get_vat_rate()
    """

    def __init__(
        self,
        rules_db=None,
        config_dir: Optional[Path] = None,
        cache_ttl_seconds: int = 300,
    ):
        """
        Args:
            rules_db: RulesDatabaseAdapter instance (optional)
            config_dir: Path to configs/ directory for JSON fallback
            cache_ttl_seconds: How often to refresh cache (default 5 min)
        """
        self.rules_db = rules_db
        self.config_dir = config_dir or Path(__file__).parent.parent / "configs"
        self.cache_ttl = cache_ttl_seconds

        # Cache storage
        self._formulas: Dict[str, FormulaDefinition] = {}
        self._rounding_rules: Dict[str, RoundingRule] = {}
        self._policies: Dict[str, List[PolicyRule]] = {}  # keyed by policy_type
        self._exemptions: Dict[str, ExemptionRule] = {}

        # Cache management
        self._cache_lock = threading.Lock()
        self._last_refresh: float = 0
        self._db_available = rules_db is not None

        # Initial load
        self.refresh_cache()

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def get_formula(self, formula_id: str) -> Optional[FormulaDefinition]:
        """Get a formula by ID. Returns None if not found."""
        self._maybe_refresh()
        return self._formulas.get(formula_id)

    def get_formulas_by_type(self, formula_type: str) -> List[FormulaDefinition]:
        """Get all formulas of a given type."""
        self._maybe_refresh()
        return [f for f in self._formulas.values() if f.formula_type == formula_type]

    def get_rounding_rule(self, field_name: str) -> RoundingRule:
        """
        Get the rounding rule for a specific field.
        Falls back to hardcoded defaults if not in DB.
        """
        self._maybe_refresh()

        # Check DB-loaded rules first
        if field_name in self._rounding_rules:
            return self._rounding_rules[field_name]

        # Check if any rule's applies_to list contains this field
        for rule in self._rounding_rules.values():
            if field_name in rule.applies_to:
                return rule

        # Fallback to hardcoded defaults
        if field_name in _DEFAULT_ROUNDING:
            return _DEFAULT_ROUNDING[field_name]

        # Ultimate fallback: no rounding
        return RoundingRule("DEFAULT", "No Rounding", [field_name], "NONE", 1)

    def get_policies(self, policy_type: str) -> List[PolicyRule]:
        """Get active policies of a given type, ordered by priority."""
        self._maybe_refresh()
        return self._policies.get(policy_type, [])

    def get_matching_policies(
        self, policy_type: str, context: Dict[str, Any]
    ) -> List[PolicyRule]:
        """
        Get policies whose conditions match the given context.
        
        Context example: {"hs_code": "22041000", "origin_country": "TH"}
        """
        policies = self.get_policies(policy_type)
        matching = []
        for policy in policies:
            if self._conditions_match(policy.conditions, context):
                matching.append(policy)
        return matching

    def get_exemption(self, exemption_code: str) -> Optional[ExemptionRule]:
        """Get an exemption rule by code."""
        self._maybe_refresh()
        return self._exemptions.get(exemption_code)

    def get_all_exemptions(self) -> List[ExemptionRule]:
        """Get all active exemptions."""
        self._maybe_refresh()
        return list(self._exemptions.values())

    def get_vat_rate(self, effective_date: Optional[str] = None) -> Decimal:
        """
        Get the current VAT rate. Checks policies first, then defaults to 0.10.
        """
        self._maybe_refresh()
        # Check if there's a policy overriding VAT
        vat_policies = self.get_policies("vat")
        for policy in vat_policies:
            for action in policy.actions:
                if action.action_type == "set_rate" and "vat_rate" in action.parameters:
                    return Decimal(str(action.parameters["vat_rate"]))
        return Decimal("0.10")  # Default 10% per Law on Taxation 2023

    def get_all_formulas(self) -> List[FormulaDefinition]:
        """Get all loaded formulas."""
        self._maybe_refresh()
        return list(self._formulas.values())

    def get_all_rounding_rules(self) -> List[RoundingRule]:
        """Get all loaded rounding rules."""
        self._maybe_refresh()
        rules = list(self._rounding_rules.values())
        # Include defaults not overridden
        for key, default_rule in _DEFAULT_ROUNDING.items():
            if key not in self._rounding_rules:
                found = False
                for r in self._rounding_rules.values():
                    if key in r.applies_to:
                        found = True
                        break
                if not found:
                    rules.append(default_rule)
        return rules

    def refresh_cache(self) -> None:
        """Force refresh of all cached rules."""
        with self._cache_lock:
            self._load_from_db()
            self._load_from_json_fallback()
            self._last_refresh = time.time()
            logger.debug("Rules cache refreshed")

    # ------------------------------------------------------------------
    # CACHE MANAGEMENT
    # ------------------------------------------------------------------

    def _maybe_refresh(self) -> None:
        """Refresh cache if TTL has elapsed."""
        if time.time() - self._last_refresh > self.cache_ttl:
            self.refresh_cache()

    # ------------------------------------------------------------------
    # DATABASE LOADING
    # ------------------------------------------------------------------

    def _load_from_db(self) -> None:
        """Load rules from PostgreSQL."""
        if not self.rules_db:
            return

        try:
            # Formulas
            rows = self.rules_db.get_active_formulas()
            for row in rows:
                f = FormulaDefinition.from_db_row(row)
                self._formulas[f.formula_id] = f
            logger.debug(f"Loaded {len(rows)} formulas from DB")

            # Rounding rules
            rows = self.rules_db.get_active_rounding_rules()
            for row in rows:
                r = RoundingRule.from_db_row(row)
                # Index by rule_id AND by each field in applies_to
                self._rounding_rules[r.rule_id] = r
                for field in r.applies_to:
                    self._rounding_rules[field] = r
            logger.debug(f"Loaded {len(rows)} rounding rules from DB")

            # Policies
            rows = self.rules_db.get_active_policies()
            self._policies.clear()
            for row in rows:
                p = PolicyRule.from_db_row(row)
                self._policies.setdefault(p.policy_type, []).append(p)
            logger.debug(f"Loaded {sum(len(v) for v in self._policies.values())} policies from DB")

            # Exemptions
            rows = self.rules_db.get_active_exemptions()
            for row in rows:
                e = ExemptionRule.from_db_row(row)
                self._exemptions[e.exemption_code] = e
            logger.debug(f"Loaded {len(rows)} exemptions from DB")

            self._db_available = True
        except Exception as e:
            logger.warning(f"Failed to load rules from DB: {e}")
            self._db_available = False

    # ------------------------------------------------------------------
    # JSON FALLBACK LOADING
    # ------------------------------------------------------------------

    def _load_from_json_fallback(self) -> None:
        """Load rules from JSON config files if not already loaded from DB."""
        # Only load JSON fallback for rules NOT already loaded from DB
        self._load_formulas_from_json()
        self._load_rounding_from_json()

    def _load_formulas_from_json(self) -> None:
        """Load formulas from formula_registry.json."""
        json_path = self.config_dir / "formula_registry.json"
        if not json_path.exists():
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Load from "formulas" section
            for key, formula_data in data.get("formulas", {}).items():
                fid = formula_data.get("formula_id", key)
                if fid not in self._formulas:  # Don't override DB
                    self._formulas[fid] = FormulaDefinition(
                        formula_id=fid,
                        formula_name=formula_data.get("description", key),
                        formula_type=key,
                        expression=formula_data.get("formula", ""),
                        description=formula_data.get("description", ""),
                        variables=[
                            inp["name"] for inp in formula_data.get("inputs", [])
                            if isinstance(inp, dict) and "name" in inp
                        ],
                    )

            # Load from "extended_formulas" section
            for key, formula_data in data.get("extended_formulas", {}).items():
                fid = f"EXT_{key}"
                if fid not in self._formulas:
                    inputs = formula_data.get("inputs", [])
                    if isinstance(inputs, list) and inputs and isinstance(inputs[0], str):
                        variables = inputs
                    else:
                        variables = [
                            inp["name"] for inp in inputs
                            if isinstance(inp, dict) and "name" in inp
                        ]
                    self._formulas[fid] = FormulaDefinition(
                        formula_id=fid,
                        formula_name=formula_data.get("description", key),
                        formula_type=key,
                        expression=formula_data.get("formula", ""),
                        description=formula_data.get("description", ""),
                        variables=variables,
                    )

            logger.debug(f"Loaded {len(self._formulas)} total formulas (DB + JSON fallback)")
        except Exception as e:
            logger.warning(f"Failed to load formulas from JSON: {e}")

    def _load_rounding_from_json(self) -> None:
        """Load rounding rules from rounding_rules.json."""
        json_path = self.config_dir / "rounding_rules.json"
        if not json_path.exists():
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for rule_data in data.get("rounding_rules", []):
                rid = rule_data.get("rule_id")
                if rid and rid not in self._rounding_rules:
                    applies_to = rule_data.get("applies_to", [])

                    # Prefer explicit method field; fall back to parsing rule text for backward compat
                    method = rule_data.get("method", "").upper()
                    if method not in ("CEILING_100", "ROUND_WHOLE", "NONE"):
                        method = "NONE"
                        rule_text = rule_data.get("rule", "")
                        if "nearest 100" in rule_text.lower() or "ceiling" in rule_text.lower():
                            method = "CEILING_100"
                        elif "whole number" in rule_text.lower():
                            method = "ROUND_WHOLE"
                        elif "no rounding" in rule_text.lower() or "do not round" in rule_text.lower():
                            method = "NONE"

                    r = RoundingRule(
                        rule_id=rid,
                        rule_name=rule_data.get("name", rid),
                        applies_to=applies_to,
                        rounding_method=method,
                        precision=100 if method == "CEILING_100" else 1,
                        priority=rule_data.get("priority", "HIGH"),
                        description=rule_data.get("description", ""),
                    )
                    self._rounding_rules[rid] = r
                    for field in applies_to:
                        if field not in self._rounding_rules:
                            self._rounding_rules[field] = r
        except Exception as e:
            logger.warning(f"Failed to load rounding rules from JSON: {e}")

    # ------------------------------------------------------------------
    # POLICY CONDITION MATCHING
    # ------------------------------------------------------------------

    @staticmethod
    def _conditions_match(conditions: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """
        Check if all conditions in a policy match the given context.
        
        Supported condition types:
          - "hs_code": exact match
          - "hs_code_starts_with": prefix match
          - "origin_country": exact match
          - "origin_in": list membership
          - "agreement_code": exact match
          - "flag_set": check if a flag is truthy in context
        """
        for key, expected in conditions.items():
            if key == "hs_code":
                if context.get("hs_code") != expected:
                    return False
            elif key == "hs_code_starts_with":
                hs = context.get("hs_code", "")
                if not hs.replace(".", "").startswith(str(expected).replace(".", "")):
                    return False
            elif key == "origin_country":
                if context.get("origin_country") != expected:
                    return False
            elif key == "origin_in":
                if context.get("origin_country") not in expected:
                    return False
            elif key == "agreement_code":
                if context.get("agreement_code") != expected:
                    return False
            elif key == "flag_set":
                flags = context.get("flags", {})
                if not flags.get(expected):
                    return False
            else:
                # Generic key match
                if context.get(key) != expected:
                    return False
        return True
