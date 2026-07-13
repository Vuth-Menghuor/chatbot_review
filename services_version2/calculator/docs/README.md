# Calculator Service

> **Owner:** Vechika | **Port:** `8002` | **Version:** `2.0.0` (reference microservice)

Import tax calculation service for Cambodia customs (GDCE).
This is the **reference implementation** for the GDCE-ChatBot microservice migration.

---

## Directory Structure

```
services/calculator/
├── app.py                  # FastAPI application factory (create_app)
├── main.py                 # Uvicorn entrypoint — run this to start the service
├── config.yaml             # All configuration options (documented)
│
├── api/                    # HTTP layer
│   ├── __init__.py
│   ├── endpoints.py        # All FastAPI endpoints (v1)
│   ├── routes.py           # Mounts endpoints router
│   ├── schemas.py          # Pydantic request/response models
│   └── deps.py             # FastAPI Depends() providers
│
├── core/                   # Business logic & domain (no framework deps)
│   ├── __init__.py
│   ├── config.py           # Settings (env-driven, lru_cache)
│   ├── models.py           # Domain dataclasses
│   └── calculator.py       # ImportTaxCalculator (uses formulas + DatabaseInterface)
│
├── infrastructure/         # I/O adapters
│   ├── __init__.py
│   └── retrieval_client.py # HTTP client → Retrieval Service (placeholder)
│
├── tests/                  # Automated tests
│   ├── __init__.py
│   ├── conftest.py         # Shared pytest fixtures
│   ├── test_core.py        # Core calculator smoke tests
│   └── test_api.py         # API validation + calculation flow
│
│ ── (legacy — kept for reference)
├── calculator.py           # Legacy orchestration (migrated into core/)
├── formulas.py             # Legacy formulas (copied into core/)
├── api.py                  # Legacy monolith
├── test_formulas.py        # Legacy formula smoke tests
├── schema.sql              # DB schema (future PostgreSQL migration)
└── seed.sql                # Seed data
```

---

## Quick Start

### Start the service

```powershell
# From project root: e:\GDCE-ChatBot
$env:PYTHONPATH = (Get-Location).Path
.\env\Scripts\python.exe -m services.calculator.main
```

Or with uvicorn directly:

```powershell
$env:PYTHONPATH = (Get-Location).Path
.\env\Scripts\python.exe -m uvicorn services.calculator.main:app --host 127.0.0.1 --port 8002 --reload
```

### Endpoints (v1)

| Method | Path                              | Description                |
| ------ | --------------------------------- | -------------------------- |
| `GET`  | `/`                            | Service info               |
| `GET`  | `/health`                      | Health check               |
| `GET`  | `/lookup/duty-rate`            | Duty rates by HS code      |
| `GET`  | `/lookup/hs-info`              | HS code description & unit |
| `GET`  | `/lookup/exchange-rate`        | FX rate to KHR             |
| `GET`  | `/lookup/vat-formula`          | VAT formula text           |
| `POST` | `/lookup/hs-code-from-product` | Auto-lookup HS code        |
| `POST` | `/calculate_import_taxes`      | **Main calculation**       |

### API Structure & Parameters

**LLM/caller rules (trade queries)**

- Always include a date/period (`calculation_date`), e.g., 2026-03-30; prompt the user if missing.
- Return only the single best HS code (no unrelated alternatives); downstream UI may let users compare later.
- Show currency values with a `$` prefix when displayed to users (e.g., `$40,000`), while the API still accepts numeric floats.
- Map user queries → API params before calling; if a required param is absent, ask for it (especially date and HS code).
- If `currency` or CIF/customs value is missing, ask the user to provide them before calling the API.

**calculate_import_taxes (POST /calculate_import_taxes)**

- Mandatory: `calculation_date` (YYYY-MM-DD), `regime`, `goods.description`, `valuation.customs_value`, `valuation.currency`
- Optional: `goods.hs_code`, `goods.origin_country`, `goods.quantity`, `goods.unit`, `goods.net_mass_kg`, `goods.volume_liter`, `flags.*`, `requested_breakdown`
- Outputs: `calculation_id`, `currency`, `total` (numeric, display as `$` in UI), `breakdown`, `line_items`, `assumptions`, `references`, optional `exchange_rate_usd_to_khr`, `cif_value_usd`

**lookup_duty_rate (GET /lookup/duty-rate)**

- Mandatory: `hs_code`; Optional: `origin_country`, `effective_date`
- Outputs: `found`, `rates` (numeric, display as `$` when showing values), `hs_info`, `source`

