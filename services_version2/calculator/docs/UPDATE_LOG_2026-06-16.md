# Calculator Service Update Log — 2026-06-16

## Summary

All petroleum tax calculation logic, database formulas, and data sources were updated to match the Cambodian SAD (Single Administrative Document) system. The calculator service is now fully standalone using `gdce_calculator` as its sole PostgreSQL database.

---

## 1. Petroleum Calculation Fixes

### Phase 1 vs Phase 2 Logic
- **Importer always pays Phase 1 total** regardless of Phase 2 comparison.
- DPP (Differential Petroleum Price) is **informational only** — handled separately by the state.
- `total_payable` now hardcoded to equal Phase 1 total.

### DPP Display
- DPP shown as a **positive number** with conditional label:
  - Phase 2 > Phase 1: **"Additional charge (DPP)"**
  - Phase 1 > Phase 2: **"Subsidy by the state (DPP)"**
  - Equal: **"No difference between phases (DPP)"**
- Table rows render dashes (`—`) in base/rate columns for DPP.

### SAD Rounding (Double Rounding)
All petroleum tax components now use:
```
ROUND to whole number → CEILING to nearest 100
```
Applied to: **CPP, ATP, SPP, VPP, COP, SOP, VOP**

### Formula Changes in `core/formulas.py`
```python
def calculate_petroleum_phase1_cpp(cpp_base, cpp_rate):
    cpp = Decimal(str(cpp_base)) * Decimal(str(cpp_rate))
    return round_up_to_hundred(round_to_whole_number(cpp))

def calculate_petroleum_phase1_atp(atp_base, atp_rate, exchange_rate):
    atp = Decimal(str(atp_base)) * Decimal(str(atp_rate)) * Decimal(str(exchange_rate))
    return round_up_to_hundred(round_to_whole_number(atp))

def calculate_petroleum_phase1_spp(cpp_base, cpp_amount, atp_amount, spp_rate):
    base = Decimal(str(cpp_base)) + Decimal(str(cpp_amount)) + Decimal(str(atp_amount))
    spp = base * Decimal(str(spp_rate))
    return round_up_to_hundred(round_to_whole_number(spp))

def calculate_petroleum_phase1_vpp(vpp_base, vpp_rate):
    vpp = Decimal(str(vpp_base)) * Decimal(str(vpp_rate))
    return round_up_to_hundred(round_to_whole_number(vpp))

def calculate_petroleum_dpp(phase1_total, phase2_total):
    return ABS(phase1_total - phase2_total)  # was MAX(0, diff)
```

### Verified SAD Example (HS 27101226)
| Component | Value (KHR) |
|-----------|-------------|
| CIF | 1,586,135,071 |
| CPP | 107,779,800 |
| ATP | 54,536,736 |
| SPP | 162,316,500 |
| VPP | 181,076,800 |
| **Phase 1 Total** | **690,812,000** |
| Phase 2 Total | 621,706,400 |
| **DPP** | **69,105,600** |
| **Total Payable** | **690,812,000** |

---

## 2. Formula Registry JSON Updates

File: `configs/formula_registry.json`

- Updated petroleum formulas with `rounding` field: **"ROUND to whole number, then CEILING to nearest 100"**
- Updated `petroleum_case.final` to document importer always pays Phase 1.
- Updated DPP description to clarify it's informational only.
- Updated DPP acronym definition.

---

## 3. Database Formula Updates (`gdce_calculator`)

### `formulas` Table

| Formula ID | Before | After |
|-----------|--------|-------|
| **PF_001** | `max(cpp, atp, spp, vpp) - dpp` | `cpp_amount + atp_amount + spp_amount + vpp_amount` |
| **PF_002** | `cpp2 + atp2 + spp2 + vpp2` | `cpp2_amount + atp2_amount + spp2_amount + vpp2_amount` |
| **DPP_001** | `phase1_total - phase2_total` | `ABS(phase1_total - phase2_total)` |
| **CPP_001** | no rounding note | Added "round to whole, then CEILING_100" |
| **ATP_001** | no rounding note | Added "round to whole, then CEILING_100" |
| **SPP_001** | no rounding note | Added "round to whole, then CEILING_100" |
| **VPP_001** | no rounding note | Added "round to whole, then CEILING_100" |

### `rounding_rules` Table

- **RR_003** expanded `applies_to` to include petroleum components: `cpp_amount`, `atp_amount`, `spp_amount`, `vpp_amount`
- **RR_007** added: dedicated "Petroleum Tax Components" rounding rule with `CEILING_100`

---

## 4. FTA Car Case Verified (HS 87032259, ACFTA)

Verified the calculator correctly handles the FTA base-buildup logic:
- Original COP for base build-up uses MFN rate (35%).
- Payable COP uses preferential FTA rate (0%).
- SPP base = CIF + Original COP (not zero).
- Result matches SAD when XR = 4061.

