import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from calculator.app.services.calculator import ImportTaxCalculator, CalculationRequest

class FakeDB:
    def get_duty_rates(self, hs, origin, date):
        return {
            'cd_rate': Decimal('0.35'),
            'st_rate': Decimal('0.35'),
            'vat_rate': Decimal('0.10'),
            'et_rate': Decimal('0'),
        }
    def get_exchange_rate(self, cc, date):
        return Decimal('4022.5')
    def get_hs_code_info(self, hs):
        return {'description': 'Whisky', 'unit': 'ltr'}
    def get_declared_value(self, hs, date=None):
        return None
    def save_calculation(self, result):
        pass

db = FakeDB()
calc = ImportTaxCalculator(db)

req = CalculationRequest(
    calculation_date='2026-05-18',
    regime='import',
    goods={'hs_code': '2208.90.10', 'origin_country': 'GB', 'description': 'Whisky'},
    valuation={'customs_value': 999.99, 'currency': 'USD', 'exchange_rate_to_khr': Decimal('4022.5')},
    flags={},
    requested_breakdown=['duty', 'vat', 'total'],
)

result = calc.calculate(req)
print('Total:', result.total)
print('COP:', result.breakdown['cop_amount'])
print('SOP:', result.breakdown['sop_amount'])
print('VOP:', result.breakdown['vop_amount'])

assert result.breakdown['cop_amount'] == Decimal('1407900'), f"COP wrong: {result.breakdown['cop_amount']}"
assert result.breakdown['sop_amount'] == Decimal('1900700'), f"SOP wrong: {result.breakdown['sop_amount']}"
assert result.breakdown['vop_amount'] == Decimal('733200'), f"VOP wrong: {result.breakdown['vop_amount']}"
assert result.total == Decimal('4041800'), f"Total wrong: {result.total}"
print('PASS: All amounts match expected values')
