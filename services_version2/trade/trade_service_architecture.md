# GDCE Trade Service — Complete Pipeline Architecture

## Overview

The trade service is a **7-stage NLP-to-data pipeline** that converts a natural language question into a structured JSON response containing records, a chart, a table, an NLG message, and suggestions. Every incoming HTTP request passes through all 7 stages in sequence.

```
User question (HTTP POST /query)
    │
    ▼
[Stage 0] API Gateway
    │
    ▼
[Stage 1] LLM Parameter Extraction
    │
    ▼
[Stage 2] Semantic Enrichment
    │
    ▼
[Stage 3] Intent Scoping
    │
    ▼
[Stage 4] Query Orchestration
    │
    ▼
[Stage 5] DAL Execution + Post-processing
    │
    ▼
[Stage 5b] Normalisation
    │
    ▼
[Stage 6] Natural Language Generation (NLG)
    │
    ▼
JSON Response → Orchestrator → Frontend
```

---

## Stage 0 — API Gateway

**Purpose:** Accept the HTTP request, validate the question string, dispatch to the service, and map all exceptions to HTTP status codes.

| File | Role |
|---|---|
| `app.py` | FastAPI app factory — creates the app, mounts the router, initialises `TradeService` at startup via `set_service()` |
| `main.py` | Uvicorn entrypoint; loads `.env`, calls `app.py` |
| `api/endpoints.py` | Defines `POST /query` and `GET /health` routes; catches all exceptions and maps them to HTTP responses |
| `api/schemas.py` | Pydantic `QueryRequest` (input) and `TradeQueryResponse` (output) models |
| `api/validators.py` | `validate_question()` — length and character checks on raw question string |
| `api/exceptions.py` | `map_core_exception_to_http()` — converts `ValidationError`, `DALError`, `NoResultsError` etc. to FastAPI `HTTPException` |
| `config.py` / `config.yaml` | Service-level settings (DAL URL, API key, timeouts, default frequency) |

**Entry point call:**
```python
# api/endpoints.py line 48
result = svc.query_from_question(question, request.extracted_params)
```

The API layer also handles the `no_data` graceful fallback — when `NoResultsError` is raised from the service, it builds a complete empty-shell response instead of returning an HTTP 404.

---

## Stage 1 — LLM Parameter Extraction

**Purpose:** Parse the raw NL question into a structured dict of typed parameters using Google Gemini.

| File | Role |
|---|---|
| `core/llm_extractor.py` | Main extraction logic + SYSTEM_INSTRUCTION prompt + post-processing |
| `core/query_plan.py` → `RawQueryPlan` | Frozen dataclass that holds the Stage 1 output |

**What happens:**

1. `extract_parameters_llm(question)` sends the question + `SYSTEM_INSTRUCTION` to Gemini.
2. The model returns a JSON blob with fields: `intent`, `year`, `trade_direction`, `partner_countries`, `hs_code`, `sitc_division`, `mode_of_transport`, `sort_order`, `limit`, etc.
3. `parse_and_resolve_parameters()` converts raw LLM output into typed Python values:
   - `year` → `int`, with a **current-year guard** (suppresses 2026 if not explicit in question)
   - `partner_countries` → list of ISO-2 codes via `resolve_country()`
   - `trade_direction` → `"EX"` or `"IM"`
   - Perspective-based direction override: *"countries import from Cambodia"* → FLOW=EX
4. The result is packed into a `RawQueryPlan` dataclass.

**Retry loop (in `service.py`):**
- Up to `MAX_EXTRACTION_RETRIES = 2` attempts
- If Stage 4 validation fails, the error text is fed back to the LLM as `retry_context` so it can correct itself
- Only applies when the service owns the extraction (not pre-extracted params from the orchestrator)

**Supported intents extracted by LLM:**
`summary` | `ranking` | `trend` | `comparison` | `breakdown` | `growth` | `trade_balance`

