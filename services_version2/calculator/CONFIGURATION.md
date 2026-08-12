# GDCE Calculator Service — Complete Configuration Reference

> **Version:** 2.0.0  
> **Jurisdiction:** Cambodia  
> **Authority:** GDCE (General Department of Customs and Excise)  
> **Last Updated:** 2026-08-05

---

## Table of Contents

1. [Service Identity](#1-service-identity)
2. [Environment Variables (.env)](#2-environment-variables-env)
3. [Server Settings (config.yaml)](#3-server-settings-configyaml)
4. [Python Settings (config.py)](#4-python-settings-configpy)
5. [Docker Configuration](#5-docker-configuration)
6. [Tax Calculation Rules](#6-tax-calculation-rules)
7. [Rounding Rules](#7-rounding-rules)
8. [Formula Registry](#8-formula-registry)
9. [Exchange Rate Policy](#9-exchange-rate-policy)
10. [Dependencies](#10-dependencies)
11. [Dynamic Rules Engine](#11-dynamic-rules-engine)
12. [System Architecture](#12-system-architecture)

---

## 1. Service Identity

| Field | Value |
|-------|-------|
| **Name** | GDCE Calculator Service |
| **Version** | 2.0.0 |
| **Description** | Import tax calculation service for Cambodia customs (GDCE) |
| **Host** | `0.0.0.0` |
| **Port** | `8002` |
| **Jurisdiction** | Cambodia |
| **Issuing Authority** | GDCE (General Department of Customs and Excise) |

---

## 2. Environment Variables (.env)

### 2.1 Calculator Service

| Variable | Value | Description |
|----------|-------|-------------|
| `CALCULATOR_HOST` | `0.0.0.0` | Bind address |
| `CALCULATOR_PORT` | `8002` | TCP port |
| `CALCULATOR_RELOAD` | `false` | Uvicorn hot reload |

### 2.2 Database (PostgreSQL)

The calculator uses its own standalone PostgreSQL database as the primary source of truth.

| Variable | Value |
|----------|-------|
| `CALCULATOR_DB_HOST` | `localhost` |
| `CALCULATOR_DB_PORT` | `5432` |
| `CALCULATOR_DB_NAME` | `gdce_calculator_local` |
| `CALCULATOR_DB_USER` | `postgres` |
| `CALCULATOR_DB_PASSWORD` | `16112005` |
| `CALCULATOR_DB_SSL_MODE` | `disable` |

**Legacy aliases also accepted:**
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `PG_HOST`, `PG_PORT`, `PG_DATABASE`, `PG_USER`, `PG_PASSWORD`
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

### 2.3 Vector Store (Qdrant)

| Variable | Value |
|----------|-------|
| `QDRANT_HOST` | `localhost` |
| `QDRANT_PORT` | `6333` |
| `QDRANT_SEARCH_COLLECTION` | `gdce_docs` |
| `QDRANT_COLLECTION_NAME` | `gdce_docs` |
| `QDRANT_HS_CODE_COLLECTION` | `gdce_hs_code` |
| `QDRANT_HS_CODE_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` |

### 2.4 Redis

| Variable | Value |
|----------|-------|
| `REDIS_HOST` | `localhost` |
| `REDIS_PORT` | `6379` |
| `REDIS_PASSWORD` | `gdceintern` |
| `CACHE_LEVEL` | `hybrid` |

### 2.5 Gemini LLM

| Variable | Value |
|----------|-------|
| `GEMINI_API_KEY` | *(set in .env)* |
| `GEMINI_ENABLED` | `true` |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` |

### 2.6 LLM Intent Detection

| Variable | Value |
|----------|-------|
| `CALCULATOR_LLM_ENABLED` | `false` |
| `CALCULATOR_INTENT_LLM_ENABLED` | `true` |
| `CALCULATOR_INTENT_LLM_TIMEOUT` | `10.0` |
| `CALCULATOR_INTENT_LLM_MODEL` | `gemini-3.1-flash-lite` |
| `LLM_INTENT_DETECTION` | `true` |

### 2.7 Exchange Rate

| Variable | Value |
|----------|-------|
| `USD_TO_KHR_RATE` | `4029.0` |
| `POSTGRESQL_EXCHANGE_RATE_ENABLED` | `true` |
| `MEF_VERIFY_SSL` | `false` |
| `FETCH_INTERVAL_HOURS` | `24` (fetcher-scheduler) |

### 2.8 Embedding Models

| Variable | Value |
|----------|-------|
| `QUERY_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` |
| `EMBEDDING_BATCH_SIZE` | `32` |
| `EMBEDDING_CACHE_ENABLED` | `true` |
| `INTENT_DETECTION_MODEL` | `all-MiniLM-L12-v2` |
| `INTENT_CONFIDENCE_THRESHOLD` | `0.65` |
| `INTENT_DETECTION_TIMEOUT_MS` | `500` |
| `CURRENCY_DETECTION_MODEL` | `all-MiniLM-L12-v2` |
| `CURRENCY_CONFIDENCE_THRESHOLD` | `0.70` |

### 2.9 Service URLs

| Variable | Value |
|----------|-------|
| `RETRIEVAL_SERVICE_URL` | `http://localhost:8003` |
| `CALCULATOR_SERVICE_URL` | `http://localhost:8002` |
| `TRADE_DATA_SERVICE_URL` | `http://localhost:8004` |
| `ORCHESTRATOR_SERVICE_URL` | *(optional)* |

### 2.10 DAL (Data Access Layer)

| Variable | Value |
|----------|-------|
| `DAL_BASE_URL` | `http://localhost:8000` |
| `DAL_API_KEY` | `dal-pub-key-abc123xyz789` |
| `DAL_DATASET_CODE` | `trade_volume` |
| `USE_DAL` | `true` |

### 2.11 Legacy Mode

| Variable | Value |
|----------|-------|
| `CALCULATOR_LEGACY_MODE` | `false` |

### 2.12 Data Files

| Variable | Value |
|----------|-------|
| `DUTY_RATES_CSV_PATH` | `./data/processed/structured/duty_rates.csv` |

### 2.13 Ollama (Optional)

| Variable | Value |
|----------|-------|
| `OLLAMA_HOST` | `localhost` |
| `OLLAMA_PORT` | `11434` |
| `OLLAMA_MODEL` | `llama3.2:3b` |
| `OLLAMA_TIMEOUT` | `120` |
| `OLLAMA_ENABLED` | `false` |

### 2.14 Security & Middleware

| Variable | Value |
|----------|-------|
| `ALLOWED_ORIGINS` | `http://localhost:3000,http://localhost:5173,http://127.0.0.1:8001,http://127.0.0.1:8002,http://127.0.0.1:8003,http://127.0.0.1:8004` |
| `RATE_LIMIT_REQUESTS` | `100` |
| `RATE_LIMIT_WINDOW` | `60` |
| `MAX_PAYLOAD_SIZE_MB` | `10` |

### 2.15 Logging

| Variable | Value |
|----------|-------|
| `LOG_LEVEL` | `INFO` |

### 2.16 Python Path (Docker)

| Variable | Value |
|----------|-------|
| `PYTHONPATH` | `/app` |

---

## 3. Server Settings (config.yaml)

### 3.1 Server

```yaml
server:
  host: "127.0.0.1"
  port: 8002
  reload: false
```

### 3.2 Service Identity

```yaml
service:
  name: "GDCE Calculator Service"
  version: "2.0.0"
  description: "Import tax calculation service for Cambodia customs (GDCE)"
  jurisdiction: "Cambodia"
  issuing_authority: "GDCE (General Department of Customs and Excise)"
```

### 3.3 Upstreams

```yaml
upstreams:
  retrieval_service:
    url: ""           # env: RETRIEVAL_SERVICE_URL
    timeout_seconds: 30
    fallback: "csv_description_search"
```

### 3.4 Security / Middleware

```yaml
security:
  rate_limit_requests: 60
  max_payload_size_mb: 5
  allowed_origins:
    - "*"
```

> **Note:** In production, replace `"*"` with the explicit origin of the chatbot/UI.

### 3.5 Data / Infrastructure

```yaml
infrastructure:
  duty_rates_csv:
    path: "data/processed/structured/duty_rates.csv"
    reload_on_startup: true
    cache_in_memory: true

  exchange_rates:
    default_usd_to_khr: 4022
    source: "Ministry of Economy and Finance (MEF)"
    effective_date: "2026-02-19"
    update_frequency: "Daily (manual update required)"
```

### 3.6 Tax Calculation Rules

```yaml
calculation:
  output_currency: "KHR"
  rounding:
    intermediate: "ROUND_HALF_UP to whole number"
    final_payment: "CEILING to nearest 100 KHR"
  vat_rate: 0.10

  calculation_order:
    step_1: "Convert customs value to USD if needed"
    step_2: "Lookup HS code duty rates from CSV"
    step_3: "Convert USD → KHR using exchange rate"
    step_4: "Calculate COP (Customs Duty)"
    step_5: "Calculate SOP (Special Tax)"
    step_6: "Calculate VOP (VAT) — conditional base"
    step_7: "Sum totals and round UP to nearest 100 KHR"
```

### 3.7 Supported Regimes

- `import`
- `export`
- `transit`
- `temporary_admission`
- `bonded_warehouse`
- `duty_free`
- `qip`
- `sez`
- `diplomatic`
- `ngo_humanitarian`
- `passenger_personal`
- `other`

### 3.8 Special Cases

| Case | Required Fields | Formula |
|------|-----------------|---------|
| Petroleum | `net_mass_kg`, `volume_liter` | Two-phase CPP/ATP/SPP/VPP calculation |
| Rubber | `net_mass_kg` | ETR (Export Tax on Rubber) based on mass |
| FTA/DV | `fta_applicable: true` | Normal case with 0% or reduced duty rate |

### 3.9 Logging

```yaml
logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
```

---

## 4. Python Settings (config.py)

The `Settings` dataclass in `app/core/config.py` provides typed, cached configuration with sensible defaults.

### 4.1 Server Configuration

| Setting | Default | Env Var |
|---------|---------|---------|
| `calculator_host` | `127.0.0.1` | `CALCULATOR_HOST` |
| `calculator_port` | `8002` | `CALCULATOR_PORT` |
| `calculator_reload` | `False` | `CALCULATOR_RELOAD` |
| `calculator_version` | `2.0.0` | `CALCULATOR_VERSION` |

### 4.2 LLM Formatter

| Setting | Default | Env Var |
|---------|---------|---------|
| `llm_host` | `127.0.0.1` | `CALCULATOR_LLM_HOST` |
| `llm_port` | `11434` | `CALCULATOR_LLM_PORT` |
| `llm_model` | `kimi-k2.6:cloud` | `CALCULATOR_LLM_MODEL` |
| `llm_enabled` | `True` | `CALCULATOR_LLM_ENABLED` |

### 4.3 LLM Intent Extractor

| Setting | Default | Env Var |
|---------|---------|---------|
| `intent_llm_enabled` | `True` | `CALCULATOR_INTENT_LLM_ENABLED` |
| `intent_llm_timeout` | `10.0` | `CALCULATOR_INTENT_LLM_TIMEOUT` |
| `intent_llm_model` | `llama3.2:3b` | `CALCULATOR_INTENT_LLM_MODEL` |
| `gemini_api_key` | `""` | `GEMINI_API_KEY` |

### 4.4 External Services

| Setting | Default | Env Var |
|---------|---------|---------|
| `retrieval_service_url` | `""` | `RETRIEVAL_SERVICE_URL` |
| `orchestrator_service_url` | `""` | `ORCHESTRATOR_SERVICE_URL` |

### 4.5 Security & Middleware

| Setting | Default | Env Var |
|---------|---------|---------|
| `rate_limit_requests` | `60` | `RATE_LIMIT_REQUESTS` |
| `max_payload_size_mb` | `5` | `MAX_PAYLOAD_SIZE_MB` |
| `allowed_origins` | `["*"]` | `ALLOWED_ORIGINS` |

### 4.6 Calculator DB

| Setting | Default | Env Var |
|---------|---------|---------|
| `calculator_db_host` | `localhost` | `CALCULATOR_DB_HOST` |
| `calculator_db_port` | `5432` | `CALCULATOR_DB_PORT` |
| `calculator_db_name` | `gdce_calculator` | `CALCULATOR_DB_NAME` |
| `calculator_db_user` | `calc_app` | `CALCULATOR_DB_USER` |
| `calculator_db_password` | `""` | `CALCULATOR_DB_PASSWORD` |
| `calculator_db_ssl_mode` | `disable` | `CALCULATOR_DB_SSL_MODE` |

### 4.7 Currency Settings

| Setting | Default | Env Var |
|---------|---------|---------|
| `usd_to_khr_rate` | `None` | `USD_TO_KHR_RATE` |
| `enable_currency_cache` | `True` | `ENABLE_CURRENCY_CACHE` |

### 4.8 HS Code Settings

| Setting | Default | Env Var |
|---------|---------|---------|
| `enable_hs_fuzzy_search` | `True` | `ENABLE_HS_FUZZY_SEARCH` |
| `hs_code_candidate_limit` | `5` | `HS_CODE_CANDIDATE_LIMIT` |

### 4.9 Dynamic Rules Engine

| Setting | Default | Env Var |
|---------|---------|---------|
| `admin_api_key` | `None` | `ADMIN_API_KEY` |
| `rules_cache_ttl_seconds` | `300` | `RULES_CACHE_TTL_SECONDS` |
| `rules_db_enabled` | `True` | `RULES_DB_ENABLED` |

### 4.10 Logging

| Setting | Default | Env Var |
|---------|---------|---------|
| `log_level` | `"INFO"` | `LOG_LEVEL` |

---

## 5. Docker Configuration

### 5.1 Dockerfile (Main Service)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the restructured calculator package into a 'calculator' subdir
COPY . /app/calculator/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8002

CMD ["uvicorn", "calculator.main:app", "--host", "0.0.0.0", "--port", "8002"]
```

### 5.2 Dockerfile.fetcher (Exchange Rate Scheduler)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the fetcher script
COPY exchange_rate_fetcher.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "exchange_rate_fetcher.py"]
```

### 5.3 docker-compose.yml

| Service | Image / Build | Exposed Port | Notes |
|---------|---------------|--------------|-------|
| `redis` | `redis:7-alpine` | `6379:6379` | In Docker network `gdce-network` |
| `calculator` | Build from `Dockerfile` | `8002:8002` | Live-mounts `./app`, `./prompts`, `./configs`, `./tests` as read-only |
| `fetcher-scheduler` | Build from `Dockerfile.fetcher` | — | Runs every `FETCH_INTERVAL_HOURS` (default: 24h) |

**Environment overrides inside container:**

| Variable | Container Value |
|----------|-----------------|
| `CALCULATOR_HOST` | `0.0.0.0` |
| `CALCULATOR_PORT` | `8002` |
| `CALCULATOR_DB_HOST` | `host.docker.internal` |
| `CALCULATOR_DB_NAME` | `gdce_calculator_local` |
| `REDIS_HOST` | `redis` |
| `QDRANT_HOST` | `qdrant` |
| `PYTHONPATH` | `/app` |

**Network:** `gdce-network` (external)

---

## 6. Tax Calculation Rules

### 6.1 Overview (`configs/calculator_config.json`)

- **Default currency:** `KHR`
- **VAT rate:** `10%` (Law on Taxation 2023)
- **Exchange rate source:** Ministry of Economy and Finance (MEF)
- **Effective date:** `2026-02-19`
- **Default USD→KHR rate:** `4022`

### 6.2 Customs Duty Rates (Special Cases)

| Product | HS Code | General Rate | FTA Rate | Notes |
|---------|---------|--------------|----------|-------|
| Beer | `2204` | `20%` | — | 20% CD for beer imports |
| Spirits | `2208` | `20%` | — | 20% CD for spirits |
| Smartphones | `8517.62` | `25%` | `0%` (ATIGA) | Requires ATIGA Form D |
| Medical Equipment | `9018` | `0%` | — | Exempted under investment law |
| Machinery | `84` | `10%` | — | Variable by type |

### 6.3 Special Tax Rates

| Product | HS Code | Rate | Notes |
|---------|---------|------|-------|
| Beer | `2204` | `30%` | Applied to all beer regardless of origin |
| Spirits | `2208` | `35%` | Applied to all spirits |
| Tobacco | `2402-2403` | `50%` | Standard tobacco excise |
| Energy Drinks | `2202` | `20%` | Non-alcoholic energy/sports drinks |
| Smartphones (ATIGA) | `8517.62` | `5%` | Reduced from 10% with valid ATIGA |
| Default Industrial | — | `10%` | When no special rate defined |

### 6.4 Free Trade Agreements (FTA)

| Agreement | Certificate | Members | CD Reduction | ST Reduction |
|-----------|-------------|---------|--------------|--------------|
| **ATIGA** | Form D | ASEAN (10 countries) | `0%` | Often 50% or specific rate |
| **CPTPP** | CPTPP CoO | 11 countries | `0-5%` | Variable |
| **ASEAN Framework (CEPT)** | — | ASEAN members | `0-5%` | Variable |

### 6.5 Exemptions

| Category | CD | ST | VAT | Requires Certification |
|----------|----|----|-----|------------------------|
| Diplomatic goods | `100%` | `100%` | `100%` | Yes (Ministry of Foreign Affairs) |
| Humanitarian aid | `100%` | `100%` | `100%` | Yes |
| Government goods | Variable | Variable | Often exempted | Yes |
| QIP goods | Exemption/reduction | Often exempted | Variable | Yes (CDC) |

### 6.6 Calculation Order

1. Verify currency and convert to KHR if needed (`USD × exchange_rate`)
2. Lookup HS code and confirm classification
3. Check origin and FTA documents (if applicable)
4. Apply Customs Duty rate (CD)
5. Apply Special Tax rate (ST)
6. Calculate subtotal (`CIF + CD + ST`)
7. Apply VAT on subtotal
8. Round UP final total to nearest 100 KHR

---

## 7. Rounding Rules

> **Core Principle:** All monetary amounts round **UP** to nearest 100 KHR (ceiling function). Quantities, rates, and exchange rates are **NOT rounded**.

### 7.1 Rule Summary

| Rule ID | Name | Method | Applies To | Priority |
|---------|------|--------|------------|----------|
| `RULE_001` | Exchange Rate Precision | **NONE** | `exchange_rate` | CRITICAL |
| `RULE_002` | Currency Conversion Result | `ROUND_WHOLE` | `cif_value_khr_after_conversion` | HIGH |
| `RULE_003` | Cambodia Customs Tax Components | `CEILING_100` | `cop_amount`, `sop_amount`, `vop_amount`, `total_duties_and_taxes` | HIGH |
| `RULE_004` | Final Payment Amount | `CEILING_100` | `total_payable` | CRITICAL |
| `RULE_005` | Quantity Values | **NONE** | `quantity`, `net_mass_kg`, `gross_mass_kg`, `volume_ltr` | CRITICAL |
| `RULE_006` | Tax Rates and Duty Rates | **NONE** | `duty_rate`, `vat_rate`, `excise_rate`, `special_tax_rate` | CRITICAL |

### 7.2 Execution Order

1. **Currency Conversion:** `Customs Value (USD) × Exchange Rate = Customs Value (KHR)` → Round to whole number (Rule 002)
2. **Calculate COP:** `customs_value_khr × import_tax_rate` → CEILING to nearest 100 (Rule 003)
3. **Calculate SOP:** `(customs_value_khr + cop_amount) × special_tariff_rate` → CEILING to nearest 100 (Rule 003)
4. **Determine VOP Base:**
   - Non-taxable goods: `VOP_base = customs_value_khr + cop_amount`
   - General taxable goods: `VOP_base = customs_value_khr + cop_amount + sop_amount`
5. **Calculate VOP:** `vop_base × vat_rate (10%)` → CEILING to nearest 100 (Rule 003)
6. **Sum Duties and Taxes:** `cop_amount + sop_amount + vop_amount` → CEILING to nearest 100 (Rule 003)
7. **Calculate Fees:** `processing_fee + inspection_fee + other_fees` → CEILING to nearest 100 (Rule 003)
8. **Final Total Payable:** `total_duties_and_taxes + total_fees` → CEILING to nearest 100 (Rule 004)

### 7.3 Key Examples

**Taxable Goods Example:**
- Customs Value: 1,000 USD × 4,022 = **4,022,000 KHR**
- COP: 4,022,000 × 0.35 = 1,407,700 → **1,407,700 KHR**
- SOP: (4,022,000 + 1,407,700) × 0.10 = 542,970 → CEILING = **543,000 KHR**
- VOP: (4,022,000 + 1,407,700 + 543,000) × 0.10 = 597,270 → CEILING = **597,300 KHR**
- **Total Payable:** 1,407,700 + 543,000 + 597,300 = **2,548,000 KHR**

**Non-Taxable Goods Example (Medical Equipment):**
- Customs Value: 1,000 USD × 4,022 = **4,022,000 KHR**
- COP: 4,022,000 × 0.35 = 1,407,700 → **1,407,700 KHR**
- SOP: **0 KHR** (non-taxable)
- VOP: (4,022,000 + 1,407,700) × 0.10 = 542,970 → CEILING = **543,000 KHR**
- **Total Payable:** 1,407,700 + 0 + 543,000 = **1,950,700 KHR**

---

## 8. Formula Registry

### 8.1 Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `vat_standard_rate` | `0.1` (10%) | Standard VAT rate per Law on Taxation 2023 |
| `rounding_mode` | `CEILING` | Always round UP to nearest 100 |
| `rounding_precision` | `100` KHR | Round to nearest 100 KHR |

### 8.2 Standard Formulas

| Formula | ID | Formula | Rounding |
|---------|----|---------|----------|
| Currency Conversion | `CC_001` | `customs_value_khr = cif_value * exchange_rate` | Whole number |
| Rate Determination | `RD_001` | Lookup HS code in `duty_rates.csv` | — |
| COP Amount | `ID_001` | `cop_amount = customs_value_khr * duty_rate` | CEILING 100 |
| SOP Amount | `ST_001` | `sop_amount = (customs_value_khr + cop_amount) * special_tax_rate` | CEILING 100 |
| VOP Amount | `VAT_001` | `vop_amount = vop_base * vat_rate` | CEILING 100 |
| Total Duties & Taxes | `TDT_001` | `total = cop_amount + sop_amount + vop_amount` | CEILING 100 |
| Total Payable | `TP_001` | `total_payable = total_duties_and_taxes + fees` | CEILING 100 |

### 8.3 VOP Base Conditional Logic

```
IF special_tax_rate == 0 (non-taxable goods):
    vop_base = customs_value_khr + cop_amount
ELSE (taxable goods, SOP > 0%):
    vop_base = customs_value_khr + cop_amount + sop_amount
```

### 8.4 Special Formulas

#### Petroleum (Two-Phase)

| Phase | Formula | Description |
|-------|---------|-------------|
| Phase 1 CPP Base | `(dv * exchange_rate * net_mass) / 1000` | Customs Petroleum Payment base |
| Phase 1 CPP | `cpp_base * cpp_rate` | Customs duty for petroleum |
| Phase 1 ATP | `atp_base * atp_rate * exchange_rate` | Additional Tax Petroleum |
| Phase 1 SPP | `(cpp_base + cpp_amount + atp_amount) * spp_rate` | Special tax petroleum |
| Phase 1 VPP Base | `spp_base + spp_amount` | VAT base for petroleum |
| Phase 1 VPP | `vpp_base * vpp_rate` | VAT for petroleum |
| Phase 2 | Same as Phase 1 but replace CPP base with actual customs value | |
| DPP | `ABS(phase1_total - phase2_total)` | Partial subsidy by the state (informational only) |

#### Rubber

| Formula | Expression |
|---------|------------|
| ETR | `(dv * exchange_rate * net_mass) / 1000` |

#### FTA / DV Cases

| Case | COP | SOP | VOP |
|------|-----|-----|-----|
| FTA/DV (non-taxable) | `customs_value * cop_rate` (typically 0%) | `(customs_value + cop) * sop_rate` | `(CIF + COP) * 10%` |
| FTA/DV (taxable) | `customs_value * cop_rate` (typically 0%) | `(customs_value + cop) * sop_rate` | `(CIF + COP + SOP) * 10%` |
| FTA/DV + DQ | `cop_base * cop_rate` (0%) | `(sop_base + cop_base) * sop_rate * dq` | `(CIF + COP + DQ-adjusted SOP) * 10%` |

#### Mass / Volume Based Taxes

| Formula | Expression | Applies To |
|---------|------------|------------|
| Commodity Tax by Mass | `net_mass_kg * rate_per_kg` | Rubber, certain agricultural products |
| Commodity Tax by Volume | `volume_ltr * rate_per_ltr` | Petroleum products, certain liquids |
| Commodity Tax Hybrid | `(net_mass_kg * mass_rate) + (volume_ltr * volume_rate)` | Specific rubber/petroleum types |

---

## 9. Exchange Rate Policy

### 9.1 Method

- **Current:** `fixed_table_from_csv` (MEF-scraped data)
- **Rationale:** Use official MEF exchange rate tables for reproducible, auditable calculations
- **Update Frequency:** Manual (future: daily automated scrape at 08:00 UTC)

### 9.2 Rate Selection Rules

| Priority | Rule | Action |
|----------|------|--------|
| 1 | `RATE_BY_DECLARATION_DATE` | Use rate for exact customs declaration date |
| 2 | `FALLBACK_LATEST_RATE` | If no declaration date, use latest available rate (logged as estimate) |
| 3 | `REJECT_MISSING_CURRENCY` | Reject calculation if currency not found (NEVER invent rates) |

### 9.3 Supported Currencies

| Code | Name | Priority |
|------|------|----------|
| USD | US Dollar | 1 |
| VND | Vietnamese Dong | 1 |
| CNY | China Yuan | 2 |
| THB | Thai Baht | 2 |
| EUR | Euro | 3 |
| SGD | Singapore Dollar | 3 |
| GBP | British Pound | 4 |
| JPY | Japanese Yen | 4 |
| AUD | Australian Dollar | 5 |
| CAD | Canadian Dollar | 5 |

### 9.4 Validation Rules

- Rate must be `> 0`
- USD/KHR sanity check range: `3000 – 5000`
- Currency codes must be valid ISO 4217 (3-letter uppercase)
- All rates on same date must come from same MEF source file

### 9.5 Data Update Process

1. Place new CSV in: `data/processed/structured/exchange_rates_selenium_YYYYMMDD_HHMMSS.csv`
2. Keep old files for audit trail (NEVER delete historical rates)
3. Future: automatic daily scrape from MEF at 08:00 UTC

---

## 10. Dependencies

### 10.1 requirements.txt

```
# Web framework
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.7.0
pydantic-settings==2.2.0
python-dotenv==1.0.1
python-multipart==0.0.6

# HTTP client
httpx==0.26.0

# Database
psycopg2-binary==2.9.9

# Config
PyYAML==6.0.1

# Redis (exchange rate cache)
redis==5.0.1

# Vector search (semantic HS code search)
qdrant-client==1.7.0

# Embeddings
sentence-transformers==2.5.1

# Testing (dev only)
pytest==7.4.4
pytest-asyncio==0.23.3
pytest-cov==4.1.0
```

---

## 11. Dynamic Rules Engine

| Setting | Default | Description |
|---------|---------|-------------|
| Enabled | `true` | Enable loading rules from PostgreSQL |
| Cache TTL | `300` seconds | Rules cache time-to-live |
| Admin API Key | `None` | Required for admin endpoints; `None` = unprotected (dev mode) |

---

## 12. System Architecture

```
┌─────────────────────────────────────────┐
│         Client (Chatbot / UI)           │
│         Origin: http://localhost:3000   │
└─────────────────┬───────────────────────┘
                  │ HTTP / JSON
┌─────────────────▼───────────────────────┐
│  Calculator Service (FastAPI) :8002     │
├─────────────────────────────────────────┤
│  Routes:                                │
│    - /api/v1/calculate                  │
│    - /api/v1/admin/*                    │
│    - /api/v1/convert (currency)         │
├─────────────────────────────────────────┤
│  Components:                            │
│    - Intent Extractor (Gemini)          │
│    - LLM Formatter (optional)           │
│    - Formula Engine                     │
│    - Rules Provider                     │
│    - Currency Handler                   │
│    - HS Code Handler                    │
├─────────────────────────────────────────┤
│  Data Layer:                            │
│    - calculator_db.py (PostgreSQL)      │
│    - unified_database.py                │
│    - exchange_rate_adapter.py           │
│    - redis_exchange_rate_client.py      │
│    - rules_database.py                  │
│    - qdrant_client.py                   │
│    - retrieval_client.py                │
├─────────────────────────────────────────┤
│  Configuration:                         │
│    - .env                               │
│    - config.yaml                        │
│    - config.py                          │
│    - configs/*.json                     │
├─────────────────────────────────────────┤
│  External Services:                      │
│    - PostgreSQL :5432                   │
│    - Redis :6379                        │
│    - Qdrant :6333                       │
│    - Retrieval Service :8003            │
│    - Trade Data Service :8004           │
│    - DAL :8000                          │
│    - MEF Exchange Rate (CSV/API)        │
└─────────────────────────────────────────┘
```

---

## Appendix A: File Structure

```
calculator/
├── app/
│   ├── main.py                    # Entry point (FastAPI app)
│   ├── core/
│   │   ├── config.py              # Typed Python settings
│   │   ├── config.yaml            # YAML configuration reference
│   │   ├── exceptions.py          # Custom exceptions
│   │   └── logging.py             # Logging setup
│   ├── api/
│   │   ├── routes.py              # API route aggregation
│   │   ├── deps.py                # FastAPI dependencies
│   │   └── v1/
│   │       ├── calculator_routes.py
│   │       └── admin_routes.py
│   ├── schemas/
│   │   ├── calculator_schema.py
│   │   └── admin_schema.py
│   ├── services/
│   │   ├── calculator.py          # Main calculation logic
│   │   ├── formulas.py            # Tax formulas
│   │   ├── formula_engine.py      # Formula execution engine
│   │   ├── rules_provider.py      # Rules loading/provider
│   │   ├── rules_models.py        # Pydantic models for rules
│   │   ├── ask_back_policy.py     # "Ask back" clarification policy
│   │   ├── currency_handler.py    # Currency conversion handler
│   │   └── models.py              # Service models
│   ├── data/
│   │   ├── calculator_db.py       # PostgreSQL adapter
│   │   ├── unified_database.py    # Unified DB interface
│   │   ├── exchange_rate_adapter.py
│   │   ├── redis_exchange_rate_client.py
│   │   ├── rules_database.py      # Dynamic rules DB
│   │   ├── qdrant_client.py       # Vector store client
│   │   └── retrieval_client.py    # Retrieval service client
│   ├── ai/
│   │   ├── intent_extractor.py    # Natural language → structured request
│   │   └── llm_formatter.py       # LLM response formatting
│   ├── converter/                 # Currency converter module
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── service.py
│   └── utils/
├── configs/
│   ├── calculator_config.json     # Main tax rules & FTA config
│   ├── exchange_rate_policy.json  # Exchange rate rules
│   ├── formula_registry.json      # Calculation formulas
│   ├── rounding_rules.json        # Cambodia rounding rules
│   └── calculate_import_taxes.schema.json
├── prompts/
│   └── intent_prompts.py          # LLM prompts
├── scripts/
│   ├── init_db.py                 # DB initialization
│   ├── migrate_*.py               # Migration scripts
│   └── sync_qdrant.py             # Qdrant sync script
├── tests/
│   ├── test_api.py
│   ├── test_core.py
│   ├── test_formulas.py
│   ├── test_converter.py
│   ├── test_chat_questions.py
│   ├── test_prefix_resolution.py
│   └── test_import_export_cases.py
├── exchange_rate_fetcher.py       # Standalone exchange rate fetcher
├── requirements.txt
├── Dockerfile
├── Dockerfile.fetcher
├── docker-compose.yml
├── .env                           # Local environment variables
├── .gitignore
└── CALCULATOR_ARCHITECTURE.md
```

---

## Appendix B: Environment Variable Quick Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `CALCULATOR_HOST` | `127.0.0.1` | Bind address |
| `CALCULATOR_PORT` | `8002` | TCP port |
| `CALCULATOR_RELOAD` | `false` | Enable uvicorn hot reload |
| `CALCULATOR_VERSION` | `2.0.0` | Service version |
| `RETRIEVAL_SERVICE_URL` | *(empty)* | URL of retrieval microservice |
| `ORCHESTRATOR_SERVICE_URL` | *(empty)* | URL of orchestrator microservice |
| `CALCULATOR_LLM_HOST` | `127.0.0.1` | LLM host for formatting |
| `CALCULATOR_LLM_PORT` | `11434` | LLM port |
| `CALCULATOR_LLM_MODEL` | `kimi-k2.6:cloud` | LLM model name |
| `CALCULATOR_LLM_ENABLED` | `true` | Enable LLM formatting |
| `CALCULATOR_INTENT_LLM_ENABLED` | `true` | Enable intent LLM |
| `CALCULATOR_INTENT_LLM_TIMEOUT` | `10.0` | Intent LLM timeout (seconds) |
| `CALCULATOR_INTENT_LLM_MODEL` | `llama3.2:3b` | Intent LLM model |
| `GEMINI_API_KEY` | *(empty)* | Gemini API key |
| `RATE_LIMIT_REQUESTS` | `60` | Max requests/min per client |
| `MAX_PAYLOAD_SIZE_MB` | `5` | Max request body size |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins |
| `CALCULATOR_DB_HOST` | `localhost` | Calculator DB host |
| `CALCULATOR_DB_PORT` | `5432` | Calculator DB port |
| `CALCULATOR_DB_NAME` | `gdce_calculator` | Calculator DB name |
| `CALCULATOR_DB_USER` | `calc_app` | Calculator DB user |
| `CALCULATOR_DB_PASSWORD` | *(empty)* | Calculator DB password |
| `CALCULATOR_DB_SSL_MODE` | `disable` | SSL mode |
| `USD_TO_KHR_RATE` | *(empty)* | Explicit USD→KHR rate override |
| `ENABLE_CURRENCY_CACHE` | `true` | Cache exchange rates |
| `ENABLE_HS_FUZZY_SEARCH` | `true` | Fuzzy HS code matching |
| `HS_CODE_CANDIDATE_LIMIT` | `5` | Max HS code candidates |
| `ADMIN_API_KEY` | *(empty)* | API key for admin endpoints |
| `RULES_CACHE_TTL_SECONDS` | `300` | Rules cache TTL |
| `RULES_DB_ENABLED` | `true` | Enable dynamic rules from DB |
| `LOG_LEVEL` | `INFO` | Logging level |

---

*Generated on 2026-08-05 from live codebase inspection.*
