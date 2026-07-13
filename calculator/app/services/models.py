"""
GDCE Calculator Service - Core Models
====================================
Domain-level data structures used by the calculator. These are intentionally
framework-agnostic so they can be shared across API layers, batch jobs, and
tests without pulling in FastAPI or Pydantic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

__all__ = [
    "CalculationRequest",
    "CalculationResult",
    "TaxLineItem",
    "TaxReference",
]


@dataclass
class CalculationRequest:
    """Input request for tax calculation."""

    calculation_date: str
    regime: str
    goods: Dict[str, Any]
    valuation: Dict[str, Any]
    flags: Optional[Dict[str, Any]] = field(default_factory=dict)
    requested_breakdown: Optional[List[str]] = field(
        default_factory=lambda: ["duty", "excise", "vat", "fees", "total"]
    )

    @property
    def hs_code(self) -> Optional[str]:
        return self.goods.get("hs_code")

    @property
    def origin_country(self) -> Optional[str]:
        return self.goods.get("origin_country")

    @property
    def customs_value(self) -> Decimal:
        return Decimal(str(self.valuation["customs_value"]))

    @property
    def currency(self) -> str:
        return self.valuation["currency"]

    @property
    def exchange_rate_to_khr(self) -> Optional[Decimal]:
        rate = self.valuation.get("exchange_rate_to_khr")
        return Decimal(str(rate)) if rate is not None else None

    @property
    def declared_value(self) -> Optional[Decimal]:
        value = self.valuation.get("declared_value")
        return Decimal(str(value)) if value is not None else None

    @property
    def declared_value_basis(self) -> str:
        return self.valuation.get("declared_value_basis", "total")

    @property
    def dq_factor(self) -> Decimal:
        value = self.valuation.get("dq_factor")
        if value is None:
            value = self.flags.get("dq_factor") if self.flags else None
        return Decimal(str(value)) if value is not None else Decimal("1")

    @property
    def dq_applicable(self) -> bool:
        if not self.flags:
            return self.dq_factor != Decimal("1")
        return bool(
            self.flags.get("dq_applicable")
            or self.flags.get("duty_quota_applicable")
            or self.dq_factor != Decimal("1")
        )

    @property
    def quantity(self) -> Optional[Decimal]:
        q = self.goods.get("quantity")
        return Decimal(str(q)) if q is not None else None

    @property
    def net_mass_kg(self) -> Optional[Decimal]:
        """Weight in kilograms (raw field). Use net_mass_kg_normalized for calculations."""
        m = self.goods.get("net_mass_kg")
        return Decimal(str(m)) if m is not None else None

    @property
    def preferential_cd_rate(self) -> Optional[Decimal]:
        """User-provided preferential CD rate override (percentage, e.g., 0 for 0%)."""
        if not self.flags:
            return None
        rate = self.flags.get("preferential_cd_rate")
        return Decimal(str(rate)) if rate is not None else None

    @property
    def net_mass_tons(self) -> Optional[Decimal]:
        """Weight in metric tons (raw field). Use net_mass_kg_normalized for calculations."""
        t = self.goods.get("net_mass_tons")
        return Decimal(str(t)) if t is not None else None

    @property
    def net_mass_unit(self) -> str:
        """Unit of weight: 'kg' (default) or 'ton'."""
        return str(self.goods.get("net_mass_unit", "kg")).lower()

    @property
    def net_mass_kg_normalized(self) -> Optional[Decimal]:
        """
        Returns net mass always in kilograms, regardless of how the user provided it.

        Resolution order:
          1. net_mass_tons field → multiply by 1000
          2. net_mass_kg with net_mass_unit='ton' → multiply by 1000
          3. net_mass_kg (default, already in kg)
        """
        # Explicit tons field takes priority
        if self.net_mass_tons is not None:
            return self.net_mass_tons * Decimal("1000")
        # kg field provided but declared as tons
        if self.net_mass_kg is not None and self.net_mass_unit == "ton":
            return self.net_mass_kg * Decimal("1000")
        # Default: already in kg
        return self.net_mass_kg

    @property
    def volume_liter(self) -> Optional[Decimal]:
        v = self.goods.get("volume_liter")
        return Decimal(str(v)) if v is not None else None


@dataclass
class TaxLineItem:
    """Individual tax line item in the calculation."""

    name: str
    tax_type: str
    amount: Decimal
    currency: str
    base: Optional[Decimal] = None
    rate: Optional[Decimal] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "tax_type": self.tax_type,
            "amount": float(self.amount),
            "currency": self.currency,
        }
        if self.base is not None:
            result["base"] = float(self.base)
        if self.rate is not None:
            result["rate"] = float(self.rate)
        return result


@dataclass
class TaxReference:
    """Reference to source document for a rate or rule."""

    doc_id: str
    title: str
    effective_start_date: Optional[str] = None
    effective_end_date: Optional[str] = None
    source_url: Optional[str] = None
    section_title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "doc_id": self.doc_id,
            "title": self.title,
        }
        if self.effective_start_date:
            result["effective_start_date"] = self.effective_start_date
        if self.effective_end_date:
            result["effective_end_date"] = self.effective_end_date
        if self.source_url:
            result["source_url"] = self.source_url
        if self.section_title:
            result["section_title"] = self.section_title
        return result


@dataclass
class CalculationResult:
    """Complete calculation result."""

    calculation_id: str
    currency: str
    total: Decimal
    breakdown: Dict[str, Decimal]
    line_items: List[TaxLineItem]
    assumptions: List[str]
    references: List[TaxReference]
    exchange_rate_usd_to_khr: Optional[Decimal] = None
    cif_value_usd: Optional[Decimal] = None
    preferential_rate_missing: Optional[bool] = None
    requested_agreement: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "calculation_id": self.calculation_id,
            "currency": self.currency,
            "total": float(self.total),
            "breakdown": {k: float(v) for k, v in self.breakdown.items()},
            "line_items": [item.to_dict() for item in self.line_items],
            "assumptions": self.assumptions,
            "references": [ref.to_dict() for ref in self.references],
        }
        if self.exchange_rate_usd_to_khr is not None:
            result["exchange_rate_usd_to_khr"] = float(self.exchange_rate_usd_to_khr)
        if self.cif_value_usd is not None:
            result["cif_value_usd"] = float(self.cif_value_usd)
        if self.preferential_rate_missing is not None:
            result["preferential_rate_missing"] = self.preferential_rate_missing
        if self.requested_agreement is not None:
            result["requested_agreement"] = self.requested_agreement
        return result

    def format_for_display(self) -> str:
        """Format calculation result in simple, step-by-step format."""
        lines: List[str] = []

        cif = self.breakdown.get("cif_value", Decimal("0"))
        cop = self.breakdown.get("cop_amount", Decimal("0"))
        sop = self.breakdown.get("sop_amount", Decimal("0"))
        vop = self.breakdown.get("vop_amount", Decimal("0"))
        total = self.total

        lines.append("## Customs Tax Calculation (Step-by-Step)")
        lines.append("")

        if self.assumptions:
            lines.append("### Assumptions")
            for assumption in self.assumptions[:7]:
                if assumption and assumption.strip():
                    lines.append(f"- {assumption}")

        lines.append("")
        lines.append("### Calculation")

        if cop > 0:
            cop_base = cif
            cop_rate = cop / cop_base * 100 if cop_base > 0 else 0
            lines.append(
                f"1. **Import Taxes (COP)** = {float(cif):,.2f} KHR × {float(cop_rate):.2f}%"
            )
            lines.append(f"   = **{float(cop):,.2f} KHR**")
            lines.append("")

        if sop > 0:
            sop_base = cif + cop
            sop_rate = sop / sop_base * 100 if sop_base > 0 else 0
            lines.append(
                f"2. **Special Tariff (SOP)** = ({float(cif):,.2f} + {float(cop):,.2f}) × {float(sop_rate):.2f}%"
            )
            lines.append(f"   = **{float(sop):,.2f} KHR**")
            lines.append("")

        if vop > 0:
            vop_base = cif + cop + sop
            vop_rate = vop / vop_base * 100 if vop_base > 0 else 0
            lines.append(
                f"3. **Value Added Tax (VAT)** = ({float(cif):,.2f} + {float(cop):,.2f} + {float(sop):,.2f}) × {float(vop_rate):.2f}%"
            )
            lines.append(f"   = **{float(vop):,.2f} KHR**")
            lines.append("")

        lines.append("### **Total Taxes and Duties**")
        lines.append(f"= {float(cop):,.2f} + {float(sop):,.2f} + {float(vop):,.2f}")
        lines.append(f"= **{float(total):,.2f} KHR**")

        return "\n".join(lines)