---

## Stage 2 — Semantic Enrichment

**Purpose:** Convert raw text values and codes into canonical database-ready identifiers. Resolve product names, country names, dimension synonyms.

| File | Role |
|---|---|
| `core/enrichment.py` → `enrich_query_plan()` | Stage 2 main function; produces `EnrichedQueryPlan` |
| `core/semantic_registry.py` | Registry of all dimensions, measures, and their synonyms |
| `core/countries.py` | `COUNTRY_TO_CODE_MAP` pattern registry + `VALID_COUNTRY_CODES` |
| `core/product_resolver.py` | Maps product names (e.g. `"rice"`) to HS codes (e.g. `"1006"`) via regex |
| `core/query_plan.py` → `EnrichedQueryPlan` | Stage 2 output dataclass |

**What happens:**

1. Country resolution: `"vietnam"` → `"VN"`, `"EU"` → expands to 27 ISO-2 codes via `REGIONAL_EXPANSIONS`
2. Product resolution: `"rice"` → `hs_code = "1006"`, `"garments"` → `hs_chapter = "62"`
3. SITC code resolution: `"Section 7"` → `"7"`, `"Dairy products"` → `"02"`
4. Mode of transport: `"air"` → `"4"`, `"sea"` → `"1"`, `"land"` → `"3"`
5. Trade direction: `"export"` → `"EX"`, `"import"` → `"IM"`
6. Dimension synonym resolution: `"by country"` → `"PARTNER_COUNTRY"` via `find_dimension_by_synonym()`

---

## Stage 3 — Intent Scoping

**Purpose:** Apply per-intent business rules: set default dimensions, default metrics, default limits, default sort order, default frequency. Lock in the "scope" of what the query will ask for.

| File | Role |
|---|---|
| `handlers/scopes.py` → `apply_intent_scoping()` | Stage 3 main function; produces `ScopedQueryPlan` |
| `handlers/strategies.py` | Per-intent strategy definitions (dimensions, sort behaviour) |
| `core/semantic_registry.py` → `INTENT_RULES` | Per-intent default rules (default dimensions, metrics, limits) |
| `core/query_plan.py` → `ScopedQueryPlan` | Stage 3 output dataclass |

**What each intent gets scoped to:**

| Intent | Default Dimensions | Default Metrics | Default Limit | Default Sort | Default Freq |
|---|---|---|---|---|---|
| `summary` | *(none / FLOW)* | VALUE_USD, NET_WEIGHT | 1000 | — | A |
| `ranking` | PARTNER_COUNTRY | VALUE_USD | 10 | VALUE_USD:desc | A |
| `trend` | PERIOD | VALUE_USD | 1000 | PERIOD:asc | A |
| `comparison` | PARTNER_COUNTRY | VALUE_USD | 1000 | VALUE_USD:desc | A |
| `breakdown` | PARTNER_COUNTRY or product dim | VALUE_USD, NET_WEIGHT | 1000 | VALUE_USD:desc | A |
| `growth` | PARTNER_COUNTRY or PERIOD | VALUE_USD | 1000 | — | A |
| `trade_balance` | FLOW | VALUE_USD | 1000 | — | A |

**Key scoping decisions:**
- If the user specifies `group_by` / dimensions, those override defaults
- Comparison with EU → adds FLOW to group_by so both EX and IM show up per country
- Weight-based sort: if `sort_metric=NET_WEIGHT`, changes `sort` to `NET_WEIGHT:desc`
- `consolidate_flows` flag set for ranking when both flows must be summed together

---

## Stage 4 — Query Orchestration

**Purpose:** Combine the scoped plan with period/frequency resolution, filter construction, sort string assembly, and the `extra` metadata bag. Produce the final executable query plan.

| File | Role |
|---|---|
| `core/enrichment.py` → `orchestrate_query_plan()` | Stage 4 main function; produces `FinalQueryPlan` |
| `core/query_plan.py` → `FinalQueryPlan` | Stage 4 output dataclass |

