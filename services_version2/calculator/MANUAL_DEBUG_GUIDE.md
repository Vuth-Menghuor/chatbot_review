# GDCE Calculator — Manual Unit-by-Unit Debugging Guide

> One-stop copy-paste guide for manually testing every layer of the calculator service.
> Run from `W:\GDCE-ChatBot` (repo root) so Python can resolve the `calculator` package.

---

## Quick Reference Table

| Unit | File | What It Tests | Needs DB? | Needs Service? |
|------|------|---------------|-----------|----------------|
| 1 | `calculator/tests/test_formulas.py` | Pure math (rounding, CIF, COP, SOP, VOP, total) | ❌ No | ❌ No |
| 2 | `calculator/tests/test_currency_and_formatting.py` | Money regex, LLM post-validation, human-readable formatter | ❌ No | ❌ No |
| 3 | `calculator/tests/test_core.py` | `ImportTaxCalculator` with FakeDB | ❌ FakeDB | ❌ No |
| 4 | `calculator/tests/test_prefix_resolution.py` | HS prefix resolution, intent extractor regex, chapter mismatch | ❌ FakeDB | ❌ No |
| 5 | `calculator/tests/test_api.py` | FastAPI endpoints with FakeDB | ❌ FakeDB | ❌ No |
| 6 | `calculator/tests/test_converter.py` | Currency converter endpoints | ❌ FakeDB | ❌ No |
| 7 | `calculator/tests/test_import_export_cases.py` | Real HS codes against live DB (port 8002) | ✅ Yes | ✅ Port 8002 |
| 8 | `calculator/tests/test_chat_questions.py` | End-to-end NL questions via orchestrator (port 8001) | ✅ Yes | ✅ Port 8001 |

---

## 0. Prerequisites

Open **PowerShell** and navigate to the repo root:

```powershell
cd "W:\GDCE-ChatBot"
```

Verify pytest is available:

```powershell
python -m pytest --version
```

Expected: `pytest 9.x.x`

---

## 1. Unit 1 — Pure Formulas (`calculator/app/services/formulas.py`)

**What to debug:**
- `round_to_whole_number()`
- `round_up_to_hundred()`
- `calculate_cif_value()`
- `calculate_import_duty()`, `calculate_specific_tax()`, `calculate_vat()`
- `calculate_total_payable()`
- `calculate_normal_case()`

### 1.1 Run the formula test script

```powershell
cd "W:\GDCE-ChatBot"
$env:PYTHONPATH = "W:\GDCE-ChatBot"
python calculator/tests/test_formulas.py
```

**Expected output:** All sections print values and end with `"All formula tests completed successfully!"`

### 1.2 Manual REPL — test rounding edge cases

```powershell
python -c "
from calculator.app.services import formulas
from decimal import Decimal

# Rounding
print('round_to_whole(1234.567):', formulas.round_to_whole_number(Decimal('1234.567')))
print('round_up_to_hundred(1234):', formulas.round_up_to_hundred(Decimal('1234')))
print('round_up_to_hundred(1200):', formulas.round_up_to_hundred(Decimal('1200')))
print('round_up_to_hundred(1):', formulas.round_up_to_hundred(Decimal('1')))

# CIF
print('CIF:', formulas.calculate_cif_value(Decimal('10000'), Decimal('500'), Decimal('100')))

# Normal case
r = formulas.calculate_normal_case(
    exchange_rate=Decimal('4022.5'),
    item_price=Decimal('999.99'),
    cop_rate=Decimal('0.35'),
    sop_rate=Decimal('0.35'),
    vop_rate=Decimal('0.10')
)
print('CIF:', r['customs_value'])
print('COP:', r['cop'])
print('SOP:', r['sop'])
print('VOP:', r['vop'])
print('TOTAL:', r['total_payable'])
"
```

### 1.3 What to verify

| Check | Expected |
|-------|----------|
| `round_to_whole(1234.567)` | `1235` |
| `round_up_to_hundred(1234)` | `1300` |
| `round_up_to_hundred(1)` | `100` |
| Normal case total | `4041800` (for 999.99 USD × 4022.5) |

---

## 2. Unit 2 — Currency & Formatting (`app/ai/intent_extractor.py`, `app/ai/llm_formatter.py`)

**What to debug:**
- `IntentExtractor._extract_money()` — KHR/EUR glued suffix bug
- `IntentExtractor._post_validate_money()` — 1000× inflation safety net
- `format_human_readable()` — currency-aware formatting

