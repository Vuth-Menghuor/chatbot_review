# Calculator Service v2 - Complete Architecture Guide

## 📋 Overview

**Calculator Service v2** handles import tax calculations for Cambodia customs (GDCE). It's a microservice that:

1. **Receives** a calculation request (HS code, origin country, goods value, currency)
2. **Looks up** duty rates and exchange rates from data sources
3. **Calculates** customs duty, special tax, VAT, and excise tax
4. **Returns** a detailed breakdown with formulas and references

---

## 🗣️ Natural Language to Calculation Flow

The complete journey from user question to tax answer:

```
User Chat Question
        ↓
"Calculate tax for HS 0102.29.11 CIF $800 from China"
        ↓
Orchestrator Service (Port 8001)
├─ Parse question text
├─ Extract parameters:
│  ├─ hs_code: "0102.29.11"
│  ├─ origin: "China" → "CN"
│  ├─ value: "800"
│  └─ currency: "USD" or "KHR"
├─ (If product name instead of HS code: call Retrieval Service to lookup)
├─ Build structured JSON payload
└─ POST to Calculator Service (Port 8002)
        ↓
Calculator Service (/v1/calculate_import_taxes)
├─ Validate inputs
├─ Query duty rates from http://172.25.3.243:6333/dashboard#/collections/gdce_hs_code
├─ Apply formulas (CD, ST, VAT, ET)
├─ Convert to KHR (if the currency is not KHR)
└─ Return structured result
        ↓
Orchestrator Service (formats response)
├─ Convert to human-readable answer
├─ Add assumptions & sources
└─ Send to user
        ↓
User Receives Answer:
"Total Tax: 852,700 KHR
 - Customs Duty: 482,640 KHR (15%)
 - VAT: 369,024 KHR (10%)"
```

---

## 🏗️ Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│ API LAYER (FastAPI HTTP Interface)                      │
├─────────────────────────────────────────────────────────┤
│ • endpoints.py    → HTTP routes (/calculate, /lookup)   │
│ • schemas.py      → Request/response Pydantic models    │
│ • deps.py         → Dependency injection (get_db)       │
│ • routes.py       → Router configuration                │
└────────────────────┬────────────────────────────────────┘
                     │ passes CalculationRequest
                     ↓
┌─────────────────────────────────────────────────────────┐
│ CORE LAYER (Business Logic)                             │
├─────────────────────────────────────────────────────────┤
│ • calculator.py   → ImportTaxCalculator orchestration   │
│ • formulas.py     → Pure calculation functions          │
│ • models.py       → Domain data structures              │
│ • config.py       → Settings from .env                  │
└────────────────────┬────────────────────────────────────┘
                     │ uses DatabaseInterface
                     ↓
┌─────────────────────────────────────────────────────────┐
│ INFRASTRUCTURE LAYER (Data Access)                      │
├─────────────────────────────────────────────────────────┤
│ • qdrant_client.py          → Remote Qdrant queries     │
│ • exchange_rate_adapter.py  → Exchange rate lookups     │
│ • csv_database.py           → CSV fallback (legacy)     │
└─────────────────────────────────────────────────────────┘
```

---

## 📊 Data Flow: Complete Calculation

### Step 0: User Asks in Natural Language (via Chat)

Real users don't send JSON. They ask questions like:

```
User Input Examples:
────────────────────────────────────────────────────────
1. "Calculate tax for HS 0102.29.11 CIF $800 from China"
2. "Calculate tax for Oxen CIF 800 USD from China"
3. "Calculate tax for honda dream, CIF 2000 USD from China"
4. "What's the duty on live cattle CIF 500 from Thailand?"
5. "I need to import 10 units of cattle from China, CIF 8000. Taxes?"
6. "I want to know the tax of import 10 live horses."
```

### Step 1: Orchestrator Parses Natural Language

The **Orchestrator Service** (running on port 8001) receives the chat question and:

```python
# services_version2/orchestrator_version2/core/coordinator.py