**What happens:**

1. **Period resolution** (in priority order):
   - Explicit year from question (e.g. `"in 2025"`) → `period = "2025"`
   - `"last year"` / `"last decade"` → resolves to range `start_period` / `end_period`
   - Quarter/semester/month appended to year → `"2025-Q2"`, `"2025-S1"`, `"2025-03"`
   - No year at all → `default_year = current_year - 1` → `period = "2025"`
   - Growth intent → always expands to a 2-year range (current + prior year)

2. **Filter construction:** All enriched values (FLOW, PARTNER_COUNTRY, HS_HEADING, SITC_DIVISION, MODE_OF_TRANSPORT) → `filters` dict

3. **Sort assembly:** `"VALUE_USD:desc"`, `"NET_WEIGHT:desc"`, `"PERIOD:asc"` etc.

4. **Metrics cleanup:** Replaces VALUE_KHR with VALUE_USD, deduplicates

5. **Extra bag:** `{"consolidate_flows": bool, "user_limit": int, "trade_bloc": bool}`

6. **`FinalQueryPlan`** is a frozen dataclass with `filters`, `metrics`, `group_by`, `dimensions`, `period`, `start_period`, `end_period`, `frequency`, `sort`, `limit`, `offset`, `extra`

---

## Stage 5 — DAL Execution + Post-processing

**Purpose:** Execute the query against the Data Access Layer (DAL), apply post-filters, sanity-check the response, and rebuild the canonical source URL.

| File | Role |
|---|---|
| `core/service.py` → `query_from_question()` | Orchestrates stage 5 |
| `dal/dal_request_builder.py` → `build_request()` | Converts `FinalQueryPlan` → `DALRequest` |
| `dal/url_builder.py` → `build()` | Serializes `DALRequest` → HTTP query URL |
| `dal/dal_client.py` → `execute()` | Sends HTTP GET to `dal-app:8000`, retries on timeout/429 |
| `dal/dal_models.py` | `DALRequest` Pydantic model |
| `dal/exceptions.py` | `DALError` (wraps HTTP and network errors) |

**Post-processing steps (all in `service.py`):**

1. **FLOW post-filter** — Range queries can't combine FLOW and start/end period in a single DAL call (DAL bug). Workaround: FLOW filter removed from the DAL request, applied in Python after the response arrives.

2. **Time sub-period post-filter** — Range queries over-fetch (e.g. all months), then Python filters to the requested quarter/semester/month.

3. **Period sanity check** — If DAL returns records for a different period than requested, `dal_params["period"]` is corrected and the source URL is rebuilt from the url_builder with corrected params.

4. **URL rebuild** — `dal_source_url` is always rebuilt from the url_builder (using the corrected `dal_params`) to guarantee the logged URL matches what was actually served.

**DAL URL format:**
```
http://dal-app:8000/v1/query/trade_volume
  ?dimensions=PARTNER_COUNTRY
  &measures=VALUE_USD
  &version=1.0
  &period=2025
  &frequency=A
  &sort=VALUE_USD:desc
  &limit=10
  &filter=FLOW:eq:EX
  &filter=PARTNER_COUNTRY:in:VN,TH
```

---

## Stage 5b — Normalisation

**Purpose:** Convert raw DAL records into a clean, intent-specific response structure: `records`, `summary`, `table`, `visualization`, `metadata`.

| File | Role |
|---|---|
| `core/normaliser.py` → `normalise()` | Main normalisation dispatcher |
| `core/normaliser.py` → `compute_growth_rates()` | Growth rate computation (sole authority) |
| `visualization/chart_mapper.py` → `generate_visualizations()` | Builds `table` + `visualization` objects |
| `visualization/transformers.py` | `transform_to_bar_chart()`, `transform_to_line_chart()`, `transform_to_pie_chart()` |
| `visualization/registry.py` | Maps intent → chart type |

