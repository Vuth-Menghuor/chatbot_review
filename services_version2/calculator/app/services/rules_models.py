"""
GDCE Calculator Service - Dynamic Rules Models
================================================
Framework-agnostic data classes for the rules engine.

Version: 1.0
Created: 2026-05-04
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

__all__ = [
    "FormulaDefinition",
    "RoundingRule",
    "PolicyRule",
    "PolicyAction",
    "ExemptionRule",
]


@dataclass
class FormulaDefinition:
    """A calculation formula stored in the database."""

    formula_id: str
    formula_name: str
    formula_type: str
    expression: str
    description: str = ""
    variables: List[str] = field(default_factory=list)
    rounding_method: str = "CEILING_100"
    version: int = 1
    effective_date: Optional[str] = None
    end_date: Optional[str] = None
    is_active: bool = True

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "FormulaDefinition":
        variables = row.get("variables") or []
        if isinstance(variables, str):
            import json
            variables = json.loads(variables)
        if isinstance(variables, dict):
            variables = variables.get("required", list(variables.keys()))
        return cls(
            formula_id=row["formula_id"],
            formula_name=row["formula_name"],
            formula_type=row["formula_type"],
            expression=row["expression"],
            description=row.get("description", ""),
            variables=variables,
            version=row.get("version", 1),
            effective_date=str(row["effective_date"]) if row.get("effective_date") else None,
            end_date=str(row["end_date"]) if row.get("end_date") else None,
            is_active=row.get("is_active", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "formula_id": self.formula_id, "formula_name": self.formula_name,
            "formula_type": self.formula_type, "expression": self.expression,
            "description": self.description, "variables": self.variables,
            "rounding_method": self.rounding_method, "version": self.version,
            "effective_date": self.effective_date, "end_date": self.end_date,
            "is_active": self.is_active,
        }


@dataclass
class RoundingRule:
    """A rounding rule: CEILING_100, ROUND_WHOLE, or NONE."""

    rule_id: str
    rule_name: str
    applies_to: List[str]
    rounding_method: str
    precision: int = 100
    priority: str = "HIGH"
    description: str = ""

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "RoundingRule":
        applies_to = row.get("applies_to", [])
        if isinstance(applies_to, str):
            applies_to = [s.strip() for s in applies_to.split(",")]
        return cls(
            rule_id=row["rule_id"], rule_name=row["rule_name"],
            applies_to=applies_to, rounding_method=row["rounding_method"],
            precision=row.get("precision", 100), priority=row.get("priority", "HIGH"),
            description=row.get("description", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id, "rule_name": self.rule_name,
            "applies_to": self.applies_to, "rounding_method": self.rounding_method,
            "precision": self.precision, "priority": self.priority,
            "description": self.description,
        }


@dataclass
class PolicyAction:
    """An action when a policy's conditions are met."""
    action_type: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"action_type": self.action_type, "parameters": self.parameters}


@dataclass
class PolicyRule:
    """A business rule that conditionally modifies calculation behavior."""

    policy_id: str
    policy_name: str
    policy_type: str
    conditions: Dict[str, Any] = field(default_factory=dict)
    actions: List[PolicyAction] = field(default_factory=list)
    priority: int = 100
    description: str = ""
    is_active: bool = True

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "PolicyRule":
        conditions = row.get("conditions", {})
        raw_actions = row.get("actions", {})
        actions: List[PolicyAction] = []
        if isinstance(raw_actions, dict):
            for atype, params in raw_actions.items():
                p = params if isinstance(params, dict) else {"value": params}
                actions.append(PolicyAction(action_type=atype, parameters=p))
        elif isinstance(raw_actions, list):
            for item in raw_actions:
                actions.append(PolicyAction(
                    action_type=item.get("action_type", "unknown"),
                    parameters=item.get("parameters", {}),
                ))
        return cls(
            policy_id=row["policy_id"], policy_name=row["policy_name"],
            policy_type=row["policy_type"], conditions=conditions,
            actions=actions, priority=row.get("priority", 100),
            description=row.get("description", ""),
            is_active=row.get("is_active", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id, "policy_name": self.policy_name,
            "policy_type": self.policy_type, "conditions": self.conditions,
            "actions": [a.to_dict() for a in self.actions],
            "priority": self.priority, "description": self.description,
            "is_active": self.is_active,
        }


@dataclass
class ExemptionRule:
    """An exemption regime (DIP, QIP, NGO, etc.)."""

    exemption_code: str
    regime_name: str
    exemption_type: str
    cd_exempt: bool = False
    st_exempt: bool = False
    vat_exempt: bool = False
    et_exempt: bool = False
    cd_reduction_pct: Decimal = Decimal("0")
    vat_reduction_pct: Decimal = Decimal("0")
    conditions: str = ""
    is_active: bool = True

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "ExemptionRule":
        return cls(
            exemption_code=row["exemption_code"], regime_name=row["regime_name"],
            exemption_type=row["exemption_type"],
            cd_exempt=row.get("cd_exempt", False), st_exempt=row.get("st_exempt", False),
            vat_exempt=row.get("vat_exempt", False), et_exempt=row.get("et_exempt", False),
            cd_reduction_pct=Decimal(str(row.get("cd_reduction_pct", 0))),
            vat_reduction_pct=Decimal(str(row.get("vat_reduction_pct", 0))),
            conditions=row.get("conditions", ""), is_active=row.get("is_active", True),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "exemption_code": self.exemption_code, "regime_name": self.regime_name,
            "exemption_type": self.exemption_type,
            "cd_exempt": self.cd_exempt, "st_exempt": self.st_exempt,
            "vat_exempt": self.vat_exempt, "et_exempt": self.et_exempt,
            "cd_reduction_pct": float(self.cd_reduction_pct),
            "vat_reduction_pct": float(self.vat_reduction_pct),
            "conditions": self.conditions, "is_active": self.is_active,
        }