### 2.1 Run the pytest suite

```powershell
cd "W:\GDCE-ChatBot"
python -m pytest calculator/tests/test_currency_and_formatting.py -v
```

**Expected:** 25 passed.

### 2.2 Manual REPL — money regex (the core KHR bug)

```powershell
python -c "
from calculator.app.ai.intent_extractor import IntentExtractor

# Bug: 'khr' was treated as K suffix (×1000)
tests = [
    ('CIF 400,000,000khr', 400000000.0, 'KHR'),
    ('CIF 500khr', 500.0, 'KHR'),
    ('customs value 1000KHR', 1000.0, 'KHR'),
    ('CIF 50000eur', 50000.0, 'EUR'),
    ('CIF 2.2M USD', 2200000.0, 'USD'),
    ('CIF 8000', 8000.0, None),
]

for text, exp_val, exp_cur in tests:
    val, cur = IntentExtractor._extract_money(text)
    ok = (val == exp_val and cur == exp_cur)
    print(f'{\"PASS\" if ok else \"FAIL\"}: \"{text}\" => val={val}, cur={cur}')
"
```

### 2.3 Manual REPL — human-readable formatter (KHR vs USD)

```powershell
python -c "
from calculator.app.ai.llm_formatter import format_human_readable
from calculator.app.services.models import CalculationRequest

# KHR input should NOT show 0.00 USD
req = CalculationRequest(
    calculation_date='2026-08-06',
    regime='import',
    goods={'hs_code': '0102.10.00', 'description': 'Rice', 'origin_country': 'KH'},
    valuation={'customs_value': 50000000.0, 'currency': 'KHR'},
)
result = {
    'breakdown': {'cif_value': 50000000.0, 'cop_amount': 0.0, 'sop_amount': 0.0, 'vop_amount': 5000000.0, 'vvf_amount': 0.0, 'fees': 0.0},
    'line_items': [
        {'name': 'VOP', 'tax_type': 'VAT', 'amount': 5000000.0, 'currency': 'KHR', 'base': 50000000.0, 'rate': 10.0},
    ],
    'assumptions': ['HS: 0102.10.00'],
    'references': [],
    'exchange_rate_usd_to_khr': 1.0,
    'cif_value_usd': None,
    'total': 5000000.0,
    'currency': 'KHR',
}
text = format_human_readable(req, result)
print(text)
assert '0.00 USD' not in text, 'FAIL: Should not show 0.00 USD for KHR input'
assert 'CURRENCY CONFIRMATION' in text, 'FAIL: Should say CONFIRMATION not CONVERSION'
print('PASS: KHR input formatting is correct')
"
```

### 2.4 What to verify

| Check | Expected |
|-------|----------|
| `500khr` value | `500.0` (NOT `500000.0`) |
| `2.2M USD` value | `2200000.0` |
| KHR formatter | No `"0.00 USD"`, says `"CURRENCY CONFIRMATION"` |
| USD formatter | Shows `"40,000.00 USD"` and `"1 USD = 4,022.00 KHR"` |

---

## 3. Unit 3 — Core Calculator (`app/services/calculator.py` with FakeDB)

**What to debug:**
- `ImportTaxCalculator.calculate()` — normal case
- Rounding to ceiling 100
- Zero SOP → conditional VOP base
- FTA/DV — original amounts feed SOP/VOP base
- FTA/DV/DQ — BUR calculation
- Exemptions (QIP, passenger allowance)
- ATP rate from DB not overwritten

### 3.1 Run the pytest suite

```powershell
cd "W:\GDCE-ChatBot"
python -m pytest calculator/tests/test_core.py -v
```

**Expected:** 10 passed.

### 3.2 Debug a single test with pdb (stops on failure)

```powershell
python -m pytest calculator/tests/test_core.py::test_normal_case_rounding_to_ceiling_100 -v --pdb
```

### 3.3 Manual REPL — full calculation with FakeDB

```powershell
python -c
" from decimal import Decimal
from calculator.app.services.calculator import ImportTaxCalculator, CalculationRequest, DatabaseInterface

class FakeDB(DatabaseInterface):
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

assert result.breakdown['cop_amount'] == Decimal('1407900'), f\"COP wrong: {result.breakdown['cop_amount']}\"
assert result.breakdown['sop_amount'] == Decimal('1900700'), f\"SOP wrong: {result.breakdown['sop_amount']}\"
assert result.breakdown['vop_amount'] == Decimal('733200'), f\"VOP wrong: {result.breakdown['vop_amount']}\"
assert result.total == Decimal('4041800'), f\"Total wrong: {result.total}\"
print('PASS: All amounts match expected values')
"
```