**Normalisation sub-steps:**

1. **Record cleaning:** Rename raw DAL keys to canonical names (`VALUE_USD`, `NET_WEIGHT`, `PARTNER_COUNTRY`, `PERIOD`, `FLOW`)

2. **Country name resolution:** ISO-2 codes (`VN`) → display names (`Viet Nam`) via `COUNTRY_NAMES` map

3. **Mode of transport resolution:** codes (`4`) → names (`Air transport`)

4. **Growth rate computation** (growth intent only): Pairs records by `PERIOD`, computes `growth_rate_pct = (new - old) / old × 100`

5. **Flow consolidation** (ranking with `consolidate_flows=true`): Sums EX + IM per country, sorts by the requested metric, caps at `user_limit`; NET_WEIGHT only included if explicitly requested

6. **Summary computation:** `total_trade_value`, `subset_total_value`, `subset_label` (`"top 10"` / `"bottom 5"`), `total_weight_kg`

7. **Table generation:** Lowercase column names, proper display values

8. **Visualization generation:**
   - `ranking` → horizontal `bar` chart, sorted by `sort_col` (VALUE_USD or NET_WEIGHT)
   - `trend` → `line` chart, multi-series if multiple flows or countries
   - `comparison` → `bar` chart
   - `breakdown` → `pie` chart
   - `summary` → `pie` chart
   - `growth` → `bar` chart (if growth valid) or fallback `line`
   - `trade_balance` → split `bar` chart (EX vs IM stacked)

**Visualization cap:**  `user_limit` from `extra` is passed to transformers — overrides the old hardcoded 15-item cap.

---

## Stage 6 — Natural Language Generation (NLG)

**Purpose:** Generate a human-readable message and follow-up suggestions from the normalised response.

| File | Role |
|---|---|
| `core/nlg/__init__.py` → `generate_nlg_response()` | Stage 6 entry point; injects facts, calls generator, attaches suggestions |
| `core/nlg/formatters.py` → `extract_facts()` | Extracts a flat `facts` dict from the payload + query_params |
| `core/nlg/generator.py` → `generate_message()` | LLM-first message generation with deterministic fallback |
| `core/nlg/suggestions.py` → `get_suggestions()` | Generates 3 follow-up question suggestions |

**NLG flow:**

```
payload + query_params
    │
    ▼
extract_facts()          ← formatters.py
    │   Builds a flat dict: intent, flow, period, partner, product,
    │   transport, metrics, records, totals, group_by, sort_param, ...
    │
    ▼
generate_message()       ← generator.py
    │
    ├─ [PRIMARY] LLM call to Gemini with structured facts as context
    │      → Returns a natural prose paragraph
    │
    └─ [FALLBACK] _generate_fallback_template() if LLM times out/fails
           → Deterministic template per intent:
```

**Fallback template logic per intent:**

| Intent | Template behaviour |
|---|---|
| `summary` | `"Cambodia's [flow] [product] [transport] in [period] was [value]."` |
| `ranking` | Entity-aware: uses `"transport modes"`, `"HS chapters"`, `"partners"` etc. based on group_by dim. Single-result → KPI sentence. Weight-sort → annotates `"(ranked by weight)"` and shows weight per item. |
| `trend` | Multi-flow detection: splits EX vs IM into labelled lines if both present |
| `comparison` | `"[Country A] ($X) vs [Country B] ($Y)..."` with a verdict if question asks "which is bigger" |
| `breakdown` | `"The breakdown of [flow] by [dim] in [period] was led by [top item]..."` |
| `growth` | `"[entity] [grew/declined] by [rate]% YoY..."` |
| `trade_balance` | `"Cambodia had a trade [surplus/deficit] of $X with [country] in [period]."` |