1. Detect intent: "CALCULATE_TAX"
2. Extract parameters from user text:
   ├─ hs_code: "0102.29.11" (from number pattern or product name lookup)
   ├─ origin_country: "CN" (from "China" country mapping)
   ├─ customs_value: 800 (from "$800" or "800")
   ├─ currency: "USD" (explicit or assumed from context)
   └─ calculation_date: "2026-04-01" (today's date)

3. Call Retrieval Service to look up HS code if only product name given
   - Query: "Oxen" or "honda dream"
   - Returns: hs_code "0102.29.11" for cattle

4. Build internal CalculationRequest JSON
5. Forward to Calculator Service (/v1/calculate_import_taxes)
```

### Step 1b: Internal JSON Structure (Sent to Calculator)

After parsing, the system builds this structured request:

```json
{
  "calculation_date": "2026-04-01",
  "regime": "normal",
  "goods": {
    "hs_code": "0102.29.11",
    "origin_country": "CN",
    "description": "Live cattle (excluding buffalo)"
  },
  "valuation": {
    "customs_value": 800,
    "currency": "USD"
  }
}
```

**This JSON is NOT sent by the user** — it's created automatically from parsing the natural language question.

### Step 2: Calculator API Validates Request

```python
# api/endpoints.py → calculate_import_taxes()
# 1. Receive parsed JSON from Orchestrator
# 2. Convert to internal CalculationRequest
# 3. Call ImportTaxCalculator.calculate()
```

### Step 3: Calculator Orchestrates

```python
# core/calculator.py → ImportTaxCalculator.calculate()

1. Generate unique calculation_id
2. Validate inputs (HS code format, customs_value > 0, currency valid)
3. Convert customs_value to USD (if not already)
4. Lookup duty rates from Qdrant collection `gdce_hs_code` (172.25.3.243:6333)
   - Query: Retrieve Qdrant point by HS code ID
   - Returns: {"cd_rate": 0, "st_rate": 0, "vat_rate": 10, "et_rate": 0, ...}
5. Extract HS code info from same Qdrant point
   - Query: Point payload already contains description and unit
   - Returns: description="Live horses, asses, mules...", unit="u"
6. Determine calculation case (normal, petroleum, rubber, FTA)
7. Call appropriate calculation formula
   - Normal case: _calculate_normal_case()
```

8. Convert result to output currency (KHR)
9. Save calculation to database (audit trail)
10. Return CalculationResult

````

### Step 4: Formulas Calculate Taxes

```python
# core/formulas.py

For NORMAL CASE (most common):
═══════════════════════════════════

Input: HS code, CIF value (in USD or foreign currency), duty rates, origin country

**IMPORTANT: Currency Conversion Happens FIRST**

Step 1: Convert CIF to KHR (if not already in KHR)
   Exchange Rate: $1 USD = 4022 KHR (from PostgreSQL exchange_rates table)
   Formula: CIF_KHR = CIF_value_USD × EXCHANGE_RATE
   Calculation: $800 × 4022 = 3,217,600 KHR
   Rounding: Standard rounding to whole number → 3,217,600 KHR
   **All subsequent calculations use KHR values**

Step 2: Load Duty Rates from Qdrant
   ├─ cd_rate = 0       (0% customs duty - integers from Qdrant)
   ├─ st_rate = 0       (0% special tax)
   ├─ vat_rate = 10     (10% VAT)
   └─ et_rate = 0       (0% excise tax)
   **Convert rates: rate / 100 for calculations**
   ├─ cd_rate_decimal = 0 / 100 = 0.00
   ├─ st_rate_decimal = 0 / 100 = 0.00
   ├─ vat_rate_decimal = 10 / 100 = 0.10
   └─ et_rate_decimal = 0 / 100 = 0.00

Step 3: Customs Duty (CD) - calculated in KHR
   Formula: CD = CIF_KHR × cd_rate_decimal
   Calculation: 3,217,600 × 0.00 = 0
   Rounding: Standard rounding → 0 KHR
   Base for next tax: 3,217,600 KHR (CIF)

Step 4: Special Tax (ST) - calculated in KHR
   Formula: ST = CIF_KHR × st_rate_decimal
   Calculation: 3,217,600 × 0.00 = 0
   Rounding: Standard rounding → 0 KHR
   Base for next tax: 3,217,600 KHR (CIF)

Step 5: Subtotal (COP - Cost of Product) - in KHR
   Formula: COP = CIF_KHR + CD + ST
   Calculation: 3,217,600 + 0 + 0 = 3,217,600
   Rounding: Standard rounding → 3,217,600 KHR

Step 6: VAT (VOP - Value of Payment) - calculated in KHR
   Formula: VAT = COP × vat_rate_decimal
   Calculation: 3,217,600 × 0.10 = 321,760
   Rounding: Standard rounding → 321,760 KHR

Step 7: Excise Tax (ET) - calculated in KHR
   Formula: ET = CIF_KHR × et_rate_decimal
   Calculation: 3,217,600 × 0.00 = 0
   Rounding: Standard rounding → 0 KHR

Step 8: Total Taxes (all in KHR, no further conversion needed)
   Formula: TOTAL_KHR = CD + ST + VAT + ET
   Calculation: 0 + 0 + 321,760 + 0 = 321,760
   Rounding: CEILING to nearest 100 → 321,800 KHR

═══════════════════════════════════════════════════════════
FINAL ANSWER (Payment Amount) - All values in KHR
═══════════════════════════════════════════════════════════
• Customs Duty (CD):     0 KHR      (0% × 3,217,600)
• Special Tax (ST):      0 KHR      (0% × 3,217,600)
• VAT:                   321,760 KHR (10% × 3,217,600)
• Excise Tax (ET):       0 KHR      (0% × 3,217,600)
                         ────────   ──────────────
TOTAL TAXES:             321,760 KHR → 321,800 KHR ← PAYMENT AMOUNT (rounded to 100)

Original Value: $800 USD
Exchange Rate Used: 1 USD = 4,022 KHR
CIF Value in KHR: 3,217,600 KHR
````

---

## 📁 Data Sources

### 1. **HS Code & Duty Rates** → Qdrant Collection `gdce_hs_code`

**Server**: `172.25.3.243:6333`
**Dashboard**: `http://172.25.3.243:6333/dashboard#/collections/gdce_hs_code`

**Document Structure (Qdrant Point)**:

Each point in the collection represents an HS code with its duty rates:

```json
{
  "id": "0101.21.00",
  "vector": [0.234, 0.567, ...],
  "payload": {
    "hs_code": "0101.21.00",
    "description": "Live horses, asses, mules and hinnies. > Horses : …",
    "unit": "u",
    "cd_rate": 0,
    "st_rate": 0,
    "vat_rate": 10,
    "et_rate": 0
  }
}
```

**Payload Field Descriptions**:

| Field         | Type   | Description                                   | Example                                         |
| ------------- | ------ | --------------------------------------------- | ----------------------------------------------- |
| `hs_code`     | string | HS classification code with dots              | "0101.21.00"                                    |
| `description` | string | Full product description from tariff schedule | "Live horses, asses, mules..."                  |
| `unit`        | string | Unit of measurement                           | "u" (units), "kg" (kilograms), "head" (animals) |
| `cd_rate`     | number | Customs Duty rate (0-100)                     | 0, 15, 20                                       |
| `st_rate`     | number | Special Tax rate (0-100)                      | 0, 5, 30                                        |
| `vat_rate`    | number | VAT rate - typically 10 for Cambodia (0-100)  | 10                                              |
| `et_rate`     | number | Excise Tax rate (0-100)                       | 0, 10                                           |

**Rate Format & Conversion**:

Rates in Qdrant are stored as **integers (0-100)** representing percentages. The calculator must convert them to decimals for formula calculations:

```python
# Qdrant payload example: "cd_rate": 15 (means 15%)
# Calculator conversion:
qdrant_cd_rate = 15
decimal_cd_rate = qdrant_cd_rate / 100  # → 0.15
calculated_cd = cif_value * decimal_cd_rate  # 3,217,600 × 0.10 = 321,760
```

**How it's queried** (from `infrastructure/csv_database.py` via QdrantClient):

```python
# On startup: init_db.py connects to Qdrant
qdrant_client = QdrantClient(host="172.25.3.243", port=6333)

# Verify collection exists
collections = qdrant_client.get_collections()
# Should include: "gdce_hs_code" collection with duty rate documents

# On request: get_duty_rates(hs_code="0101.21.00")
1. Query Qdrant by HS code (point ID or payload filter)
2. Retrieve point payload
3. Extract: cd_rate, st_rate, vat_rate, et_rate
4. Return: {"hs_code": "0101.21.00", "cd_rate": 0, "st_rate": 0, "vat_rate": 10, "et_rate": 0}
5. If not found, return None or use fallback default rates
```

### 2. **HS Code Descriptions** → Same Qdrant Collection

**Query**: Retrieve point payload from Qdrant for HS code

```python
# Qdrant query (Point ID lookup)
point = qdrant_client.retrieve(
    collection_name="gdce_hs_code",
    ids=["0101.21.00"],
    with_payload=True
)

# Returns payload with all duty rate and HS info fields
returns: {
  "hs_code": "0101.21.00",
  "description": "Live horses, asses, mules and hinnies. > Horses : …",
  "unit": "u",
  "cd_rate": 0,
  "st_rate": 0,
  "vat_rate": 10,
  "et_rate": 0
}
```

### 3. **Exchange Rates** → PostgreSQL Remote Database

**Server**: `172.25.3.243` (same as Qdrant)
**Database**: `gdce_hs_code`
**Table**: `exchange_rates`

**Table Structure**:

```sql
CREATE TABLE exchange_rates (
    id SERIAL PRIMARY KEY,
    currency TEXT,
    usd_unit TEXT DEFAULT '1USD',
    foreign_rate NUMERIC(15, 4),
    foreign_unit TEXT,
    local_rate NUMERIC(15, 4),
    effective_date DATE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Example Data**:

```
id | currency | usd_unit | foreign_rate | foreign_unit | local_rate | effective_date | created_at
---|----------|----------|--------------|--------------|------------|----------------|-----------
1  | USD      | 1 USD    | 1.0          | 1 USD        | 4022.0     | 2026-04-01     | 2026-04-01
2  | EUR      | 1 USD    | 0.908        | 1 EUR        | 4400.0     | 2026-04-01     | 2026-04-01
3  | THB      | 1 USD    | 34.8         | 1 THB        | 115.0      | 2026-04-01     | 2026-04-01
```

**How it's queried** (from `infrastructure/exchange_rate_adapter.py`):

```python
# On startup: exchange_rate_adapter.py connects to PostgreSQL
conn = psycopg2.connect(
    host="172.25.3.243",
    database="gdce_hs_code",
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD")
)

# On request: get_exchange_rate(currency="USD")
1. Query PostgreSQL: SELECT local_rate
                    FROM exchange_rates
                    WHERE currency = 'US Dollar'
                    AND effective_date <= CURRENT_DATE
                    ORDER BY effective_date DESC
                    LIMIT 1;
2. Returns: 4022.0
3. Cache result for performance (TTL: 1 hour)
4. If not found, use fallback from config or raise error
```

### 4. **CSV Fallback (Legacy)**

For backwards compatibility, if Qdrant is unavailable:

- File: `data/raw/tables/Duty & Tax.csv`
- Fallback: CSVDatabase adapter in `infrastructure/csv_database.py`
- Usage: Only if Qdrant connection fails
- Status: Not recommended for production (use Qdrant instead)

---

## 🔍 Breakdown & Response Format

### Full Response Structure

```json
{
  "calculation_id": "calc_2026-04-01_hs0101_2100_141500_abc123",
  "query": "Calculate tax for HS 0101.21.00 CIF 800 USD from China",
  "currency": "KHR",
  "total": 321800,

  "conversion_step": {
    "original_value": 800,
    "original_currency": "USD",
    "exchange_rate": 4022.0,
    "converted_value": 3217600,
    "converted_currency": "KHR",
    "note": "Currency conversion happens FIRST before all tax calculations"
  },

  "breakdown": {
    "customs_duty": 0,
    "special_tax": 0,
    "vat": 321760,
    "excise_tax": 0,
    "total": 321760,
    "total_rounded": 321800
  },

  "line_items": [
    {
      "name": "Customs Duty (CD)",
      "tax_type": "CD",
      "base_khr": 3217600,
      "rate": 0,
      "rate_source": "Qdrant (0% for HS 0101.21.00)",
      "amount_khr": 0
    },
    {
      "name": "Special Tax (ST)",
      "tax_type": "ST",
      "base_khr": 3217600,
      "rate": 0,
      "rate_source": "Qdrant (0% for HS 0101.21.00)",
      "amount_khr": 0
    },
    {
      "name": "Cost of Product (COP)",
      "tax_type": "SUBTOTAL",
      "calculation": "CIF_KHR + CD + ST",
      "base_khr": 3217600,
      "amount_khr": 3217600,
      "note": "COP is used as base for VAT calculation"
    },
    {
      "name": "VAT",
      "tax_type": "VAT",
      "base_khr": 3217600,
      "rate": 0.1,
      "rate_source": "Qdrant (10% standard VAT for Cambodia)",
      "amount_khr": 321760
    },
    {
      "name": "Excise Tax (ET)",
      "tax_type": "ET",
      "base_khr": 3217600,
      "rate": 0,
      "rate_source": "Qdrant (0% for HS 0101.21.00)",
      "amount_khr": 0
    }
  ],

  "assumptions": [
    "Currency conversion applied first: $800 USD = 3,217,600 KHR",
    "All calculations performed in KHR (local currency)",
    "Exchange rate 1 USD = 4,022 KHR from PostgreSQL (172.25.3.243)",
    "HS code 0101.21.00 resolved to: Live horses, asses, mules",
    "Applied normal tariff regime (no preferential agreement)",
    "Duty rates retrieved from Qdrant collection gdce_hs_code"
  ],

  "references": [
    {
      "hs_code": "0101.21.00",
      "hs_description": "Live horses, asses, mules and hinnies. > Horses",
      "duty_source": "Qdrant (172.25.3.243:6333/collections/gdce_hs_code)",
      "exchange_source": "PostgreSQL (172.25.3.243 gdce_hs_code.exchange_rates)"
    }
  ],

  "summary": {
    "original_usd": 800.0,
    "converted_khr": 3217600.0,
    "total_tax_khr": 321760.0,
    "total_tax_rounded_khr": 321800.0,
    "rounding_applied": "CEILING to nearest 100 KHR"
  }
}
```

---

## 🧮 Special Calculation Cases

### Case 1: Normal Imports (Most Common)

```
Base: CIF value
Flow: CIF → CD → ST → (CIF+CD+ST) → VAT → Total
Used for: General merchandise, live animals, vegetables, etc.
```

### Case 2: Petroleum Products

```
Base: CIF value
Special handling: May apply surcharge or volume tax
Formula may differ from normal case
```

### Case 3: Rubber Products

```
Base: CIF value + quantity-based calculations
Applied to: Natural rubber, tyres, etc.
```

### Case 4: FTA (Free Trade Agreement)

```
Cases: ATIGA, ACFTA, CPTPP, etc.
Requirement: Valid Certificate of Origin (CoO)
Effect: Often 0% duty or preferential rates
Base: CIF value (same calculation but different rates)
```

---

## 🔧 Configuration

### Configuration Files Location: `calculator_version2/configs/`

The Calculator Service is **self-contained** — all JSON configuration files are bundled within the service directory:

```
calculator_version2/
└── configs/
    ├── calculator_config.json                    ← Tax rules, FTA agreements, exemptions
    ├── calculate_import_taxes.schema.json        ← Request/Response schema & critical rules
    ├── exchange_rate_policy.json                 ← Exchange rate lookup and selection rules
    ├── formula_registry.json                     ← Calculation formulas and constants
    └── rounding_rules.json                       ← Rounding precision and rules
```

### Configuration Files Reference

**1. `calculate_import_taxes.schema.json`** - Request Schema & Critical Rules

```json
{
  "documentation": {
    "purpose": "Input schema for import duty and tax calculator",
    "use_cases": [
      "Tax estimation",
      "Duty rate verification",
      "Total cost calculation"
    ],
    "applies_to": "Goods imported into Cambodia"
  },
  "critical_rules": [
    {
      "rule_id": "HS_LOOKUP",
      "sequence": 1,
      "description": "Resolve HS code to 8-digit format"
    },
    {
      "rule_id": "RATE_SELECTION",
      "sequence": 2,
      "description": "Determine applicable tax rates from Qdrant/CSV"
    },
    {
      "rule_id": "CURRENCY_CONVERSION",
      "sequence": 3,
      "description": "Convert CIF to KHR using exchange_rate_policy.json rates"
    },
    {
      "rule_id": "CALCULATION_AND_ROUNDING",
      "sequence": 4,
      "description": "Execute calculations per rounding_rules.json"
    }
  ]
}
```

**2. `exchange_rate_policy.json`** - Exchange Rate Selection

```json
{
  "policy": {
    "method": "fixed_table_from_csv",
    "data_source_primary": "data/processed/structured/exchange_rates_*.csv",
    "data_source_remote": "PostgreSQL @ 172.25.3.243 (gdce_hs_code.exchange_rates table)"
  },
  "rate_selection_rules": [
    {
      "rule_id": "RATE_BY_DECLARATION_DATE",
      "priority": 1,
      "description": "Use rate published for the customs declaration date"
    },
    {
      "rule_id": "FALLBACK_LATEST_RATE",
      "priority": 2,
      "description": "If no declaration date provided, use latest available rate"
    }
  ]
}
```

**3. `formula_registry.json`** - Calculation Formulas & Constants

```json
{
  "constants": {
    "vat_standard_rate": {
      "value": 0.1,
      "percentage": 10,
      "applies_to": "CIF + Import Duty + Special Tax + Excise Tax"
    },
    "rounding_mode": {
      "value": "CEILING",
      "applies_to": "All monetary calculations"
    }
  },
  "calculation_flow": [
    "step_1: Currency Conversion",
    "step_2: Rate Lookup from Qdrant",
    "step_3: Duty Calculation",
    "step_4: Special Tax Calculation",
    "step_5: VAT Calculation",
    "step_6: Final Rounding"
  ]
}
```

**4. `rounding_rules.json`** - Rounding Precision

```json
{
  "summary": {
    "principle": "All monetary amounts round UP to nearest 100 KHR (CEILING function)",
    "exceptions": "Quantities, rates, and exchange rates are NOT rounded - use exact values"
  },
  "rules": [
    {
      "rule_id": "RULE_001",
      "name": "Exchange Rate Precision",
      "rule": "DO NOT round - use exactly as published"
    },
    {
      "rule_id": "RULE_002",
      "name": "Currency Conversion Result",
      "rule": "Standard rounding to whole number"
    },
    {
      "rule_id": "RULE_003",
      "name": "Final Payment Amount",
      "rule": "CEILING to nearest 100 KHR"
    }
  ]
}
```

### Environment Variables (from `.env`)

```bash
# Calculator Service Port
CALCULATOR_HOST=127.0.0.1
CALCULATOR_PORT=8002

# Remote Qdrant Server (Duty Rates & HS Code Data)
QDRANT_HOST=172.27.3.162
QDRANT_PORT=6333
QDRANT_DUTY_COLLECTION=gdce_hs_code
# Dashboard: http://172.27.3.162:6333/dashboard#/collections/gdce_hs_code

# Remote PostgreSQL Server (Exchange Rates)
PG_HOST=172.27.3.162
PG_PORT=5432
PG_DATABASE=gdce_hs_code
PG_USER=postgres
PG_PASSWORD=postgres
PG_EXCHANGE_RATES_TABLE=exchange_rates

# Exchange Rate Fallback (for when PostgreSQL is unavailable)
# Format: CURRENCY_RATE_FALLBACK
USD_TO_KHR_RATE_FALLBACK=4022.0   # Backup: 1 USD = 4022 KHR
EXCHANGE_RATE_CACHE_TTL=3600      # Cache duration in seconds (1 hour)

# CSV Fallback (Legacy - only if both Qdrant and PostgreSQL fail)
# CSV file at: data/raw/tables/Duty & Tax.csv
# Status: Not recommended for production
```

---

## 📊 Formulas Implemented

### Core Tax Formulas

```python
✓ calculate_import_duty()          # CD = CIF × duty_rate
✓ calculate_preferential_duty()    # Lower rate with CoO
✓ calculate_duty_exemption()       # = 0 with exemption cert
✓ calculate_special_tax()          # ST = CIF × st_rate
✓ calculate_vat()                  # VAT = (CIF+CD+ST) × 0.10
✓ calculate_excise_tax()           # ET = CIF × et_rate
✓ calculate_acfta_duty()           # ACFTA: 0%
✓ calculate_atiga_duty()           # ATIGA: 0%
✓ calculate_cptpp_duty()           # CPTPP: Preferential
✓ calculate_cef_duty()             # CEF: Preferential
```

### Rounding

```python
✓ round_to_whole_number()          # HALF_UP for tax bases
✓ round_up_to_hundred()            # CEILING to 100s for final payment
```

### CIF Calculation

```python
✓ calculate_cif_value()            # CIF = FOB + Freight + Insurance
✓ calculate_dv_declared_value()    # DV for imports from specific origins
```

---

## 🚀 Usage Examples

### 💬 How Users Actually Ask (Chat Interface)

---

**User Question 1:** "Calculate tax for HS 0102.29.11 CIF $800 from China"

#### Step 1: Extract Essential Information

```
User Input:
├─ HS Code: 0102.29.11
├─ CIF Value: $800 USD
├─ Origin Country: China (CN)
└─ Currency: USD

Query Qdrant Collection (gdce_hs_code):
├─ HS Description: "Live horses, asses, mules and hinnies. > Horses"
├─ Duty Rates Retrieved:
│  ├─ cd_rate: 0 (0% Customs Duty)
│  ├─ st_rate: 0 (0% Special Tax)
│  ├─ vat_rate: 10 (10% VAT)
│  └─ et_rate: 0 (0% Excise Tax)
└─ Unit: "u" (units/head)

Query PostgreSQL (exchange_rates):
├─ Currency: USD
├─ Local Rate: 4022.0 KHR
├─ Effective Date: 2026-04-01
└─ Source: 172.27.3.162 gdce_hs_code.exchange_rates

Case Classification: NORMAL IMPORT (non-petroleum, non-rubber, no FTA)
```

#### Step 2: Calculate CIF in Local Currency

```
Formula: CIF_KHR = CIF_USD × Exchange_Rate
         CIF_KHR = 800 × 4022
         CIF_KHR = 3,217,600 KHR
```

#### Step 3: Convert Rates to Decimals

```
Formula: decimal_rate = integer_rate / 100

cd_rate_decimal = 0 / 100 = 0.00
st_rate_decimal = 0 / 100 = 0.00
vat_rate_decimal = 10 / 100 = 0.10
et_rate_decimal = 0 / 100 = 0.00
```

#### Step 4: Calculate Each Tax Component

```
Step 4a — Customs Duty (CD):
Formula: CD = CIF_KHR × cd_rate_decimal
Calculation: CD = 3,217,600 × 0.00 = 0 KHR

Step 4b — Special Tax (ST):
Formula: ST = CIF_KHR × st_rate_decimal
Calculation: ST = 3,217,600 × 0.00 = 0 KHR

Step 4c — Cost of Product (COP):
Formula: COP = CIF_KHR + CD + ST
Calculation: COP = 3,217,600 + 0 + 0 = 3,217,600 KHR

Step 4d — VAT:
Formula: VAT = COP × vat_rate_decimal
Calculation: VAT = 3,217,600 × 0.10 = 321,760 KHR

Step 4e — Excise Tax (ET):
Formula: ET = CIF_KHR × et_rate_decimal
Calculation: ET = 3,217,600 × 0.00 = 0 KHR

Step 4f — Total Taxes:
Formula: TOTAL_TAXES = CD + ST + VAT + ET
Calculation: TOTAL_TAXES = 0 + 0 + 321,760 + 0 = 321,760 KHR
Rounding: CEILING to 100 → 321,800 KHR
```

#### Response to User

```json
{
  "user_query": "Calculate tax for HS 0102.29.11 CIF $800 from China",
  "calculation_id": "calc_2026-04-01_hs0102-2900_800usd",

  "input_summary": {
    "hs_code": "0102.29.11",
    "product": "Live horses, asses, mules and hinnies",
    "cif_value_usd": 800.0,
    "origin_country": "China (CN)",
    "calculation_case": "NORMAL IMPORT"
  },

  "exchange_rate": {
    "rate": 4022.0,
    "from_currency": "USD",
    "to_currency": "KHR",
    "source": "PostgreSQL (172.25.3.243 gdce_hs_code)",
    "effective_date": "2026-04-01"
  },

  "duty_rates": {
    "customs_duty_rate": 0,
    "special_tax_rate": 0,
    "vat_rate": 10,
    "excise_tax_rate": 0,
    "source": "Qdrant (172.25.3.243:6333 gdce_hs_code collection)"
  },

  "calculation_breakdown": {
    "cif_khr": 3217600,
    "customs_duty": 0,
    "special_tax": 0,
    "cost_of_product": 3217600,
    "vat": 321760,
    "excise_tax": 0,
    "total_taxes_before_rounding": 321760,
    "total_taxes_rounded": 321800
  },

  "payment_amount": "321,800 KHR",
  "breakdown_detailed": [
    {
      "item": "Customs Duty (CD)",
      "rate": "0%",
      "base_khR": 3217600,
      "amount_khr": 0
    },
    {
      "item": "Special Tax (ST)",
      "rate": "0%",
      "base_khr": 3217600,
      "amount_khr": 0
    },
    { "item": "VAT", "rate": "10%", "base_khr": 3217600, "amount_khr": 321760 },
    {
      "item": "Excise Tax (ET)",
      "rate": "0%",
      "base_khr": 3217600,
      "amount_khr": 0
    }
  ]
}
```

**Answer:** ✓ **Total Tax: 321,800 KHR** (rounded from 321,760 KHR)

- Customs Duty: 0 KHR (0%)
- Special Tax: 0 KHR (0%)
- VAT: 321,760 KHR (10%)
- Excise Tax: 0 KHR (0%)

---

**User Question 2:** "Calculate tax for Oxen CIF 800 USD from China"

#### System Workflow

```
1. User provides product name "Oxen" (no HS code given)
2. Orchestrator calls Retrieval Service to find HS code
   └─ Query: "Oxen from China"
   └─ Returns: HS 0102.29.11 (Live cattle excluding buffalo)
3. Proceeds with calculation using HS 0102.29.11 (same as Question 1)
4. Returns identical response to Question 1
```

**Answer:** ✓ **Total Tax: 321,800 KHR**

- Same breakdown as Question 1 (HS 0102.29.11 resolved automatically)
- Note: "Auto-detected HS code 0102.29.11 for Oxen/Live cattle"

---

**User Question 3:** "Calculate tax for Honda Dream CIF 2000 USD from China"

#### Step 1: Extract Essential Information

```
User Input:
├─ Product Name: Honda Dream (motorcycle)
├─ CIF Value: $2000 USD
├─ Origin Country: China (CN)
└─ Currency: USD

Retrieval Service Lookup: "Honda Dream"
└─ Returns: HS 8711.30.10 (Motorcycles > 50cc, 2-wheelers, n.e.c.)

Query Qdrant Collection (gdce_hs_code):
├─ HS Description: "Motorcycles, 2-wheelers > 50cc (not elsewhere classified)"
├─ Duty Rates Retrieved:
│  ├─ cd_rate: 20 (20% Customs Duty)
│  ├─ st_rate: 0 (0% Special Tax)
│  ├─ vat_rate: 10 (10% VAT)
│  └─ et_rate: 0 (0% Excise Tax)
└─ Unit: "u" (units)

Query PostgreSQL (exchange_rates):
├─ Currency: USD
├─ Local Rate: 4022.0 KHR
└─ Source: 172.27.3.162 gdce_hs_code.exchange_rates

Case Classification: NORMAL IMPORT
```

#### Step 2: Calculate CIF in Local Currency

```
Formula: CIF_KHR = CIF_USD × Exchange_Rate
         CIF_KHR = 2000 × 4022
         CIF_KHR = 8,044,000 KHR
```

#### Step 3: Convert Rates to Decimals & Calculate Taxes

```
cd_rate_decimal = 20 / 100 = 0.20
st_rate_decimal = 0 / 100 = 0.00
vat_rate_decimal = 10 / 100 = 0.10
et_rate_decimal = 0 / 100 = 0.00

Step 4a — Customs Duty (CD):
Formula: CD = CIF_KHR × cd_rate_decimal
Calculation: CD = 8,044,000 × 0.20 = 1,608,800 KHR

Step 4b — Special Tax (ST):
Formula: ST = CIF_KHR × st_rate_decimal
Calculation: ST = 8,044,000 × 0.00 = 0 KHR

Step 4c — Cost of Product (COP):
Formula: COP = CIF_KHR + CD + ST
Calculation: COP = 8,044,000 + 1,608,800 + 0 = 9,652,800 KHR

Step 4d — VAT:
Formula: VAT = COP × vat_rate_decimal
Calculation: VAT = 9,652,800 × 0.10 = 965,280 KHR

Step 4e — Excise Tax (ET):
Formula: ET = CIF_KHR × et_rate_decimal
Calculation: ET = 8,044,000 × 0.00 = 0 KHR

Step 4f — Total Taxes:
Formula: TOTAL_TAXES = CD + ST + VAT + ET
Calculation: TOTAL_TAXES = 1,608,800 + 0 + 965,280 + 0 = 2,574,080 KHR
Rounding: CEILING to 100 → 2,574,100 KHR
```

**Answer:** ✓ **Total Tax: 2,574,100 KHR**

- Customs Duty: 1,608,800 KHR (20%)
- Special Tax: 0 KHR (0%)
- VAT: 965,280 KHR (10% of COP 9,652,800)
- Excise Tax: 0 KHR (0%)
- Note: "Auto-detected HS code 8711.30.10 for Honda Dream motorcycle"

---

### 🔧 Technical API Examples (for Developers)

#### Example 1A: Direct Calculator API Call

```bash
# Call Calculator Service directly (after Orchestrator parses question)
curl -X POST http://localhost:8002/v1/calculate_import_taxes \
  -H "Content-Type: application/json" \
  -d '{
    "calculation_date": "2026-04-01",
    "regime": "normal",
    "goods": {
      "hs_code": "0102.29.11",
      "origin_country": "CN",
      "description": "Live cattle"
    },
    "valuation": {
      "customs_value": 800,
      "currency": "USD"
    }
  }'