### 3.4 What to verify

| Check | Formula | Expected |
|-------|---------|----------|
| CIF | 999.99 × 4022.5 | 4,022,460 KHR |
| COP | 4,022,460 × 0.35 → round whole → round up 100 | 1,407,900 |
| SOP | (4,022,460 + 1,407,900) × 0.35 → round whole → round up 100 | 1,900,700 |
| VOP | (4,022,460 + 1,407,900 + 1,900,700) × 0.10 → round whole → round up 100 | 733,200 |
| Total | COP + SOP + VOP | 4,041,800 |

---

## 4. Unit 4 — Prefix Resolution (`app/services/hs_code_handler.py`, `app/ai/intent_extractor.py`)

**What to debug:**
- `HSCodeHandler.is_prefix_code()` — 4/5/6-digit detection
- Intent extractor regex — bare 4-digit, prefixed 4-digit, 5-digit
- Prefix + description resolution
- Chapter mismatch ask-back

### 4.1 Run the pytest suite

```powershell
cd "W:\GDCE-ChatBot"
python -m pytest calculator/tests/test_prefix_resolution.py -v
```

**Expected:** 10 passed.

### 4.2 Manual REPL — prefix detection

```powershell
python -c "
from calculator.app.services.hs_code_handler import HSCodeHandler

class FakeDBNoRates:
    def get_duty_rates(self, hs, origin, date=None):
        return None

handler = HSCodeHandler(FakeDBNoRates())

tests = [
    ('7204', True),
    ('72041', True),
    ('7204.10', True),
    ('7204.10.00', False),
    ('8703.22.59', False),
]

for code, expected in tests:
    result = handler.is_prefix_code(code)
    ok = result == expected
    print(f'{\"PASS\" if ok else \"FAIL\"}: is_prefix_code(\"{code}\") = {result} (expected {expected})')
"
```

### 4.3 Manual REPL — intent extractor regex

```powershell
python -c "
from calculator.app.ai.intent_extractor import IntentExtractor

extractor = IntentExtractor(enabled=False)

tests = [
    ('Calculate import tax for 7204 steel CIF \\$5000 from China', '7204'),
    ('What is the tax for HS 7204 steel from Thailand CIF 2000', '7204'),
    ('Calculate import tax for HS 72049 steel CIF \\$5000 from China', '72049'),
]

for text, expected_hs in tests:
    result = extractor._extract_regex(text)
    hs = result.goods.get('hs_code') if result else None
    ok = hs == expected_hs
    print(f'{\"PASS\" if ok else \"FAIL\"}: \"{text[:50]}...\" => hs={hs} (expected {expected_hs})')
"
```

### 4.4 What to verify

| Check | Expected |
|-------|----------|
| `7204` is prefix | `True` |
| `7204.10` is prefix (DB has no rates) | `True` |
| `7204.10.00` is prefix | `False` |
| Regex extracts bare 4-digit | `7204` |
| Regex extracts prefixed 5-digit | `72049` |
| Chapter mismatch → ValueError | Ask-back with `"mismatch"` |

---

## 5. Unit 5 — API Layer (`app/api/v1/calculator_routes.py`, `app/api/routes.py`)

**What to debug:**
- `POST /calculate_import_taxes` — normal calculation
- Ask-back flows (FTA without rate, exemption without rate)
- Currency fallback chain (explicit → inferred → default KHR)
- Description vs HS code conflict detection
- Natural language `/query` endpoint

### 5.1 Run the pytest suite

```powershell
cd "W:\GDCE-ChatBot"
python -m pytest calculator/tests/test_api.py -v
```

**Expected:** 20 passed.

### 5.2 Debug a specific test with pdb

```powershell
python -m pytest calculator/tests/test_api.py::test_fta_without_rate_returns_ask_back -v --pdb
```

### 5.3 Manual curl — normal calculation

```powershell
curl -s -X POST http://127.0.0.1:8002/calculate_import_taxes `
  -H "Content-Type: application/json" `
  -d '{"calculation_date":"2026-08-06","regime":"import","goods":{"description":"Laptops","hs_code":"8471.30.20","origin_country":"US"},"valuation":{"customs_value":50000,"currency":"USD"}}' | python -m json.tool
```

**Expected:** `total` > 0, `currency: "KHR"`, COP ~14M, SOP = 0, VOP ~21.7M