**Suggestions** (`suggestions.py`):
- Template-based, parameterized with the actual country/product/period from query_params
- 3 suggestions per response, intent-specific (e.g. "Show the monthly trend for Vietnam", "Break down by HS chapter")

---

## Data Flow Diagram by Intent

### `ranking` — "Top 10 export partners in 2025"
```
LLM: intent=ranking, year=2025, trade_direction=EX, limit=10
Stage 2: EX → FLOW=EX
Stage 3: group_by=[PARTNER_COUNTRY], sort=VALUE_USD:desc, limit=10
Stage 4: period=2025, freq=A, filters={FLOW:EX}
DAL: ?dimensions=PARTNER_COUNTRY&measures=VALUE_USD&period=2025&filter=FLOW:eq:EX&limit=10
Normalise: bar chart, top 10 rows, summary.subset_label="top 10"
NLG: "In 2025, Cambodia's top 10 export destinations were led by..."
```

### `comparison` — "Compare exports to Vietnam vs Thailand in 2025"
```
LLM: intent=comparison, year=2025, trade_direction=EX, partner_countries=[VN,TH]
Stage 2: VN,TH → ISO-2
Stage 3: group_by=[PARTNER_COUNTRY], limit=1000
Stage 4: period=2025, filters={FLOW:EX, PARTNER_COUNTRY:[VN,TH]}
DAL: ?filter=FLOW:eq:EX&filter=PARTNER_COUNTRY:in:VN,TH
Normalise: bar chart 2 bars
NLG: "In 2025, Cambodia's exports to Viet Nam ($3.73B) significantly exceed Thailand ($732M)."
```

### `trend` — "How have Cambodia's exports changed over the last 5 years?"
```
LLM: intent=trend, trade_direction=EX
Stage 4: start_period=2021, end_period=2025, freq=A
DAL: ?start-period=2021&end-period=2025&frequency=A
Normalise: line chart (1 series = EX, x-axis = PERIOD)
NLG: "Cambodia's exports have grown from $X in 2021 to $Y in 2025..."
```

### `breakdown` — "What is the breakdown of imports by transport mode in 2025?"
```
LLM: intent=breakdown, trade_direction=IM, group_by=[mode_of_transport]
Stage 3: group_by=[MODE_OF_TRANSPORT]
DAL: ?dimensions=MODE_OF_TRANSPORT&filter=FLOW:eq:IM&period=2025
Normalise: pie chart (slices = transport modes)
NLG: "In 2025, sea transport dominated imports at $X (Y%), followed by..."
```

### `growth` — "Which products had the fastest export growth in 2025?"
```
LLM: intent=growth, year=2025, trade_direction=EX
Stage 4: start_period=2024, end_period=2025 (auto-expanded for YoY)
DAL: ?dimensions=HS_HEADING&start-period=2024&end-period=2025
Normalise: compute_growth_rates() pairs 2024+2025 rows → growth_rate_pct
NLG: "The fastest growing export product in 2025 was X at +Y%..."
```

### `trade_balance` — "What is Cambodia's trade balance with China?"
```
LLM: intent=trade_balance, partner_country=CN
Stage 3: group_by=[PARTNER_COUNTRY, FLOW], no FLOW filter (both EX+IM needed)
DAL: ?filter=PARTNER_COUNTRY:in:CN (no FLOW filter)
Normalise: separate EX vs IM records, compute balance = EX - IM
NLG: "Cambodia had a trade deficit of $X with China in 2025 ($Y exports, $Z imports)."
Viz: split bar chart (EX green, IM red)
```

### `summary` — "How much did Cambodia trade with Vietnam in 2025?"
```
LLM: intent=summary, year=2025, partner_country=VN
Stage 3: group_by=[], no dimension grouping
DAL: ?filter=PARTNER_COUNTRY:in:VN&period=2025
Normalise: single aggregate value
NLG: "Cambodia's total trade with Viet Nam in 2025 was $X."
```

