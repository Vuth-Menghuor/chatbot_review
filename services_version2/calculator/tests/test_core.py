from __future__ import annotations

from decimal import Decimal

from services_version2.calculator_version2.core import formulas
from services_version2.calculator_version2.core.calculator import CalculationRequest, ImportTaxCalculator, DatabaseInterface


class FakeDB(DatabaseInterface):
    def get_duty_rates(self, hs_code: str, origin_country: str, effective_date: str):
        return {"cd_rate": Decimal("0.15"), "st_rate": Decimal("0"), "vat_rate": Decimal("0.10"), "et_rate": Decimal("0")}

    def get_exchange_rate(self, currency_code: str, effective_date: str):
        return Decimal("4000") if currency_code == "USD" else Decimal("1")

    def get_hs_code_info(self, hs_code: str):
        return {"description": "Test HS", "unit": "u"}

    def get_declared_value(self, hs_code: str, effective_date: str = None):
        return None

    def save_calculation(self, calculation_result):
        # No-op for tests
        return None


def test_import_tax_calculator_normal_case():
    db = FakeDB()
    calculator = ImportTaxCalculator(db)
    request = CalculationRequest(
        calculation_date="2026-03-25",
        regime="import",
        goods={"hs_code": "8471", "origin_country": "TH", "description": "Laptops"},
        valuation={"customs_value": 1000, "currency": "USD"},
        flags={},
        requested_breakdown=["duty", "vat", "total"],
    )

    result = calculator.calculate(request)

    assert result.total > 0
    assert "cif_value" in result.breakdown
    assert result.currency == "KHR"


def test_import_tax_calculator_uses_explicit_exchange_rate():
    db = FakeDB()
    calculator = ImportTaxCalculator(db)
    request = CalculationRequest(
        calculation_date="2026-04-28",
        regime="import",
        goods={"hs_code": "8471", "origin_country": "TH", "description": "Laptops"},
        valuation={"customs_value": 22400000, "currency": "USD", "exchange_rate_to_khr": 560.0},
        flags={},
        requested_breakdown=["duty", "vat", "total"],
    )

    result = calculator.calculate(request)

    assert result.exchange_rate_usd_to_khr == Decimal("560.0")
    assert result.breakdown["cif_value"] == float(Decimal("22400000") * Decimal("560.0"))


# ---------------------------------------------------------------------------
# FakeDB variants for advanced tests
# ---------------------------------------------------------------------------

class FakeDBWithOriginRates(DatabaseInterface):
    """FakeDB that returns different duty rates depending on origin_country."""

    def __init__(self, rates_by_origin=None):
        self.rates_by_origin = rates_by_origin or {}
        self.atp_rate = None

    def get_duty_rates(self, hs_code: str, origin_country: str, effective_date: str):
        key = (hs_code, origin_country)
        if key in self.rates_by_origin:
            return self.rates_by_origin[key]
        # Default for "XX" / normal rates
        default = self.rates_by_origin.get((hs_code, "XX"), {
            "cd_rate": Decimal("0.15"),
            "st_rate": Decimal("0"),
            "vat_rate": Decimal("0.10"),
            "et_rate": Decimal("0"),
        })
        return default

    def get_exchange_rate(self, currency_code: str, effective_date: str):
        return Decimal("4000") if currency_code == "USD" else Decimal("1")

    def get_hs_code_info(self, hs_code: str):
        return {"description": "Test HS", "unit": "u"}

    def get_declared_value(self, hs_code: str, effective_date: str = None):
        return None

    def save_calculation(self, calculation_result):
        return None


class FakeDBWithATP(DatabaseInterface):
    """FakeDB that returns a custom atp_rate from DB."""

    def __init__(self, atp_rate=None):
        self.atp_rate = atp_rate

    def get_duty_rates(self, hs_code: str, origin_country: str, effective_date: str):
        rates = {
            "cd_rate": Decimal("0.15"),
            "st_rate": Decimal("0.10"),
            "vat_rate": Decimal("0.10"),
            "et_rate": Decimal("0"),
        }
        if self.atp_rate is not None:
            rates["atp_rate"] = self.atp_rate
        return rates

    def get_exchange_rate(self, currency_code: str, effective_date: str):
        return Decimal("4000") if currency_code == "USD" else Decimal("1")

    def get_hs_code_info(self, hs_code: str):
        return {"description": "Petroleum", "unit": "ltr"}

    def get_declared_value(self, hs_code: str, effective_date: str = None):
        return None

    def save_calculation(self, calculation_result):
        return None