### 5.4 Manual curl — ask-back (FTA claimed, no rate)

```powershell
curl -s -X POST http://127.0.0.1:8002/calculate_import_taxes `
  -H "Content-Type: application/json" `
  -d '{"calculation_date":"2026-08-06","regime":"import","goods":{"description":"Cars","hs_code":"8703","origin_country":"CN"},"valuation":{"customs_value":10000,"currency":"USD"},"flags":{"fta_applicable":true,"fta_certificate_type":"ACFTA"}}' | python -m json.tool
```

**Expected:** `total: 0`, `preferential_rate_missing: true`, `requested_agreement: "ACFTA"`

### 5.5 Manual curl — currency inference (no currency, origin=Thailand)

```powershell
curl -s -X POST http://127.0.0.1:8002/calculate_import_taxes `
  -H "Content-Type: application/json" `
  -d '{"calculation_date":"2026-08-06","regime":"import","goods":{"description":"Rice","hs_code":"1006","origin_country":"Thailand"},"valuation":{"customs_value":5000}}' | python -m json.tool
```

**Expected:** `assumptions` contains `"inferred as THB"`

### 5.6 Manual curl — natural language query

```powershell
curl -s -X POST http://127.0.0.1:8002/query `
  -H "Content-Type: application/json" `
  -d '{"question":"calculate import tax for car cif 40000 USD from china hs 8703"}' | python -m json.tool
```

**Expected:** `success: true`, `result.total` > 0

### 5.7 What to verify

| Check | Expected |
|-------|----------|
| Normal calc | `total > 0`, `currency == "KHR"` |
| FTA ask-back | `total == 0`, `preferential_rate_missing == true` |
| Currency inference | Assumption says `"inferred as THB"` for Thailand origin |
| NL query | `success == true`, intent extracted correctly |

---

## 6. Unit 6 — Currency Converter (`app/converter/`)

**What to debug:**
- `GET /v1/currencies` — list supported currencies
- `POST /v1/convert/natural` — parse natural language conversion queries
- Edge cases: glued amount (`40000usd`), arrow (`→`), comma (`10,000`), decimal (`1500.50`)

### 6.1 Run the pytest suite

```powershell
cd "W:\GDCE-ChatBot"
python -m pytest calculator/tests/test_converter.py -v
```

**Expected:** 18 passed.

### 6.2 Manual curl — list currencies

```powershell
curl -s http://127.0.0.1:8002/v1/currencies | python -m json.tool
```

**Expected:** `count > 0`, entries have `code`, `name`, `symbol`, `decimals`

### 6.3 Manual curl — natural conversion (glued)

```powershell
curl -s -X POST http://127.0.0.1:8002/v1/convert/natural `
  -H "Content-Type: application/json" `
  -d '{"query":"40000usd to khr"}' | python -m json.tool
```

**Expected:** `parsed_amount: 40000`, `from_currency: "USD"`, `to_currency: "KHR"`, `converted_amount > 0`

### 6.4 Manual curl — natural conversion (arrow)

```powershell
curl -s -X POST http://127.0.0.1:8002/v1/convert/natural `
  -H "Content-Type: application/json" `
  -d '{"query":"40000 usd → khr"}' | python -m json.tool
```

**Expected:** Same as above.

### 6.5 Manual curl — missing amount (should fail)

```powershell
curl -s -X POST http://127.0.0.1:8002/v1/convert/natural `
  -H "Content-Type: application/json" `
  -d '{"query":"usd to khr"}' | python -m json.tool
```

**Expected:** HTTP 400.

### 6.6 What to verify

| Check | Expected |
|-------|----------|
| `40000usd to khr` | `parsed_amount: 40000`, `parsed_from: "USD"` |
| `$500 to euro` | `parsed_amount: 500`, `parsed_from: "USD"`, `parsed_to: "EUR"` |
| `1 THB to KHR` | `converted_amount >= 200` (rounded up to 100) |
| `100 USD to USD` | `exchange_rate: 1.0`, note contains `"same"` |
| `usd to khr` (no amount) | Status 400 |

---

## 7. Unit 7 — Import/Export Integration (Live DB, Port 8002)

**What to debug:**
- Real HS codes from PostgreSQL database
- Real exchange rates (USD→KHR ~4022)
- All calculation paths: normal, FTA/DV, FTA/DV/DQ, exemptions, rubber export

### 7.1 Check service is running