# Returns:
{
  "total": 852700,  # KHR (final payment amount)
  "breakdown": {
    "customs_duty": 482640,
    "special_tax": 0,
    "vat": 369024,
    "excise_tax": 0,
    "total": 852700
  },
  "line_items": [
    {
      "name": "Customs Duty",
      "tax_type": "CD",
      "base": 800,
      "rate": 0.15,
      "amount": 482640
    }
  ]
}
```

### Example 1B: Duty Rate Lookup (API)

```bash
# Retrieve duty rates for a specific HS code
curl "http://localhost:8002/v1/lookup/duty-rate?hs_code=0102.29.11&origin_country=CN"

# Returns:
{
  "found": true,
  "hs_code": "0102.29.11",
  "rates": {
    "cd_rate": 0.15,
    "st_rate": 0.00,
    "vat_rate": 0.10,
    "et_rate": 0.00
  },
  "hs_info": {
    "description": "Live cattle",
    "unit": "head"
  }
}
```

### Example 2: HS Code Lookup by Product (API)

```bash
# When user asks about "tomato from Thailand"
# Orchestrator calls this to find the HS code
curl -X POST http://localhost:8002/v1/lookup/hs-code-from-product \
  -H "Content-Type: application/json" \
  -d '{"product_description": "tomato from Thailand"}'