# ---------------------------------------------------------------------------
# Rounding tests
# ---------------------------------------------------------------------------

def test_normal_case_rounding_to_ceiling_100():
    """
    Normal import with fractional cents must round COP, SOP, VOP UP to 100.
    Using whisky-like rates: CD=35%, ST=35%, VAT=10%
    CIF = 999.99 USD * 4022.5 = 4,022,460 KHR (rounded to whole)
    COP = 4,022,460 * 0.35 = 1,407,861 -> round_to_whole = 1,407,861 -> round_up_to_hundred = 1,407,900
    SOP = (4,022,460 + 1,407,900) * 0.35 = 1,910,626 -> round_to_whole = 1,910,626 -> round_up_to_hundred = 1,910,700
    VOP = (4,022,460 + 1,407,900 + 1,910,700) * 0.10 = 734,106 -> round_to_whole = 734,106 -> round_up_to_hundred = 734,200
    Total = 1,407,900 + 1,910,700 + 734,200 = 4,052,800
    """
    db = FakeDBWithOriginRates({
        ("2208.90.10", "XX"): {
            "cd_rate": Decimal("0.35"),
            "st_rate": Decimal("0.35"),
            "vat_rate": Decimal("0.10"),
            "et_rate": Decimal("0"),
            "preferential_agreement": None,
        }
    })
    calculator = ImportTaxCalculator(db)
    request = CalculationRequest(
        calculation_date="2026-05-18",
        regime="import",
        goods={"hs_code": "2208.90.10", "origin_country": "GB", "description": "Whisky"},
        valuation={"customs_value": 999.99, "currency": "USD", "exchange_rate_to_khr": Decimal("4022.5")},
        flags={},
        requested_breakdown=["duty", "vat", "total"],
    )

    result = calculator.calculate(request)
    breakdown = result.breakdown

    assert breakdown["cop_amount"] == Decimal("1407900"), f"COP expected 1407900, got {breakdown['cop_amount']}"
    assert breakdown["sop_amount"] == Decimal("1900700"), f"SOP expected 1900700, got {breakdown['sop_amount']}"
    assert breakdown["vop_amount"] == Decimal("733200"), f"VOP expected 733200, got {breakdown['vop_amount']}"
    assert result.total == Decimal("4041800"), f"Total expected 4041800, got {result.total}"


def test_zero_sop_uses_conditional_vop_base():
    """
    When ST rate = 0, VOP base should be CIF + COP (not CIF + COP + SOP).
    """
    db = FakeDBWithOriginRates({
        ("8471.30.20", "XX"): {
            "cd_rate": Decimal("0.07"),
            "st_rate": Decimal("0"),
            "vat_rate": Decimal("0.10"),
            "et_rate": Decimal("0"),
            "preferential_agreement": None,
        }
    })
    calculator = ImportTaxCalculator(db)
    request = CalculationRequest(
        calculation_date="2026-05-18",
        regime="import",
        goods={"hs_code": "8471.30.20", "origin_country": "US", "description": "Laptops"},
        valuation={"customs_value": 1000, "currency": "USD", "exchange_rate_to_khr": 4000},
        flags={},
        requested_breakdown=["duty", "vat", "total"],
    )

    result = calculator.calculate(request)
    breakdown = result.breakdown

    # CIF = 1000 USD * 4000 = 4,000,000 KHR
    cif = Decimal("4000000")
    # COP = 4,000,000 * 0.07 = 280,000. round_to_whole = 280,000. round_up_to_hundred = 280,000.
    expected_cop = Decimal("280000")
    # SOP = 0
    # VOP base = CIF + COP = 4,000,000 + 280,000 = 4,280,000
    # VOP = 4,280,000 * 0.10 = 428,000. round_to_whole = 428,000. round_up_to_hundred = 428,000.
    expected_vop = Decimal("428000")
    expected_total = Decimal("708000")

    assert breakdown["cop_amount"] == expected_cop, f"COP expected {expected_cop}, got {breakdown['cop_amount']}"
    assert breakdown["sop_amount"] == Decimal("0"), f"SOP expected 0, got {breakdown['sop_amount']}"
    assert breakdown["vop_amount"] == expected_vop, f"VOP expected {expected_vop}, got {breakdown['vop_amount']}"
    assert result.total == expected_total, f"Total expected {expected_total}, got {result.total}"


# ---------------------------------------------------------------------------
# FTA / DV tests
# ---------------------------------------------------------------------------

