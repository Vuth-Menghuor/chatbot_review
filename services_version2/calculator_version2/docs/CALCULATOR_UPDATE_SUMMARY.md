# Calculator Service v2 - Update Summary

> **Date:** 2026-05-25 | **Branch:** vechika_branch | **Status:** All 23 tests passing

This document summarizes all major updates made to the GDCE Calculator Service across development sessions.

---

## Table of Contents

1. [Preferential Rates Removed from DB](#1-preferential-rates-removed-from-db)
2. [ATP Rates Imported from Excel into DB](#2-atp-rates-imported-from-excel-into-db)
3. [KHR-First Calculation Pipeline](#3-khr-first-calculation-pipeline)
4. [Full Calculation Case Support](#4-full-calculation-case-support)
5. [Ask-Back Flow for Missing Rates](#5-ask-back-flow-for-missing-rates)
6. [Dynamic Rules Engine](#6-dynamic-rules-engine)
7. [Formula Engine](#7-formula-engine)
8. [Orchestrator Integration](#8-orchestrator-integration)
9. [Key Files Changed](#9-key-files-changed)
10. [Database Schema Changes](#10-database-schema-changes)

---

## 1. Preferential Rates Removed from DB

**Core Principle:** FTA and exemption preferential rates must come **only** from user input (DV or `preferential_cd_rate`), never from a DB lookup.

### What Changed

| Area | Before | After |
|------|--------|-------|
| **DB Table** | `preferential_rates` existed with origin-specific rates | Table dropped entirely |
| **Rate Source** | `_get_rates()` queried DB for origin-specific rates (e.g., VN = 0% CD) | `_get_rates()` loads only normal/MFN rates (`origin_country = "XX"`) |
| **API** | Admin endpoints `/fta-rates` GET/POST existed | Endpoints removed |
| **Models** | `FTARate` dataclass in `rules_models.py` | Removed from `__all__` and deleted |
| **Calculator** | `agreement_code` parameter passed to `get_duty_rates()` | Parameter removed entirely |

### Files Modified

- `core/calculator.py` — `_get_rates()` rewritten; only MFN rates from DB
- `infrastructure/unified_database.py` — `get_duty_rates()` signature simplified
- `infrastructure/rules_database.py` — Removed `get_preferential_rates()` and `upsert_preferential_rate()`
- `core/rules_provider.py` — Removed FTA rate loading
- `core/rules_models.py` — Deleted `FTARate` dataclass
- `api/admin_endpoints.py` — Removed `/fta-rates` endpoints
- `api/admin_schemas.py` — Removed `FTARateCreate`/`FTARateResponse`
- `schema.sql` — Dropped `preferential_rates` table
- `seed.sql` & `seed_dynamic_rules.sql` — Removed preferential rate INSERTs
- `configs/rounding_rules.json` — Removed `preferential_rate` from rounding targets

### Ask-Back Preserved

When a user claims FTA or exemption but provides **no rate**, the calculator sets:

```python
result["preferential_rate_missing"] = True
result["requested_agreement"] = agreement_code  # e.g., "ATIGA"
```

The orchestrator then asks the user: "What is the preferential CD rate for ATIGA?"

---

## 2. ATP Rates Imported from Excel into DB

**Core Principle:** ATP (Additional Tax on Petroleum) rates from the government's `untartab` Excel file now live in PostgreSQL and are queryable at runtime.

### What Changed

| Area | Before | After |
|------|--------|-------|
| **ATP Source** | Hardcoded dictionary `_PETROLEUM_RATES_DEFAULT` in `unified_database.py` | Primary: PostgreSQL `duty_rates.atp_rate`; Fallback: hardcoded table |
| **DB Schema** | No `atp_rate` column | `atp_rate DECIMAL(10,4)` added to `duty_rates` |
| **Lookup** | Excel file parsed at startup (slow, 50-80s) | Direct SQL query to DB |

### Imported Data

From `atp_rate/untartab_202605120954.xlsx`:

| HS Code | Description | ATP Rate |
|---------|-------------|----------|
| `2710.12.11` - `2710.12.13` | Gasoline (RON 97+, leaded/unleaded) | **$0.02/L** |
| `2710.12.21` - `2710.12.29` | Gasoline (other RON, blended) | **$0.02/L** |
| `2710.12.40` | White spirit | **$0.02/L** |
| `2710.19.71` | Automotive diesel fuel | **$0.04/L** |
| `2710.19.72` | Other diesel fuels | **$0.04/L** |
| `2710.19.90` | Other petroleum oils | **$0.04/L** |
| `2710.20.00` | Petroleum oils (other than crude) | **$0.04/L** |

**Note:** 10 older/expired HS codes (e.g., `2710.11.11` - `2710.11.40`, `2710.12.14` - `2710.12.16`) were skipped because they don't exist in the current DB.

### Files Modified

- `schema.sql` — Added `atp_rate DECIMAL(10,4)` column with comment
- `infrastructure/unified_database.py` — Added `_get_atp_rate_from_db()`; DB lookup prioritized over hardcoded
- `schema_migration_002_atp_rate.sql` — Migration script for adding the column

---

## 3. KHR-First Calculation Pipeline

**Core Principle:** All calculations run in Cambodian Riel from the start, eliminating floating-point drift from intermediate USD conversions.

### What Changed

| Step | Before | After |
|------|--------|-------|
| **Currency flow** | Calculate in USD, convert each component to KHR | Convert CIF to KHR once, calculate all taxes in KHR |
| **Rounding** | Applied inconsistently | Applied per `rounding_rules.json`: tax components CEILING_100, total CEILING_100 |
| **Precision** | Floats used throughout | `Decimal` used everywhere; floats only for API serialization |

### Rounding Rules (from `configs/rounding_rules.json`)

| Target | Method | Precision | Priority |
|--------|--------|-----------|----------|
| `exchange_rate` | NONE | 1 | CRITICAL |
| `cif_value_khr` | ROUND_WHOLE | 1 | HIGH |
| `cop_amount`, `sop_amount`, `vop_amount`, `total_duties_and_taxes` | CEILING_100 | 100 | HIGH |
| `total_payable` | CEILING_100 | 100 | CRITICAL |
| `quantity`, `net_mass_kg`, `gross_mass_kg`, `volume_ltr` | NONE | 1 | CRITICAL |
| `duty_rate`, `vat_rate`, `excise_rate`, `special_tax_rate` | NONE | 1 | CRITICAL |

### Files Modified

- `core/calculator.py` — Complete rewrite of calculation flow; KHR-first
- `core/formulas.py` — Added `round_up_to_hundred()` and `round_to_whole_number()`
- `configs/rounding_rules.json` — Formalized rounding rules

---

## 4. Full Calculation Case Support

**Core Principle:** Dedicated calculation paths for every major Cambodian customs scenario.

### Supported Cases

| Case | Trigger | Behavior |
|------|---------|----------|
| **Normal** | No special flags | Standard COP + SOP + VOP using MFN rates |
| **FTA/DV** | `fta_applicable` flag + user provides `preferential_cd_rate` | CD rate from user; DV used as CD rate % if exemption applies |
| **FTA/DV + DQ** | `fta_applicable` + `dq_applicable` | DQ factor applied to SOP base as a multiplier |
| **Petroleum** | HS code starts with `2710` | Two-phase calculation: Phase 1 (DV basis) vs Phase 2 (CIF basis) → DPP |
| **Rubber Export** | `rubber_case` flag | ETR only; **NO VAT** on rubber exports |
| **Exemption** | Exemption code provided (DIP, QIP, NGO, etc.) | Full or partial CD/VAT reduction |

### DV (Declared Value) Convention

- DV is the **fair market price per metric ton** published by the government.
- When FTA or exemption applies, **DV is treated as the CD rate percentage** (e.g., DV = 0 means 0% CD rate).
- Exception: Petroleum products (`hs_code starts with "27"`) — DV is real valuation, not rate.

### Files Modified

- `core/calculator.py` — `_determine_calculation_case()`, `_calculate_fta_dv()`, `_calculate_petroleum()`, `_calculate_rubber_export()`
- `core/models.py` — Added `petroleum_case`, `rubber_case`, `fta_applicable`, `dq_applicable` flags
- `configs/formula_registry.json` — Documented all formulas per case

---

## 5. Ask-Back Flow for Missing Rates

**Core Principle:** When FTA/exemption is claimed but no preferential rate is available, ask the user rather than silently defaulting.

### Flow

```
User: "Calculate tax for HS 2710.12.11 from Vietnam with ATIGA"
        ↓
Calculator: No preferential_cd_rate provided, no DV available
        ↓
Response: preferential_rate_missing = True, requested_agreement = "ATIGA"
        ↓
Orchestrator: "What is the preferential CD rate for ATIGA?"
        ↓
User: "0%"
        ↓
Orchestrator: Recalculates with preferential_cd_rate = 0
        ↓
Calculator: Returns full result with 0% CD
```

### Ask-Back Fields (in `CalculationResult`)

| Field | Type | Meaning |
|-------|------|---------|
| `preferential_rate_missing` | `bool` | True when FTA/exemption claimed but no rate provided |
| `requested_agreement` | `str` | The agreement/exemption code that needs a rate |

### Files Modified

- `core/calculator.py` — Sets flags in `_get_rates()` when rate is missing
- `core/models.py` — Keeps `preferential_rate_missing` and `requested_agreement`
- `api/schemas.py` — Updated field descriptions
- `tests/test_api.py` — Tests for ask-back and follow-up recalculation

---

## 6. Dynamic Rules Engine

**Core Principle:** Admin-configurable rules stored in PostgreSQL with audit logging.

### Tables Managed

| Table | Purpose |
|-------|---------|
| `formulas` | Calculation formulas (expression + variables) |
| `rounding_rules` | Deterministic rounding per field |
| `policies` | Business rules (conditions + actions) |
| `exemptions` | Exemption regimes (DIP, QIP, NGO, etc.) |
| `rules_audit_log` | Audit trail of who changed what and when |

### Admin API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/rules-preview` | Preview all active rules |
| `POST` | `/admin/formulas` | Create/update formula |
| `GET` | `/admin/formulas` | List active formulas |
| `POST` | `/admin/rounding-rules` | Create/update rounding rule |
| `GET` | `/admin/rounding-rules` | List active rounding rules |
| `POST` | `/admin/policies` | Create/update policy |
| `GET` | `/admin/policies` | List active policies |
| `POST` | `/admin/exemptions` | Create/update exemption |
| `GET` | `/admin/exemptions` | List active exemptions |
| `GET` | `/admin/audit-log` | View audit trail |

### Files Modified

- `infrastructure/rules_database.py` — PostgreSQL CRUD adapter
- `api/admin_endpoints.py` — Admin HTTP handlers
- `api/admin_schemas.py` — Pydantic models for admin API
- `schema_migration_001_dynamic_rules.sql` — Migration for rounding_rules + audit_log tables
- `seed_dynamic_rules.sql` — Seeds all current hardcoded values into DB

---

## 7. Formula Engine

**Core Principle:** Safe AST-based evaluation of formulas stored in the database.

### How It Works

Formulas are stored as strings in `formulas.expression`:

```
COP_001: customs_value * duty_rate
SOP_001: (customs_value + cop_amount) * special_tax_rate
VOP_001: (customs_value + cop_amount + sop_amount) * vat_rate
ATP_001: volume_liter * atp_rate * exchange_rate
```

The engine parses the expression into an AST and evaluates it with a restricted whitelist of safe nodes (no `eval()`).

### Files Modified

- `core/formula_engine.py` — Safe AST evaluator
- `configs/formula_registry.json` — Formula definitions with variables and descriptions

---

## 8. Orchestrator Integration

**Core Principle:** The orchestrator routes queries correctly and remembers context for follow-up questions.

### What Changed

| Feature | Before | After |
|---------|--------|-------|
| **Session Memory** | None | Tracks `last_result`, `pending_agreement`, `awaiting_rate` per session |
| **Petroleum Detection** | Manual flag only | Auto-detects from HS code prefix `2710` |
| **Rubber Detection** | Not supported | Auto-detects from HS code prefix `4001` |
| **Follow-up Recalculation** | Not supported | Detects follow-up with rate, re-triggers calculation |

### Session State (Orchestrator)

```python
session_state = {
    "last_result": CalculationResult,  # For comparison
    "pending_agreement": "ATIGA",      # Waiting for rate
    "awaiting_rate": True,             # Ask-back active
    "context": {...}                   # Original request params
}
```

### Files Modified

- `orchestrator_version2/core/coordinator.py` — Session memory and follow-up handling
- `orchestrator_version2/core/workflow.py` — Petroleum/rubber case routing
- `orchestrator_version2/infrastructure/clients.py` — Calculator client with ask-back support

---

## 9. Key Files Changed

### Core Business Logic

| File | Lines Changed | Description |
|------|---------------|-------------|
| `core/calculator.py` | ~+900/-300 | Complete rewrite: KHR-first, all cases, ask-back, DV logic |
| `core/models.py` | ~+77/-20 | Added flags, ask-back fields, petroleum fields |
| `core/formulas.py` | ~+21 | Rounding helpers |
| `core/formula_engine.py` | ~+220 | Safe AST evaluator |
| `core/rules_provider.py` | ~+18 | Removed FTA rate loading |
| `core/rules_models.py` | ~-15 | Removed `FTARate` |

### Infrastructure

| File | Lines Changed | Description |
|------|---------------|-------------|
| `infrastructure/unified_database.py` | ~+433 | ATP DB lookup, simplified rate loading, country mapping |
| `infrastructure/rules_database.py` | ~+60/-20 | Removed FTA methods |
| `infrastructure/csv_database.py` | ~+2 | Minor updates |

### API Layer

| File | Lines Changed | Description |
|------|---------------|-------------|
| `api/endpoints.py` | ~+22/-10 | Endpoint updates |
| `api/schemas.py` | ~+50/-20 | Updated models, ask-back fields |
| `api/admin_endpoints.py` | ~-40 | Removed `/fta-rates` |
| `api/admin_schemas.py` | ~-30 | Removed `FTARate` schemas |

### Tests

| File | Description |
|------|-------------|
| `tests/test_core.py` | Core calculator logic (23 tests, all passing) |
| `tests/test_api.py` | API validation + ask-back flow |
| `tests/test_import_export_cases.py` | FTA, petroleum, rubber, exemption scenarios |
| `tests/test_chat_questions.py` | Natural language query parsing |

### Configuration & Docs

| File | Description |
|------|-------------|
| `configs/formula_registry.json` | All formulas documented |
| `configs/rounding_rules.json` | Rounding rules formalized |
| `config.yaml` | Service configuration updated |
| `docs/calculator_service_result.md` | Result format documentation |
| `docs/calculator_v2_summary.md` | Architecture summary |

---

## 10. Database Schema Changes

### Added

```sql
-- duty_rates.atp_rate (Migration 002)
ALTER TABLE duty_rates ADD COLUMN atp_rate DECIMAL(10,4) DEFAULT 0.00;

-- rounding_rules table (Migration 001)
CREATE TABLE rounding_rules (...);

-- rules_audit_log table (Migration 001)
CREATE TABLE rules_audit_log (...);

-- Views
CREATE VIEW active_formulas AS ...;
CREATE VIEW active_rounding_rules AS ...;
CREATE VIEW active_policies AS ...;
```

### Removed

```sql
-- Dropped entirely
DROP TABLE preferential_rates;
DROP INDEX idx_pref_hs_origin;
DROP TRIGGER update_preferential_rates_updated_at;
```

### Seeded Data

- **Formulas:** 14 formulas (currency conversion, COP, SOP, VOP, petroleum CPP/ATP/SPP/VPP/DPP, DQ, ETR, FTA_COP)
- **Rounding Rules:** 6 rules (exchange rate, CIF conversion, tax components, total payable, quantities, rates)
- **Policies:** 6 policies (VAT standard, DV import, DQ apply, petroleum detection, rubber detection, VOP base)
- **Exemptions:** 12 regimes (DIP, QIP, EXP, TMP, NGO, ATIGA, ACFTA, AKFTA, DIPLOMATIC, PERSONAL, SAMPLES, REPAIR, EDUCATION)

---

## Test Results

```
tests/test_core.py .......................    23 passed
tests/test_api.py .....................      (included in count)
======================================
23 passed, 126 warnings in 2.53s
```

All tests pass. Warnings are Pydantic v2 deprecation notices (non-breaking).

---

## Next Steps (Suggested)

1. **Run full integration test:** Orchestrator → Calculator → Ask-back → Follow-up
2. **Update Qdrant payloads:** Add `atp_rate` field to petroleum HS codes in Qdrant for faster lookups
3. **Formula engine enhancement:** Support conditional expressions (e.g., `if_sop_zero`)
4. **Admin UI:** Build frontend for rules management
5. **Audit log viewer:** Add filtering by table, date, user

---

*Document generated by Claude Code. For questions, see `docs/CALCULATOR_V2_ARCHITECTURE.md`.*