# Returns:
{
  "found": true,
  "hs_code": "0702.00.00",
  "confidence": 0.92,
  "duty_rates": {
    "cd_rate": 0.20,
    "vat_rate": 0.10
  }
}
```

---

## 🔍 Debugging & Troubleshooting

### Issue: HS Code Not Found

```bash
# Check Qdrant connection
curl http://172.25.3.243:6333/health
# Should return: {"status": "ok"}

# Check collection at Qdrant dashboard
http://172.25.3.243:6333/dashboard#/collections/gdce_hs_code

# Check if HS code exists in collection
curl -X POST http://172.25.3.243:6333/collections/gdce_hs_code/points/search \
  -H "Content-Type: application/json" \
  -d '{"vector": [0.1, 0.2, ...], "limit": 1}'

# Verify Calculator health (checks Qdrant connection)
curl http://localhost:8002/v1/health
# Look for: "qdrant_connected": true
```

### Issue: Wrong Exchange Rate

```bash
# Check PostgreSQL connection
psql -h 172.25.3.243 -U postgres -d gdce_hs_code

# Query exchange rates table
SELECT * FROM exchange_rates
WHERE currency = 'USD'
ORDER BY effective_date DESC LIMIT 5;

# Verify exchange rate endpoint
curl "http://localhost:8002/v1/lookup/exchange-rate?currency=USD"
# Returns: {"currency": "USD", "rate": 4022.0, "source": "postgresql"}