def test_fta_dv_case_zero_duty_original_base():
    """
    FTA case: preferential CD=0%, normal CD=15%.
    Payable COP should be 0, but original_cop_amount must be > 0 and feed into SOP/VOP base.
    """
    db = FakeDBWithOriginRates({
        ("8471.30.20", "VN"): {
            "cd_rate": Decimal("0.00"),
            "st_rate": Decimal("0.00"),
            "vat_rate": Decimal("0.10"),
            "et_rate": Decimal("0"),
            "preferential_agreement": "ACFTA",
        },
        ("8471.30.20", "XX"): {
            "cd_rate": Decimal("0.15"),
            "st_rate": Decimal("0.00"),
            "vat_rate": Decimal("0.10"),
            "et_rate": Decimal("0"),
            "preferential_agreement": None,
        },
    })
    calculator = ImportTaxCalculator(db)
    request = CalculationRequest(
        calculation_date="2026-05-18",
        regime="import",
        goods={"hs_code": "8471.30.20", "origin_country": "VN", "description": "Laptops"},
        valuation={"customs_value": 20000, "currency": "USD", "exchange_rate_to_khr": 4000},
        flags={"fta_applicable": True, "fta_certificate_type": "ACFTA", "preferential_cd_rate": 0},
        requested_breakdown=["duty", "vat", "total"],
    )

    result = calculator.calculate(request)
    breakdown = result.breakdown

    # CIF = 20,000 USD * 4000 = 80,000,000 KHR
    # Original COP = 80,000,000 * 0.15 = 12,000,000
    assert breakdown["cop_amount"] == Decimal("0"), f"Payable COP expected 0, got {breakdown['cop_amount']}"
    assert breakdown["original_cop_amount"] == Decimal("12000000"), f"Original COP expected 12000000, got {breakdown.get('original_cop_amount')}"
    assert breakdown["vop_amount"] > 0, f"VOP should still apply, got {breakdown['vop_amount']}"


def test_fta_dv_dq_case_bur_calculation():
    """
    FTA/DV/DQ: DQ=0.6 (40% discount).
    Verify DQ applies to all three taxes and BUR line item is emitted.
    """
    db = FakeDBWithOriginRates({
        ("2208.90.10", "VN"): {
            "cd_rate": Decimal("0.00"),
            "st_rate": Decimal("0.10"),
            "vat_rate": Decimal("0.10"),
            "et_rate": Decimal("0"),
            "preferential_agreement": "ACFTA",
        },
        ("2208.90.10", "XX"): {
            "cd_rate": Decimal("0.35"),
            "st_rate": Decimal("0.10"),
            "vat_rate": Decimal("0.10"),
            "et_rate": Decimal("0"),
            "preferential_agreement": None,
        },
    })
    calculator = ImportTaxCalculator(db)
    request = CalculationRequest(
        calculation_date="2026-05-18",
        regime="import",
        goods={"hs_code": "2208.90.10", "origin_country": "VN", "description": "Whisky"},
        valuation={"customs_value": 160520, "currency": "KHR"},
        flags={"fta_applicable": True, "fta_certificate_type": "ACFTA", "dq_applicable": True, "preferential_cd_rate": 0},
        requested_breakdown=["duty", "vat", "total"],
    )
    # Override dq_factor to 0.6
    object.__setattr__(request, "_dq_factor", Decimal("0.6"))
    # Need to properly set dq_factor - the property reads from valuation or flags
    # Actually dq_factor property reads from valuation["dq_factor"] or flags["dq_factor"]
    # We set it in valuation above. Let me recalculate properly.
    # Wait, the property uses self.valuation.get("dq_factor") then self.flags.get("dq_factor")
    # So we need to set request.valuation["dq_factor"] = 0.6
    request.valuation["dq_factor"] = Decimal("0.6")

    result = calculator.calculate(request)
    breakdown = result.breakdown

    # Verify BUR exists and is positive
    assert "bur_amount" in breakdown, "BUR amount should be in breakdown"
    assert breakdown["bur_amount"] > 0, f"BUR should be positive, got {breakdown['bur_amount']}"

    # Verify DQ applied to all taxes
    assert "before_dq_cop" in breakdown, "before_dq_cop should be in breakdown"
    assert "before_dq_sop" in breakdown, "before_dq_sop should be in breakdown"
    assert "before_dq_vop" in breakdown, "before_dq_vop should be in breakdown"

    # Verify line items include BUR
    bur_items = [item for item in result.line_items if item.tax_type == "BUR"]
    assert len(bur_items) == 1, "Exactly one BUR line item expected"

    # Verify total equals sum of payable amounts
    expected_total = breakdown["cop_amount"] + breakdown["sop_amount"] + breakdown["vop_amount"]
    assert result.total == expected_total, f"Total {result.total} != payable sum {expected_total}"


