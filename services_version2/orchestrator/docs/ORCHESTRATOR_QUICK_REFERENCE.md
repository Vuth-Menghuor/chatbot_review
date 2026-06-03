# Orchestrator Architecture - Quick Visual Guide

## 🎯 Main Data Flow

```
┌──────────────┐
│  HTTP Request│
│  /query      │
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────┐
│ ① INPUT VALIDATION                      │
│ - Injection detection                   │
│ - Security checks                       │
│ Location: api/endpoints.py              │
└──────┬────────────────────────────────┐─┘
       │                                │
       │ (SAFE)                   (UNSAFE)
       │                                │
       ▼                                ▼
┌──────────────────────┐     ┌─────────────────┐
│ ② INTENT DETECTION   │     │ Return Error    │
│ - LLM (optional)     │     │ (403 Refused)   │
│ - Keyword fallback   │     └─────────────────┘
│ Confidence: 0.0-1.0  │
│ Location:            │
│ core/workflow.py     │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│ ③ CURRENCY DETECTION (if CALCULATION)        │
│ - MiniLM embeddings                          │
│ - Pattern matching fallback                  │
│ - Defaults to KHR if unclear                 │
│ Location: core/workflow.py                   │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────┐
│ ④ INPUT VALIDATION - CALCULATION SPECIFIC    │
│ - Check for numeric value                    │
│ - Check for product/goods info               │
│ Location: core/workflow.py                   │
└──────┬───────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│ ⑤ SERVICE ROUTING (SWITCH BASED ON INTENT)                  │
│ Location: core/coordinator.py                               │
└──────┬──────────────────────────────────────────────────────┬┘
       │                                                        │
       │ ┌────────────────────────────────────────────────────┴──────────┐
       │ │                                                               │
       ▼ ▼                                                               │
   CALCULATION   TRADE_QUERY   HS_CODE_LOOKUP   DEFINITION/POLICY/OTHER │
       │             │               │                   │               │
       │             │               │                   │               │
       ▼             ▼               ▼                   ▼               ▼
   ┌────────┐   ┌─────────┐   ┌──────────┐        ┌──────────────────────┐
   │CALC    │   │TRADE    │   │RETRIEVAL │        │RETRIEVAL             │
   │SERVICE │   │QUERY    │   │SERVICE   │        │SERVICE               │
   │:8002   │   │SERVICE  │   │:8003     │        │:8003                 │
   │        │   │:8004    │   │(HS CODE  │        │(default collection)  │
   │        │   │         │   │collection)         │                      │
   └────┬───┘   └────┬────┘   └────┬─────┘        └──────────┬───────────┘
        │            │             │                         │
        │ Extract:   │             │                         │
        │ ├─Value   │ Extract:    │                         │
        │ ├─ Currency│ ├─ Origin   │ Collection:            │
        │ ├─ HS Code │ ├─ Dest     │ gdce_hs_code           │
        │ └─ Origin  │ └─ Period   │                         │
        │            │             │                         │
        │ POST       │ POST        │ POST                    │ POST
        │ /calculate │ /query      │ /retrieve              │ /retrieve
        │            │             │                         │
        └────┬────────┴─────────────┴────────────────────────┴─────────────┐
             │ (All results aggregated)                                     │
             ▼                                                              │
        ┌──────────────────────────────────────────────────────┐           │
        │ ⑥ RESPONSE BUILDING & FORMATTING                    │           │
        │ - Select answer source (calc/trade/retrieval)        │           │
        │ - Format based on intent type                        │           │
        │ - Extract citations & metadata                       │           │
        │ Location: core/coordinator.py                        │◄──────────┘
        └──────┬──────────────────────────────────────────────┘
               │
               ▼
        ┌──────────────────────────────────────────┐
        │ ⑦ LLM RESPONSE FORMATTING (Optional)     │
        │ - Skipped for calculation/trade          │
        │ - Used for definition/policy answers     │
        │ Location: api/endpoints.py               │
        └──────┬───────────────────────────────────┘
               │
               ▼
        ┌──────────────────────────────────────────┐
        │ ⑧ OUTPUT VALIDATION (Currently Disabled) │
        │ - Safety checks                          │
        │ Location: api/endpoints.py               │
        └──────┬───────────────────────────────────┘
               │
               ▼
        ┌──────────────────────────────────────────┐
        │ ⑨ RESPONSE RETURN                        │
        │ QueryResponse {                          │
        │   - request_id                           │
        │   - question                             │
        │   - answer                               │
        │   - intent                               │
        │   - status                               │
        │   - citations                            │
        │   - latency_ms                           │
        │ }                                        │
        └──────┬───────────────────────────────────┘
               │
               ▼
        ┌──────────────────────────────────────────┐
        │ HTTP 200 Response                        │
        │ (or 400/403/500 error)                   │
        └──────────────────────────────────────────┘
```