```powershell
curl -s http://127.0.0.1:8002/docs > $null; if ($?) { "Service UP" } else { "Service DOWN" }
```

If DOWN, start it:

```powershell
cd "W:\GDCE-ChatBot\calculator"
docker-compose up -d calculator
```

### 7.2 Run the full integration script

```powershell
cd "W:\GDCE-ChatBot\calculator"
python tests/test_import_export_cases.py
```

**Expected:** `27 passed, 0 failed`

### 7.3 Manual curl — Normal import (spirits, COP+SOP+VOP)

```powershell
curl -s -X POST http://127.0.0.1:8002/calculate_import_taxes `
  -H "Content-Type: application/json" `
  -d '{"calculation_date":"2026-08-06","regime":"import","goods":{"description":"Whisky in bottles","hs_code":"2208.90.10","origin_country":"GB","quantity":500,"unit":"liters"},"valuation":{"customs_value":12000,"currency":"USD"},"flags":{}}' | python -m json.tool
```

**Expected:**
- COP rate: 35%, SOP rate: 35%, VAT rate: 10%
- Total ~48.9M KHR

### 7.4 Manual curl — Zero SOP (laptops)

```powershell
curl -s -X POST http://127.0.0.1:8002/calculate_import_taxes `
  -H "Content-Type: application/json" `
  -d '{"calculation_date":"2026-08-06","regime":"import","goods":{"description":"Laptop computers","hs_code":"8471.30.20","origin_country":"US","quantity":100,"unit":"units"},"valuation":{"customs_value":50000,"currency":"USD"},"flags":{}}' | python -m json.tool
```

**Expected:**
- COP rate: 7%, SOP rate: 0%, VAT rate: 10%
- SOP amount: 0
- VOP base = CIF + COP (NOT CIF + COP + SOP)
- Total ~35.9M KHR

### 7.5 Manual curl — FTA/DV/DQ (vehicles with DQ factor)

```powershell
curl -s -X POST http://127.0.0.1:8002/calculate_import_taxes `
  -H "Content-Type: application/json" `
  -d '{"calculation_date":"2026-08-06","regime":"import","goods":{"description":"Motor cars, spark-ignition, 1500cc-3000cc","hs_code":"8703.22.29","origin_country":"CN","quantity":1,"unit":"units"},"valuation":{"customs_value":13869,"currency":"USD","dq_factor":0.50},"flags":{"fta_applicable":true,"fta_certificate_type":"ACFTA","dq_applicable":true,"preferential_cd_rate":0.0}}' | python -m json.tool
```

**Expected:**
- COP = 0 (DV=0)
- SOP > 0, VOP > 0
- BUR amount present
- VVF = 60,000 KHR
- Total ~24.7M KHR

### 7.6 Manual curl — Rubber export (ETR only)

```powershell
curl -s -X POST http://127.0.0.1:8002/calculate_import_taxes `
  -H "Content-Type: application/json" `
  -d '{"calculation_date":"2026-08-06","regime":"export","goods":{"description":"Natural rubber","hs_code":"4001.21.10","origin_country":"KH","net_mass_kg":15000},"valuation":{"customs_value":18000,"currency":"USD","declared_value":1200,"declared_value_basis":"per_ton"},"flags":{"rubber_case":true}}' | python -m json.tool
```

**Expected:**
- `regime: "export"`
- ETR amount present (may be 0 if ET rate is 0 in DB)
- Total = ETR amount

### 7.7 What to verify

| Case | HS Code | Expected Rates | Expected Behavior |
|------|---------|----------------|-------------------|
| Spirits | 2208.90.10 | CD=35%, ST=35%, VAT=10% | Normal COP+SOP+VOP |
| Cigarettes | 2402.20.10 | CD=7%, ST=20%, VAT=10% | Normal COP+SOP+VOP |
| Laptops | 8471.30.20 | CD=7%, ST=0%, VAT=10% | Zero SOP, VOP base = CIF+COP |
| Phones | 8517.62.10 | CD=0%, ST=0%, VAT=10% | Only VOP |
| FTA/DV (ASEAN) | Any with ACFTA | Preferential CD=0% | Ask-back if no rate provided |
| FTA/DV/DQ | 8703.x.x | DV=0, DQ factor applied | COP=0, SOP/VOP reduced by DQ, BUR emitted |
| Rubber export | 4001.x.x | ET rate from DB | ETR only, no VAT |
| Exemptions | Any | Any | Ask-back (needs rate confirmation) |

---

## 8. Unit 8 — End-to-End Chat (Orchestrator, Port 8001)