---

## Key Cross-Cutting Components

### `core/semantic_registry.py`
The **single source of truth** for all dimension codes, measure codes, intent rules, and their synonyms. Everything from `"export"→EX` to `"by country"→PARTNER_COUNTRY` is registered here. Scoping rules and URL builder both derive from this registry.

### `core/countries.py`
ISO-2 country code map with regex patterns (handles 200+ country name variants). Contains `REGIONAL_EXPANSIONS` that expand `"EU"` → 27 ISO-2 codes, `"ASEAN"` → 10 codes, etc.

### `core/validation.py`
`validate_query_plan()` — validates the `FinalQueryPlan` before execution. Rejects invalid intent, missing required fields, invalid period format. When validation fails, the error is fed back to the LLM as `retry_context`.

### `core/exceptions.py`
- `ValidationError` — bad input/extraction
- `NoResultsError` — query executed but returned 0 records (triggers graceful empty response)
- `UnknownIntentError` — intent not in the known set

### `core/nlg/formatters.py`
`COUNTRY_NAMES` dict (ISO-2 → display name). `extract_facts()` — flattens the full payload into a simple dict for the NLG generator so both LLM and template paths share the same inputs.

---

## Error Recovery Paths

```
LLM extraction failure (timeout/parse error)
    → Raises ValidationError → HTTP 422

LLM returns invalid params → Stage 4 validation fails
    → Retry loop feeds error back to LLM (up to 2 retries)
    → If still invalid after 3 attempts → HTTP 422

DAL timeout (3 retries, exponential backoff)
    → DALError → HTTP 504

DAL returns 0 records (NoResultsError)
    → Graceful: status=no_data, empty table/chart, single suggestion

NLG LLM timeout
    → Falls back to deterministic template (no error to user)
```

---

## File Reference Summary

| Layer | File | Purpose |
|---|---|---|
| Entry | `main.py` | Uvicorn boot |
| Entry | `app.py` | FastAPI factory + service init |
| API | `api/endpoints.py` | Route handlers |
| API | `api/schemas.py` | Pydantic I/O models |
| API | `api/validators.py` | Input validation |
| API | `api/exceptions.py` | HTTP exception mapping |
| Stage 1 | `core/llm_extractor.py` | LLM extraction + parsing |
| Stage 2 | `core/enrichment.py` (`enrich_query_plan`) | Semantic enrichment |
| Stage 2 | `core/semantic_registry.py` | Dimension/measure registry |
| Stage 2 | `core/countries.py` | Country code resolution |
| Stage 2 | `core/product_resolver.py` | HS/product name resolution |
| Stage 3 | `handlers/scopes.py` | Intent scoping rules |
| Stage 3 | `handlers/strategies.py` | Per-intent strategy configs |
| Stage 4 | `core/enrichment.py` (`orchestrate_query_plan`) | Query orchestration |
| Stage 4 | `core/query_plan.py` | Pipeline state dataclasses |
| Stage 4 | `core/validation.py` | Plan validation + repair trigger |
| Stage 5 | `core/service.py` | Full pipeline facade |
| Stage 5 | `dal/dal_request_builder.py` | Plan → DAL request |
| Stage 5 | `dal/url_builder.py` | DAL request → HTTP URL |
| Stage 5 | `dal/dal_client.py` | HTTP execution + retry |
| Stage 5b | `core/normaliser.py` | Response normalisation + growth |
| Stage 5b | `visualization/chart_mapper.py` | Table + chart generation |
| Stage 5b | `visualization/transformers.py` | Bar/line/pie chart builders |
| Stage 6 | `core/nlg/__init__.py` | NLG entry point |
| Stage 6 | `core/nlg/formatters.py` | Facts extraction |
| Stage 6 | `core/nlg/generator.py` | LLM message + fallback templates |
| Stage 6 | `core/nlg/suggestions.py` | Follow-up suggestions |