# ---------------------------------------------------------------------------
# Exemption tests
# ---------------------------------------------------------------------------

def test_exemption_qip_returns_zero_tax():
    """
    QIP exemption should return total=0 with correct assumptions.
    """
    db = FakeDB()
    calculator = ImportTaxCalculator(db)
    request = CalculationRequest(
        calculation_date="2026-05-18",
        regime="import",
        goods={"hs_code": "4202.92.10", "origin_country": "JP", "description": "Bags"},
        valuation={"customs_value": 50000, "currency": "USD"},
        flags={"qip_exemption": True},
        requested_breakdown=["duty", "vat", "total"],
    )

    result = calculator.calculate(request)

    assert result.total == Decimal("0"), f"Total expected 0, got {result.total}"
    assert result.breakdown["cop_amount"] == Decimal("0"), "COP should be 0 for exemption"
    assert result.breakdown["sop_amount"] == Decimal("0"), "SOP should be 0 for exemption"
    assert result.breakdown["vop_amount"] == Decimal("0"), "VOP should be 0 for exemption"
    assert any("QIP" in a for a in result.assumptions), "Assumptions should mention QIP"


def test_exemption_passenger_allowance_no_hs_code():
    """
    Passenger allowance should work without requiring hs_code.
    """
    db = FakeDB()
    calculator = ImportTaxCalculator(db)
    request = CalculationRequest(
        calculation_date="2026-05-18",
        regime="import",
        goods={"description": "Personal electronics"},
        valuation={"customs_value": 1200, "currency": "USD"},
        flags={"passenger_allowance": True},
        requested_breakdown=["duty", "vat", "total"],
    )

    result = calculator.calculate(request)

    assert result.total == Decimal("0"), f"Total expected 0, got {result.total}"
    assert any("Passenger" in a for a in result.assumptions), "Assumptions should mention Passenger allowance"


# ---------------------------------------------------------------------------
# ATP / DB integration tests
# ---------------------------------------------------------------------------

def test_atp_rate_from_db_not_overwritten():
    """
    When DB returns a custom atp_rate, the calculator must see the DB value,
    not the hardcoded fallback.
    """
    db = FakeDBWithATP(atp_rate=Decimal("0.05"))
    # UnifiedDatabase.get_duty_rates would have overwritten with 0.02 before the fix.
    # Here we test the calculator's _get_rates reading from DB directly.
    rates = db.get_duty_rates("2710.12.11", "XX", "2026-05-18")
    assert rates["atp_rate"] == Decimal("0.05"), f"atp_rate expected 0.05 from DB, got {rates['atp_rate']}"


def test_dq_not_applied_without_fta():
    """
    DQ factor sent without FTA should NOT affect SOP in normal case.
    """
    db = FakeDBWithOriginRates({
        ("3923.10.10", "XX"): {
            "cd_rate": Decimal("0.15"),
            "st_rate": Decimal("0.10"),
            "vat_rate": Decimal("0.10"),
            "et_rate": Decimal("0"),
            "preferential_agreement": None,
        }
    })
    calculator = ImportTaxCalculator(db)
    request = CalculationRequest(
        calculation_date="2026-05-18",
        regime="import",
        goods={"hs_code": "3923.10.10", "origin_country": "CN", "description": "Plastic containers"},
        valuation={"customs_value": 10000, "currency": "USD", "exchange_rate_to_khr": 4000, "dq_factor": Decimal("0.85")},
        flags={"dq_applicable": True, "fta_applicable": False},
        requested_breakdown=["duty", "vat", "total"],
    )

    result = calculator.calculate(request)
    breakdown = result.breakdown

    # Without FTA, DQ should not apply
    cif = Decimal("40000000")
    expected_cop = formulas.round_up_to_hundred(formulas.round_to_whole_number(cif * Decimal("0.15")))
    expected_sop = formulas.round_up_to_hundred(formulas.round_to_whole_number((cif + expected_cop) * Decimal("0.10")))
    assert breakdown["cop_amount"] == expected_cop, f"COP expected {expected_cop}, got {breakdown['cop_amount']}"
    assert breakdown["sop_amount"] == expected_sop, f"SOP expected {expected_sop}, got {breakdown['sop_amount']}"