# If PostgreSQL is down, check fallback config
grep USD_TO_KHR_RATE_FALLBACK .env
# Should show backup rate for emergency use
```

### Issue: VAT Calculation Wrong

```bash
# VAT formula: (CIF + CD + ST) × 10%
# NOT: CIF × 10%

# Example:
CIF = $800
CD = $120
ST = $0
VAT = ($800 + $120 + $0) × 0.10 = $92  ← Correct
NOT: $800 × 0.10 = $80                 ← Wrong
```

---

## 📈 Next Steps (Phase 2/3)

- [ ] Replace CSV with PostgreSQL for duty rates
- [ ] Add Qdrant semantic search for HS code descriptions
- [ ] Implement preferential agreement automation (detect CoO type)
- [ ] Add historical rate lookups
- [ ] Implement calculation audit logging
- [ ] Add batch calculation endpoint
- [ ] Support for multi-item shipments

---

## 📞 Quick Reference

| Need                 | Endpoint                               | Example               |
| -------------------- | -------------------------------------- | --------------------- |
| Calculate taxes      | POST `/v1/calculate_import_taxes`      | See Example 1         |
| Check duty rate      | GET `/v1/lookup/duty-rate`             | `?hs_code=0102.29.11` |
| Check HS info        | GET `/v1/lookup/hs-info`               | `?hs_code=0702.00.00` |
| Find HS from product | POST `/v1/lookup/hs-code-from-product` | See Example 3         |
| Get exchange rate    | GET `/v1/lookup/exchange-rate`         | `?currency=USD`       |
| Health check         | GET `/v1/health`                       | Returns status        |
| API docs             | GET `/docs`                            | Swagger UI            |