| Component | Value (KHR) |
|-----------|-------------|
| CIF | 42,640,500 |
| COP (payable) | 0 |
| SPP base | 57,564,700 |
| SPP | 28,782,400 |
| VOP base | 86,347,100 |
| VOP | 8,634,800 |
| **Total Payable** | **37,477,200** |

---

## 5. Database Sync — `gdce_hs_code` → `gdce_calculator`

### Tables Copied

| Table | Rows | Notes |
|-------|------|-------|
| `preferential_rates` | 2,906 | FTA rates (ACFTA, ATIGA, AANZFTA, etc.) |
| `customs_fees` | 5 | Scanner fees, storage fees |
| `tax_rates` | 34 | CD/ST/VAT rate catalog |
| `duty_rates` (delta) | 5 | Missing HS codes |

### Exchange Rates Updated
- South Africa Rand (`SOU`) added: `foreign=15.8972`, `local=253.0`

### `gdce_calculator` Final State

| Table | Rows |
|-------|------|
| `formulas` | 22 |
| `rounding_rules` | 7 |
| `declared_values` | 14 |
| `preferential_rates` | 2,906 |
| `customs_fees` | 5 |
| `tax_rates` | 34 |
| `duty_rates` | 11,417 |
| `exchange_rates` | 28 |
| `hs_codes` | 11,414 |
| `exemptions` | 7 |
| `calculation_history` | 81 |

---

## 6. Description → HS Code Auto-Resolution (Semantic Search)

### Problem
When a user sent a natural-language query like *"calculate import tax for car value 200000usd"*, the calculator extracted `description="car"` and `customs_value=200000` but **could not calculate** because no HS code was present. The service returned an error or empty result.

### Solution
In the `/calculate_import_taxes/nl` endpoint (`api/endpoints.py`), if the user provides a **commercial description but no HS code**, the calculator now:

1. **Queries Qdrant via semantic search** (`db.search_hs_by_description(desc, top_k=1)`)
   - Uses the existing `all-MiniLM-L6-v2` embeddings in the `gdce_hs_code` collection
   - Finds the closest HS code match for the description (e.g., "car" → `8703.22.11`)
2. **Falls back to CSV keyword search** if Qdrant is unavailable or returns nothing
3. **Injects the resolved HS code** into the request before calculation
4. **Adds an assumption** to the response so the user knows the HS code was inferred

### `infrastructure/qdrant_client.py`
- Added `_get_embedder()` — lazy-loads `SentenceTransformer`
- Added `search_by_description(query, top_k=None)` — vector-encodes the query and searches Qdrant
  - Returns `(hs_code, score)` tuple when `top_k` is `None` (legacy-compatible)
  - Returns `List[dict]` when `top_k` is provided
- Added `get_candidates(query, limit=5)` — thin wrapper returning candidate list
- Model name configurable via `QDRANT_EMBEDDING_MODEL` env var (defaults to `all-MiniLM-L6-v2`)

### Example
**User query:** `calculate import tax for car value 200000usd`

**Before:**
```json
{"success": false, "error": "Could not extract calculation parameters..."}
```

**After:**
```json
{
  "success": true,
  "result": { "total": 27136000.00, ... },
  "assumptions": [
    "HS code 8703.22.11 was inferred from the product description 'Motor cars and other motor vehicles' via semantic search because no HS code was provided."
  ]
}
```

---

## 7. Environment & Code Changes

### `.env`
```
CALCULATOR_LEGACY_MODE=true → false
```

### `exchange_rate_adapter.py`
- Default database changed from `gdce_hs_code` → `gdce_calculator`
- Now reads `CALCULATOR_DB_*` env vars first, then falls back to `POSTGRES_*`

### `rules_database.py`
- Default database changed from `customs_ai` → `gdce_calculator`
- Now reads `CALCULATOR_DB_*` env vars first

### `unified_database.py`
- Comments/log messages cleaned up to remove `gdce_hs_code` references
- Legacy mode still supported via env var but now defaults to `false`

### `qdrant_client.py`
- Docstring updated: Qdrant is for **semantic search only**
- Duty rates and formulas come from calculator DB

---

## Files Modified

```
services_version2/calculator_version2/
├── .env
├── api/endpoints.py
├── core/calculator.py
├── core/formulas.py
├── core/llm_formatter.py
├── configs/formula_registry.json
├── configs/rounding_rules.json
├── infrastructure/
│   ├── exchange_rate_adapter.py
│   ├── rules_database.py
│   ├── unified_database.py
│   └── qdrant_client.py
└── tests/test_formulas.py
```

---

## Action Required

Restart the calculator service to apply all changes:
```powershell
# In PowerShell
./service_scripts/calculator_scripts/start_calculator_v2.ps1
```

Or verify the DB is the only source:
```bash
python -m pytest services_version2/calculator_version2/tests/test_formulas.py -v
```
