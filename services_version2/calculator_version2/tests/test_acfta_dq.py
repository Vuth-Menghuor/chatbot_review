from decimal import Decimal

from services_version2.calculator_version2.core.calculator import ImportTaxCalculator, DatabaseInterface
from services_version2.calculator_version2.core.models import CalculationRequest


class DummyDB(DatabaseInterface):
    def get_duty_rates(self, hs_code: str, origin_country: str, effective_date: str):
        # Return normal MFN rates and mark the HS as FTA-eligible in DB
        return {
            "cd_rate": Decimal("0.35"),
            "st_rate": Decimal("0.10"),
            "vat_rate": Decimal("0.10"),
            "fta_eligible": True,
        }

    def get_exchange_rate(self, currency_code: str, effective_date: str):
        return Decimal("4022.0")

    def get_hs_code_info(self, hs_code: str):
        return {"description": "Vehicle"}

    def get_declared_value(self, hs_code: str, effective_date: str = None):
        return None

    def save_calculation(self, calculation_result):
        return None


def test_acfta_with_dq_applies_zero_cop_and_dq_discount():
    db = DummyDB()
    calc = ImportTaxCalculator(db)

    request = CalculationRequest(
        calculation_date="2026-05-29",
        regime="import",
        goods={"hs_code": "8703.80.99", "origin_country": "China", "description": "vehicle"},
        valuation={
            "customs_value": 40000,
            "currency": "USD",
            # declared_value == 0 should be treated as not provided (use CIF)
            "declared_value": Decimal("0.00"),
            "dq_factor": Decimal("0.4"),
        },
        flags={"fta_applicable": True, "fta_certificate_type": "ACFTA"},
    )

    res = calc.calculate(request)

    # Expected values computed in the reference example
    assert res.breakdown["cop_amount"] == Decimal("0")
    assert res.breakdown["sop_amount"] == Decimal("13031300")
    assert res.breakdown["vop_amount"] == Decimal("14334500")
    assert res.breakdown["bur_amount"] == Decimal("18243800")
    assert res.breakdown["vvf_amount"] == Decimal("60000")
    assert res.total == Decimal("27425800")

    display = res.format_for_display()
    assert "4. **BUR (Build-Up Rebate / DQ Portion)**" in display
    assert "5. **Vehicle Valuation Fee (VVF)**" in display