**What to debug:**
- Natural language questions through the orchestrator
- LLM intent extraction → calculator service → formatted response
- Full pipeline: `/query` → NL understanding → calculation → human-readable answer

### 8.1 Check orchestrator is running

```powershell
curl -s http://127.0.0.1:8001/health > $null; if ($?) { "Orchestrator UP" } else { "Orchestrator DOWN" }
```

If DOWN, start it (adjust path as needed for your setup):

```powershell
cd "W:\GDCE-ChatBot"
docker-compose up -d orchestrator
```

### 8.2 Run the chat test script

```powershell
cd "W:\GDCE-ChatBot\calculator"
python tests/test_chat_questions.py
```

**Expected:** Varies — some cases may fail if HS codes are not seeded in the live DB.

### 8.3 Manual curl — natural language query

```powershell
curl -s -X POST http://127.0.0.1:8001/query `
  -H "Content-Type: application/json" `
  -d '{"question":"calculate import tax for 200 liters of whisky from the UK, HS code 2208.90.10, CIF value \\$5000","session_id":"test-001"}' | python -m json.tool
```

**Expected:**
- `status: "completed"`
- `intent: "calculation"`
- `answer` contains COP, SOP, VOP rates and total in KHR

### 8.4 Manual curl — passenger allowance

```powershell
curl -s -X POST http://127.0.0.1:8001/query `
  -H "Content-Type: application/json" `
  -d '{"question":"i am bringing personal electronics worth \\$1200 from USA in my luggage. do i pay duty","session_id":"test-002"}' | python -m json.tool
```

**Expected:**
- `answer` mentions exemption/passenger allowance
- Total shown as 0 or exempt

### 8.5 What to verify

| Check | Expected |
|-------|----------|
| NL whisky query | Answer contains COP=35%, SOP=35%, VOP=10% |
| NL laptop query | Answer contains COP=7%, SOP=0%, VOP=10% |
| Passenger question | Answer mentions exemption, total = 0 KHR |
| Status | `"completed"` |
| Intent | `"calculation"` |
| Answer length | `len(answer) > 50` |

---

## Debug Tips & Commands

### Stop at first failure
```powershell
python -m pytest <path> -x
```

### Drop into pdb on failure
```powershell
python -m pytest <path> -v --pdb
```

### Run a single test by name
```powershell
python -m pytest calculator/tests/test_core.py -v -k test_normal_case_rounding
```

### Show local variables on failure
```powershell
python -m pytest <path> -v -l
```

### Print stdout during tests
```powershell
python -m pytest <path> -v -s
```

### Insert a manual breakpoint in source code
Add this line anywhere in the code you want to inspect:
```python
import pdb; pdb.set_trace()
```
Then run the test normally — it will pause at that line.

### Check Docker container status
```powershell
docker ps --filter "name=calculator"
docker logs --tail 50 calculator
```

### Restart calculator service
```powershell
cd "W:\GDCE-ChatBot\calculator"
docker-compose restart calculator
```

### Check if PostgreSQL has the expected HS codes
```powershell
docker exec -it calculator_postgres psql -U postgres -d gdce_calculator -c "SELECT hs_code, cd_rate, st_rate, vat_rate FROM duty_rates WHERE hs_code IN ('2208.90.10', '8471.30.20', '3923.10.10') LIMIT 10;"
```

---

## Troubleshooting Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: No module named 'calculator'` | Running from wrong directory | `cd W:\GDCE-ChatBot` and set `PYTHONPATH` |
| `pytest` not found | Not installed in current env | `pip install pytest` |
| Port 8002 connection refused | Calculator container not running | `docker-compose up -d calculator` |
| Port 8001 connection refused | Orchestrator not running | Start orchestrator service |
| All FTA cases return 0 total | No preferential rates in DB | Expected — ask-back behavior |
| `ast.Num` deprecation warning | Python 3.13 compat issue | Harmless until Python 3.14 |
| Pydantic `@validator` warning | Pydantic V1 style | Harmless until Pydantic V3 |
| FastAPI `on_event` warning | FastAPI lifespan change | Harmless for now |

---

## Version Info

- **Calculator service version:** 2.0.0
- **Test date:** 2026-08-06
- **Python:** 3.13.5
- **pytest:** 9.0.2
- **FastAPI:** Latest (with lifespan deprecation warning)
- **Pydantic:** V2.x (with V1 compat warnings)

---

*End of guide — start with Unit 1 and work your way down.*