**lookup_hs-info (GET /lookup/hs-info)**

- Mandatory: `hs_code`; Outputs: `hs_info`, `found`

**lookup_exchange-rate (GET /lookup/exchange-rate)**

- Mandatory: `currency`; Optional: `effective_date`; Outputs: `khr_rate`, `found`, `source`

**lookup_vat-formula (GET /lookup/vat-formula)**

- No params; Outputs: VAT formula text, `source`

**lookup_hs-code-from-product (POST /lookup/hs-code-from-product)**

- Mandatory: `product_description`; Outputs: `found`, best `hs_code`, `confidence`, `duty_rates`, `source`

API visibility: each endpoint returns `service`/`version` (health/root) or `source` fields so callers can log which API was used for transparency/testing.

**LLM parameter checklist (before calling any endpoint)**

- Date required: ensure `calculation_date` is present; if missing, ask the user for a specific day/month/period.
- HS code: use a single best-match HS code; avoid returning multiple unrelated codes. If HS code unknown, call `POST /lookup/hs-code-from-product` first.
- Currency display: keep API payloads numeric; prepend `$` (or local symbol) only when rendering to users.
- CIF/customs value: required for calculations; if absent, prompt the user for the amount and currency.
- Optional context: origin country, quantity/unit, regime, and flags (FTA, exemptions) improve accuracy.
- Transparency: include returned `source` or `service` metadata in logs to show which API was invoked.

Swagger UI: `http://127.0.0.1:8002/docs`

---

## Configuration

All settings are documented in [`config.yaml`](./config.yaml).
Override any setting with environment variables (see the reference table at the bottom of that file).

Key variables for local dev:

```env
CALCULATOR_PORT=8002
CALCULATOR_RELOAD=true
RETRIEVAL_SERVICE_URL=http://127.0.0.1:8000
USD_TO_KHR_RATE=4022.0
```

---

## Running Tests

```powershell
# From project root
$env:PYTHONPATH = (Get-Location).Path
.\env\Scripts\python.exe -m pytest services/calculator/tests/ -v

# Legacy formula smoke tests
.\env\Scripts\python.exe services/calculator/test_formulas.py
.\env\Scripts\python.exe scripts/calculator_test.py
```

---

## Migration Status

| Phase       | Status  | Description                                                                                             |
| ----------- | ------- | ------------------------------------------------------------------------------------------------------- |
| **Phase 0** | ✅ Done | Discovery — files, entrypoint, tests, run command documented                                            |
| **Phase 1** | ✅ Done | Skeleton — microservice folders created                                                                 |
| **Phase 2** | ✅ Done | Logic split — core/calculator, core/formulas, api schemas/endpoints                                     |
| **Phase 3** | ✅ Done | Dependency cleanup — core has zero FastAPI/Flask imports; api only calls core; no cross-service imports |
| **Phase 4** | ✅ Done | API standardization — request/response models, router structure, error handling                         |
| **Phase 5** | ✅ Done | Config & infra — config.yaml + env overrides, PostgreSQL adapter                                         |
| **Phase 6** | ✅ Done | Tests — test_core.py, test_api.py cover core math + API validation                                      |
| **Phase 7** | ✅ Done | Documentation — README updated (ownership, endpoints, config, run, test)                                |

---

## Architecture (current)

```
main.py  →  app.py (create_app)
               ├── api/routes.py       (mounts endpoints)
               │     └── api/endpoints.py  (HTTP handlers)
               │     └── api/deps.py       (DB + settings injection)
               │           └── infrastructure/unified_database.py (DatabaseInterface impl)
               └── core/                  (business logic, no frameworks)
                       ├── calculator.py  (ImportTaxCalculator, uses formulas)
                       ├── formulas.py    (pure math)
                       ├── models.py      (dataclasses)
                       └── config.py      (settings)
```

## Key Design Decisions

- **Framework-free core** — core/ has zero FastAPI/Flask/Pydantic/SQLAlchemy imports.
- **Adapter pattern** — infrastructure implements `DatabaseInterface`; swap DB implementations without touching core/api.
- **create_app factory** — clean test isolation; override deps via `app.dependency_overrides`.
- **Config via env** — `get_settings()` reads env (e.g., `CALCULATOR_DB_HOST`, `USD_TO_KHR_RATE`).
- **Tests first** — API and core tests provided as reference for other services.
- **Future (MCP)** — plan to evaluate Model Context Protocol for standardized API exposure to LLM orchestrators.