---

## 🔄 Intent Decision Tree

```
                    QUESTION RECEIVED
                          │
                          ▼
                  ┌───────────────────┐
                  │ CHECK KEYWORDS:   │
                  └─────────┬─────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   Contains        Contains              Contains
   calc/tax/      trade/export/          what is/
   duty keywords?  import keywords?     explain keywords?
        │                │                     │
        YES              YES                    YES
        │                │                     │
        ▼                ▼                     ▼
    CALCULATION    TRADE_QUERY            DEFINITION
        │                │                     │
        └────────┬───────┴─────────┬──────────┘
                 │                 │
                 NO               CONFIDENCE?
                 │                 │
                 ▼                 ├─ >= 0.75: USE IT
         Contains policy        │
         keywords?              └─ < 0.75: CONTINUE
         │
         YES
         │
         ▼
     POLICY_QUERY
         │
         └─→ (If all fail) → UNCLASSIFIED → RETRIEVAL
```

---

## 🔌 Service Integration Points

```
ORCHESTRATOR (Port 8001)
    │
    ├─→ [1] CALCULATOR SERVICE (Port 8002)
    │       Request:  POST /calculate_import_taxes
    │       Payload:  { goods, valuation, regime, flags }
    │       Response: { total_tax, breakdown, currency, exchange_rate }
    │
    ├─→ [2] RETRIEVAL SERVICE (Port 8003)
    │       Request:  POST /v1/retrieval/retrieve
    │       Payload:  { query, top_k, collection, generate_answer }
    │       Response: { documents, final_answer, answer_source, counts }
    │
    ├─→ [3] TRADE QUERY SERVICE (Port 8004)
    │       Request:  POST /query
    │       Payload:  { query, filters }
    │       Response: { data, total_trade_value, currency, count }
    │
    ├─→ [4] QDRANT (Vector DB - Host: 172.25.3.243:6333)
    │       Via Retrieval Service
    │       Collections: gdce_docs, gdce_hs_code
    │
    ├─→ [5] VLLM/OLLAMA (LLM Server - Port 8000/11434)
    │       Via LLM Intent Detector
    │       Model: llama3.2:3b or similar
    │
    └─→ [6] POSTGRESQL (Port 5432)
            Via Calculator/Trade Services
            Tables: hs_codes, duty_rates, trade_records
```

---

## 📊 Processing Time Breakdown

```
Typical CALCULATION Query: 500-1000ms

┌─────────────────────────────────────────────────────────┐
│ STEP                              │ TIME      │ CUMULATIVE│
├─────────────────────────────────────────────────────────┤
│ 1. Input Validation               │ 5ms       │ 5ms       │
│ 2. Intent Detection (keyword)     │ 10ms      │ 15ms      │
│ 3. Currency Detection (MiniLM)    │ 50-100ms  │ 65-115ms  │
│ 4. Input Validation (calc)        │ 5ms       │ 70-120ms  │
│ 5. Service Routing                │ 5ms       │ 75-125ms  │
│ 6. Calculator Service Call        │ 300-600ms │ 375-725ms │
│    ├─ Network roundtrip           │ 50ms      │           │
│    ├─ Processing                  │ 200-400ms │           │
│    └─ Response                    │ 50ms      │           │
│ 7. Response Formatting            │ 50-100ms  │ 425-825ms │
│ 8. LLM Formatting (skipped)       │ 0ms       │ 425-825ms │
│ 9. Output Validation (disabled)   │ 0ms       │ 425-825ms │
│ 10. Response Building             │ 50ms      │ 475-875ms │
│ 11. HTTP Response                 │ 25ms      │ 500-900ms │
└─────────────────────────────────────────────────────────┘
```

---

## ⚠️ Failure Scenarios

```
SCENARIO 1: Calculator Service Down
┌──────────────────────────────────────────────┐
│ Request: "Calculate tax on $500"             │
│ Intent: CALCULATION ✓                        │
│ Route to: Calculator Service                 │
│ Result: CONNECTION ERROR                     │
│ Action: FAIL ❌                              │
│ Expected: Should retry or fallback           │
│ Current: No retry, no fallback               │
└──────────────────────────────────────────────┘

SCENARIO 2: Unclear Currency
┌──────────────────────────────────────────────┐
│ Request: "Import tax for 500"                │
│ Intent: CALCULATION ✓                        │
│ Currency Detection: Confidence 0.15 < 0.6    │
│ Action: Default to KHR ✓                     │
│ Clarification Sent: YES ✓                    │
│ Result: Success with clarification           │
└──────────────────────────────────────────────┘

SCENARIO 3: Service Timeout
┌──────────────────────────────────────────────┐
│ Request: Query sent                          │
│ Processing: Takes >30 seconds                │
│ Action: Timeout error ❌                     │
│ Expected: Should degrade gracefully          │
│ Current: Hard failure                        │
└──────────────────────────────────────────────┘

SCENARIO 4: Repeated Query
┌──────────────────────────────────────────────┐
│ Request 1: "What is HS 0102.29.11?"          │
│ Action: Hit Retrieval Service                │
│ Action: Hit Qdrant                           │
│ Request 2: Same query 1 minute later         │
│ Action: Hit Retrieval Service AGAIN          │
│ Expected: Should use cache                   │
│ Current: No caching                          │
└──────────────────────────────────────────────┘
```

