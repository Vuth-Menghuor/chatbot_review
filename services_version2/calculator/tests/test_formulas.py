"""
Quick test of calculator formulas
==================================
"""

from decimal import Decimal
from calculator.app.services import formulas

print("=" * 70)
print("GDCE Calculator Service - Formula Tests")
print("=" * 70)

# Test 1: Rounding Functions
print("\n1. ROUNDING TESTS")
print("-" * 50)
base_amount = Decimal("1234.567")
print(f"Original amount: ${base_amount}")
print(f"Round to whole: ${formulas.round_to_whole_number(base_amount)}")
print(f"Round up to hundred: ${formulas.round_up_to_hundred(base_amount)}")

# Test 2: CIF Calculation
print("\n2. CIF VALUE CALCULATION")
print("-" * 50)
fob = Decimal("10000")
freight = Decimal("500")
insurance = Decimal("100")
cif = formulas.calculate_cif_value(fob, freight, insurance)
print(f"FOB: ${fob}")
print(f"Freight: ${freight}")
print(f"Insurance: ${insurance}")
print(f"CIF Total: ${cif}")

# Test 3: Import Duty
print("\n3. CUSTOMS DUTY CALCULATION")
print("-" * 50)
customs_value = Decimal("50000")
cd_rate = Decimal("0.15")  # 15%
cd_amount = formulas.calculate_import_duty(customs_value, cd_rate)
print(f"Customs Value: ${customs_value:,.2f}")
print(f"CD Rate: {cd_rate * 100}%")
print(f"CD Amount: ${cd_amount:,.2f}")

# Test 4: Special Tax
print("\n4. SPECIFIC TAX CALCULATION")
print("-" * 50)
st_base = customs_value + cd_amount
st_rate = Decimal("0.10")  # 10%
st_amount = formulas.calculate_specific_tax(st_base, st_rate)
print(f"ST Base (CV + CD): ${st_base:,.2f}")
print(f"ST Rate: {st_rate * 100}%")
print(f"ST Amount: ${st_amount:,.2f}")

# Test 5: VAT
print("\n5. VAT CALCULATION")
print("-" * 50)
vat_base = st_base + st_amount
vat_rate = Decimal("0.10")  # 10%
excise_tax = Decimal("0")
vat_amount = formulas.calculate_vat(vat_base, vat_rate, excise_tax)
print(f"VAT Base (CV + CD + ST): ${vat_base:,.2f}")
print(f"VAT Rate: {vat_rate * 100}%")
print(f"VAT Amount: ${vat_amount:,.2f}")

# Test 6: Total Payable
print("\n6. TOTAL PAYABLE")
print("-" * 50)
total = formulas.calculate_total_payable(
    cd_amount, st_amount, vat_amount, Decimal("0")
)
print(f"CD: ${cd_amount:,.2f}")
print(f"ST: ${st_amount:,.2f}")
print(f"VAT: ${vat_amount:,.2f}")
print(f"TOTAL: ${total:,.2f}")

# Test 7: Normal Case Full Calculation
print("\n7. NORMAL CASE - FULL CALCULATION")
print("-" * 50)
exchange_rate = Decimal("4100")
item_price = Decimal("100")
cop_rate = Decimal("0.15")
sop_rate = Decimal("0.10")
vop_rate = Decimal("0.10")

result = formulas.calculate_normal_case(
    exchange_rate=exchange_rate,
    item_price=item_price,
    cop_rate=cop_rate,
    sop_rate=sop_rate,
    vop_rate=vop_rate
)
print(f"Exchange Rate: {exchange_rate} KHR/USD")
print(f"Item Price: ${item_price}")
print(f"Customs Value: {result['customs_value']:,.2f} KHR")
print(f"COP ({cop_rate * 100}%): {result['cop']:,.2f} KHR")
print(f"SOP ({sop_rate * 100}%): {result['sop']:,.2f} KHR")
print(f"VOP ({vop_rate * 100}%): {result['vop']:,.2f} KHR")
print(f"TOTAL PAYABLE: {result['total_payable']:,.2f} KHR")

print("\n" + "=" * 70)
print(" All formula tests completed successfully!")
print("=" * 70)