---

## 各点の状態チェック (Status Check)

```
✅ = Working well
⚠️  = Partially working/needs attention
❌ = Not implemented

COMPONENT                          STATUS    NOTES
─────────────────────────────────────────────────────────
API Input (endpoints.py)           ✅        Clean, well-structured
Input Validation                   ⚠️        Basic injection checks only
Intent Detection (LLM)             ✅        Good with fallback
Intent Detection (Keyword)         ✅        Comprehensive coverage
Currency Detection (MiniLM)        ✅        Recently implemented
Currency Detection (Fallback)      ✅        Pattern-based backup
Calculation Input Validation       ⚠️        Could be more robust
Service Routing Logic              ✅        Clean switch statement
Service Clients (HTTP)             ⚠️        No retry/circuit-breaker
Health Checks                      ⚠️        Only at startup
Request Timeout Handling           ⚠️        Fixed 15s, no context
Response Building                  ✅        Multiple format support
Citation Extraction                ✅        Works well
Error Handling                     ⚠️        Basic try-catch
LLM Response Formatting            ✅        Nice enhancement
Output Validation                  ❌        Disabled for testing
Metrics & Monitoring               ❌        Not implemented
Caching                           ❌        No cache layer
Rate Limiting                     ❌        Not implemented
Session Management                ⚠️        Passed but not used
Documentation                     ✅        Good inline comments
Unit Tests                        ✅        Test file exists
Integration Tests                 ⚠️        Limited coverage
```

---

## 🎯 Priority Matrix

```
                    EFFORT
                     Low    Medium   High
         ┌─────────────────────────────┐
IMPACT H │                             │
  I      │ #10 Rate Limit   #5 Cache  │ #7 Stream
  G      │ #9 Fallback      #4 Logging│ #8 Metrics
  H      │                             │
         ├─────────────────────────────┤
IMPACT M │ #6 Input Val  #12 Session   │
  E      │ #11 Multi-Lang #9 Fallback  │ #5 Cache
  D      │                             │
         ├─────────────────────────────┤
IMPACT L │ #13 Admin                   │ #7 Stream
  O      │                             │ #8 Metrics
  W      │                             │
         └─────────────────────────────┘

🔴 DO FIRST: #1, #2, #3 (Stability)
🟠 DO SOON:  #4, #5, #6 (Reliability)
🟡 DO LATER: #7, #8, #9, #10 (Performance)
🟢 OPTIONAL: #11, #12, #13 (Polish)
```

---

## 📝 Configuration & Environment

```
REQUIRED ENV VARS:
├─ ORCHESTRATOR_HOST (default: 127.0.0.1)
├─ ORCHESTRATOR_PORT (default: 8001)
├─ RETRIEVAL_SERVICE_URL (default: http://127.0.0.1:8003)
├─ CALCULATOR_SERVICE_URL (default: http://127.0.0.1:8002)
├─ TRADE_DATA_SERVICE_URL (default: http://127.0.0.1:8004)
├─ QDRANT_HOST (default: 172.25.3.243)
├─ QDRANT_PORT (default: 6333)
├─ VLLM_HOST (default: localhost)
├─ VLLM_PORT (default: 8000)
├─ OLLAMA_HOST (default: http://localhost:11434)
└─ OLLAMA_MODEL (default: llama3.2:3b)

CONFIG FILES:
├─ configs/orchestrator/intent_detection_rules.json
├─ configs/orchestrator/service_routing.json
├─ configs/orchestrator/validation_rules.json
└─ configs/orchestrator/response_formatting.json
```

---

## 🚀 Quick Start Commands

```bash
# Start orchestrator service
cd services_version2/orchestrator_version2
python -m uvicorn app:app --reload --port 8001

# Test query
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Calculate tax on $500 from China"}'

# Test with currency detection
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the duty on €2000 electronics?"}'

# Health check
curl http://localhost:8001/health

# View tests
pytest tests/ -v
```
