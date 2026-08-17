# GDCE Orchestrator Service — Technical Report
> Prepared for supervisor presentation | August 2026

---

## 1. What Is the Orchestrator?

The **GDCE Orchestrator** is a **FastAPI microservice** that acts as the intelligent "brain" of the GDCE chatbot. It sits between the front-end client and a collection of specialized backend microservices. Its job is to:

1. Accept a user's natural-language question
2. Understand what the user wants (intent classification)
3. Route the question to the right backend service
4. Manage multi-turn conversation history
5. Return a clean, formatted, language-correct answer

It runs on **Python + FastAPI**, uses **Gemini (Google AI)** as its primary LLM, and is designed to handle **Khmer and English** queries.

---

## 2. High-Level Architecture

```
Client (Frontend)
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│            GDCE Orchestrator (Port 8001)                 │
│                                                         │
│  ┌────────┐  ┌───────────────┐  ┌──────────────────┐   │
│  │  API   │→ │ ServiceCoord. │→ │  WorkflowExecutor│   │
│  │Endpoints│  │  (coordinator │  │ (intent classify,│   │
│  │/query  │  │    .py)       │  │  route, session) │   │
│  │/stream │  └───────────────┘  └──────────────────┘   │
│  └────────┘         │                                   │
│                     │                                   │
│    ┌────────────────┼──────────────────┐               │
│    ▼                ▼                  ▼               │
│ Calculator      Trade Data         Retrieval/         │
│ Service         Service            General Service    │
│ (duties/tax)   (statistics)       (HS code, docs)    │
│                                                         │
│  SessionManager  ←→  Redis  ←→  Disk JSON             │
│  (multi-turn context persistence)                       │
│                                                         │
│  DynamicPromptManager (YAML-based prompt registry)     │
│  CacheService (memory + Redis, 24–48h TTL)             │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Core Files Map

| File | Role |
|---|---|
| [`app/main.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/main.py) | FastAPI app factory, startup initialization sequence |
| [`app/services/coordinator.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/coordinator.py) | **Central brain** — the full orchestration pipeline (2 800 lines) |
| [`app/services/workflow.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/workflow.py) | `WorkflowContext`, `WorkflowExecutor`, intent detection, currency detection |
| [`app/services/session_context.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/session_context.py) | `SessionContext` dataclass + `SessionManager` (Redis + disk) |
| [`app/services/input_rewriter.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/input_rewriter.py) | Slot extraction, LLM-based query rewriting for multi-turn context |
| [`app/services/clarification_manager.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/clarification_manager.py) | Ask-back / clarification merge logic |
| [`app/services/heuristics.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/heuristics.py) | Shared regex/keyword helpers (typo correction, escape-hatch detection, etc.) |
| [`app/api/endpoints.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/api/endpoints.py) | `/query` (sync) and `/query/stream` (SSE streaming) HTTP endpoints |
| [`prompts/dynamic_prompt_manager.py`](file:///e:/GDCE-Intern/Local/orchestrator/prompts/dynamic_prompt_manager.py) | YAML-based prompt registry used by all LLM calls |
| [`app/ai/providers/gemini.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/ai/providers/gemini.py) | Gemini API client wrapper |
| [`app/infrastructure/cache_service.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/infrastructure/cache_service.py) | Hybrid memory+Redis cache (TTL: HS 24h, Definition 48h) |

---

## 4. Startup Initialization Sequence (7 steps)

When the server boots, [`create_app()`](file:///e:/GDCE-Intern/Local/orchestrator/app/main.py#L41) runs these steps:

```
[1/7] Input/Output Validators
[2/7] LLM Formatter (Gemini) — formats final answers
[3/7] PostgreSQL Trade Query Client (HTTP-based now)
[4/7] Service Clients (retrieval, general, calculator, trade_data)
[5/7] Health Check Service (120-second background polling)
[6/7] LLM First Layer (Gemini unified NLU: intent + entity + language)
[7/7] Service Coordinator assembled from all the above
[+]   Cache Service (memory + Redis, hybrid)
[+]   PostgreSQL Chatbot DB initialized + Alembic migrations run
```

---

## 5. The Full Query Processing Pipeline

> **Entry point:** `ServiceCoordinator.process_query()` → `_process_query_core()`

Every user message flows through the following 13 steps inside `_process_query_core()` ([coordinator.py L414](file:///e:/GDCE-Intern/Local/orchestrator/app/services/coordinator.py#L414)):

### Step 1 — Context Initialization
- A new `WorkflowContext` is created with a unique `request_id` (UUID4).
- Language metadata is stamped if the query was detected as Khmer.

### Step 2 — Light Normalization + Early Signals
- Query is lowercased and stripped: `_light_normalize_query()`
- **Currency detected early** via `WorkflowExecutor.detect_currency()` (pattern → LLM → country map → KHR default).
- **Session context loaded** from Redis or disk via `SessionManager.get_or_create_session()`.
- **Language-only request detected** (e.g. *"in Khmer"*): if session has history, translates the last bot reply directly — no LLM call.
- **Typo correction** applied via `_normalize_query_typos()` using a gazetteer of domain, country, and brand terms.
- **Product-spec merge**: if the previous turn flagged `product_clarification_needed=True`, the current reply is merged with the saved entity before any further processing.

### Step 3–4 — Predefined Small-Talk Fast Path
- If query was already identified as small talk (step 3 stamp), intent is locked immediately without running LLM.

### Step 5 — Input Validation & Scope Boundary
- Calls `validator.validate_input_full_async()` (checks injection, format, safety).
- If query **fails validation** → returns `validation_error` immediately.
- If query is **out of scope** (not customs/trade related) → calls `_build_out_of_scope_response()` with an LLM-generated warm refusal message.

### Step 6 — Session Context (already loaded in step 2)
- No-op placeholder kept for ordering clarity.

### Step 7 — Clarification Resolution (Ask-Back Reply Handling)
> This is **the heart of multi-turn conversation**. See §6 for full detail.

### Step 8 — Intent Classification & Safety Gates
- Checks the **unified NLU cache** from the first-layer Gemini call (done by the API endpoint *before* calling the coordinator).
- If cache hit on query key → uses `cached_intent` + `cached_confidence`.
- Otherwise: `WorkflowExecutor.detect_intent_with_confidence()` (LLM facade → native LLM detector → keyword fallback).
- **Safety gate** `_apply_intent_safety_gate()` applied to prevent dangerous intent transitions.
- **Post-intent small-talk gate**: if intent = `SMALL_TALK` but query is NOT a genuine greeting/farewell → refused as out-of-scope.
- Language (EN/KM) resolved and pinned into session.

### Step 9 — Core Intent Filtering
- Intents not in `{CALCULATION, TRADE_QUERY, HS_CODE_LOOKUP, GENERAL, SMALL_TALK}` → treated as small talk fallback.

### Step 10 — Dynamic Ask-Back (Ambiguity Detection)
> Also covered in §6. Triggered when:
> - `TRADE_QUERY`: NLU confidence < 0.85 and regex-vague, OR confidence < 0.60
> - All intents: confidence < 0.60

### Step 11 — Context-Aware Query Rewriting
- Detects if query is a **relative/ambiguous follow-up** (contains *"it", "that", "same"*, etc.)
- **Topic-switch detection**: if entity from NLU cache has no token overlap with `session.last_entity` → clears slot pollution via `clear_context_slots()`.
- If intent was locked from clarification merge → **skip LLM rewrite** (saves ~1–2s).
- Otherwise: calls `rewriter_service.rewrite_input()` via **Gemini** (Ollama as fallback).
- Rewrite **validated**: if rewrite bloats query too much or seems hallucinated → reverted to original.

### Step 12 — Microservice Routing
- `_resolve_target_service(intent)` maps intent → backend:

| Intent | Service |
|---|---|
| `CALCULATION` | Calculator service |
| `TRADE_QUERY` | Trade data service |
| `GENERAL` | General / RAG service |
| `HS_CODE_LOOKUP` | Retrieval service |
| `SMALL_TALK` | In-process LLM response |

- `_route_query(context)` dispatches the async call.

### Step 13 — Session Update & Response
- `rewriter_service.update_session_context()` saves: `last_intent`, `last_entity`, `last_raw_query`, `last_normalized_query`, `detected_currency`.
- `session_context.add_turn(user_input, bot_response)` appends the turn.
- `context.finalize()` timestamps and calculates `latency_ms`.
- `_build_response(context)` assembles the final response dict.
- Intent route + session context saved to **PostgreSQL** via `ChatbotDBService`.

---

## 6. Multi-Turn Historical Chat — How It Works

This is the most critical subsystem for your report.

### 6.1 The `SessionContext` Dataclass
[`session_context.py L27`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/session_context.py#L27)

Each chat session is a `SessionContext` with these key fields:

```python
@dataclass
class SessionContext:
    session_id: str
    turns: List[Dict]           # [{user, bot, ts}, ...] up to max_turns=8
    rolling_summary: str        # LLM-generated summary of evicted old turns
    
    # Slot state (carries facts across turns)
    import_export_mode: str     # "import" | "export"
    product_category: str       # e.g. "laptop"
    origin_country: str         # e.g. "China"
    destination_country: str
    hs_code: str                # e.g. "8471.30.10"
    cif_value: float            # e.g. 5000.0
    currency: str               # "USD", "KHR", etc.
    year: str
    month: str
    trade_agreement: str        # "ATIGA", "RCEP", etc.
    
    # Turn-to-turn state
    last_intent: str
    last_entity: str
    last_raw_query: str
    last_normalized_query: str
    
    # Ask-back state machine
    pending_clarification: bool
    clarification_intents: List[str]
    pending_rewritten_query: str
    ask_back_count: int
    
    # Product spec clarification
    product_clarification_needed: bool
    clarification_entity: str
    
    # Language state
    target_language: str        # "en" | "km"
    is_language_pinned: bool
    
    total_turns_count: int      # absolute counter (never resets)
```

### 6.2 Session Persistence (3 layers)

```
Request comes in
    │
    ▼
SessionManager.get_or_create_session(session_id)
    ├── 1. Check in-memory dict (fastest, same process)
    ├── 2. Try Redis:  GET session:{id}:context  (JSON blob, 1h TTL)
    └── 3. Fallback to disk: session_store/{id}.json

On any change (_trigger_change):
    ├── Write to disk (atomic: write .tmp → rename)
    └── Redis SET + XADD new turns to transcript stream
```

### 6.3 Turn Buffer & Rolling Summary
[`session_context.py L100`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/session_context.py#L100)

```python
def add_turn(self, user, bot):
    self.turns.append({"user": user, "bot": bot, "ts": now})
    self.total_turns_count += 1
    
    if len(self.turns) > self.max_turns (=8):
        evicted = self.turns[:overflow_count]
        self.turns = self.turns[overflow_count:]
        # Async LLM summarization of evicted turns
        async_summarize_evicted_turns(session, evicted)
```

When turns overflow, **Gemini is called asynchronously** to produce a concise `rolling_summary`. This is then prepended as context in the next rewrite prompt, giving the LLM "memory" of older conversation even without the raw turn log.

Fallback if Gemini is unavailable: concatenates turn snippets, truncates at 1600 chars on turn boundary.

### 6.4 Input Rewriting (Making Follow-ups Self-Contained)
[`input_rewriter.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/input_rewriter.py)

```
Turn 1: "What is the import duty for a laptop from China?"
Turn 2: "What about a phone?"
```

The rewriter:
1. Runs `extract_context_updates(user_input)` — a **deterministic slot extractor** (no LLM) that parses: country, product, CIF value, HS code, year, month, trade agreement, import/export mode.
2. Updates all slots on `SessionContext`.
3. Checks if required fields are satisfied for the current intent.
4. If yes → `build_rewrite_from_context()` produces: *"import duty for phone from China"*.
5. If no (e.g. query is *"what about that"*, no parseable slots) → **LLM path**: Gemini rewrites using last 5 turns + rolling summary + slot state.
6. Rewrite validated: if expansion ratio is too large or entity mismatch → reverted to original.
7. **Topic-switch guard**: if new entity has zero token overlap with `last_entity` → slot state wiped before rewrite (prevents pollution, e.g. iPhone → truck).

**Three-tier strategy**:
- `slot` — pure deterministic (fastest, 0ms LLM cost)
- `llm_gemini` — Gemini rewrites ambiguous follow-ups
- `merged_partial` — accumulated fragment buffer used when still incomplete

### 6.5 Ask-Back / Clarification State Machine
[`coordinator.py Step 7 & Step 10`](file:///e:/GDCE-Intern/Local/orchestrator/app/services/coordinator.py#L596)

When intent confidence is below threshold, a **clarification round-trip** is triggered:

```
Turn 1: "What about rice?" (ambiguous — HS lookup? calculation? trade data?)
    │
    ▼ [ASK-BACK TRIGGER: NLU confidence < 0.75]
Bot: "I can help with that! Are you looking for:
      (A) HS code for rice
      (B) Import duty calculation
      (C) Trade statistics"
    │
    ▼ SessionContext:
    pending_clarification = True
    clarification_intents = ["hs_code_lookup", "calculation", "trade_query"]
    pending_rewritten_query = "rice"
    
Turn 2: "B" (or "tax" or "calculation")
    │
    ▼ [Step 7: Clarification Resolution]
    resolved_intent = "calculation"
    ClarificationManager.merge_pending_with_clarification(
        pending_query = "rice",
        clarification_response = "B",
        resolved_intent = "calculation"
    )
    merged_query = "calculate import duty for rice"
    │
    ▼ Pipeline continues with locked intent, merged query
```

**Exit conditions** (the system stops waiting for clarification):
| Condition | Action |
|---|---|
| Small talk detected | Exit clarification, respond with greeting |
| High-confidence topic switch (conf ≥ 0.80) | Exit and process new topic |
| Mid-confidence switch (0.60–0.80) | Nested ask-back for new topic |
| Low-confidence switch (0.30–0.60) | Exit clarification |
| Escape-hatch phrase ("idk", "whatever") | Resolve to macro trade default |
| Max retries reached (`ask_back_count`) | Exit, use best-effort query |

**Product-spec clarification** (separate state machine):
- Triggered when retrieval returns a generic/ambiguous product.
- `product_clarification_needed = True` + `clarification_entity = "BMW M8"`.
- Next user message (e.g. "sports car") is merged back: *"BMW M8 Competition sports car"*.

---

## 7. Intent Classification System

### 7.1 Unified First-Layer (Gemini NLU)

Before `coordinator.py` is called, the API endpoint runs **Gemini's unified first-layer** prompt (`gemini_unified_first_layer` in `prompts/core_tasks/gemini/tasks.yaml`), which returns:

```json
{
  "intent": "calculation",
  "confidence": 0.92,
  "entity": "laptop",
  "entity_confidence": "high",
  "requested_language": "km",
  "is_language_explicitly_requested": true,
  "is_ambiguous": false
}
```

This single LLM call replaces many separate passes.

### 7.2 Intent Detection Priority (Keyword Fallback)

When the NLU cache misses, `WorkflowExecutor._keyword_based_intent_detection()` uses a **10-priority ladder**:

```
P0: Product + calculation signal → CALCULATION
P1: Numeric HS code pattern → HS_CODE_LOOKUP
P2: Service/fee markers (safety gate) → GENERAL
P3: "what is hs code" (asking to define HS) → GENERAL
P4: Explicit HS markers (hs code, tariff, classify) → HS_CODE_LOOKUP
P4B: Policy composite phrases ("how to import") → GENERAL
P4.5: Trade data keywords → TRADE_QUERY
P5: Definition keywords → GENERAL
P6: Calculation keywords → CALCULATION
P8: Short product noun phrase heuristic → HS_CODE_LOOKUP
P9: Policy engine fallback → (any)
```

### 7.3 Supported Intents

| Intent | Description | Backend |
|---|---|---|
| `calculation` | Import/export duty, tax, VAT calculation | Calculator service |
| `hs_code_lookup` | Find HS code for a product | Retrieval service |
| `trade_query` | Trade statistics, bilateral flows, volumes | Trade data service |
| `general` | Policy, procedure, definitions, compliance | General / RAG service |
| `small_talk` | Greetings, farewells, casual | In-process Gemini |
| `out_of_scope` | Off-topic (rejected) | — |

---

## 8. Language Support (EN/KH)

The orchestrator has a full **bidirectional Khmer↔English translation layer**:

```
User sends Khmer query
    │
    ▼ QueryTranslator.translate_to_english()
English query processed through entire pipeline
    │
    ▼ Final answer in English
    │
    ▼ QueryTranslator.translate_to_khmer()
Khmer answer returned to user
```

**Language state machine** on `SessionContext`:
- `target_language` = `"en"` or `"km"`
- `is_language_pinned` = `True` if user explicitly requested a language

**Language pinning**: *"answer in Khmer"* → all future responses in Khmer until user says *"use auto language"*.

**Batch translation** for suggestion chips and clarification questions (joined with `|###|` delimiter, translated in one call, split back).

---

## 9. Caching Strategy

[`app/infrastructure/cache_service.py`](file:///e:/GDCE-Intern/Local/orchestrator/app/infrastructure/cache_service.py)

| Layer | Type | Notes |
|---|---|---|
| L1 | In-memory LRU | Up to 5,000 entries, instant |
| L2 | Redis | Shared across workers (horizontal scale) |

**TTL by intent:**
```
calculation:   24 hours
hs_code_lookup: 24 hours
definition:    48 hours
policy:        48 hours
trade_query:   24 hours
general:       24 hours
```

**Not cached**: `small_talk`, `out_of_scope`, `validation_error` — these are never deterministic enough.

Admin endpoint: `GET /admin/cache-stats` shows hit rates, entry counts, memory usage.

---

## 10. Observability & Health

### Prometheus Metrics (endpoint: `/metrics`)
- `gdce_query_count` — per intent + status
- `gdce_query_duration_seconds` — histogram
- `gdce_service_errors` — per service + error type
- `gdce_cache_hits` / `gdce_cache_misses`

### Health Endpoints
| Endpoint | Use |
|---|---|
| `GET /health` | Liveness probe (K8s) |
| `GET /ready` | Readiness probe (K8s) |
| `GET /admin/health/status` | Detailed per-service health |
| `GET /admin/cache-stats` | Cache performance |
| `GET /admin/metrics/summary` | Human-readable Prometheus summary |

Background task runs every **120 seconds** checking all downstream services.

---

## 11. Key Design Decisions (Worth Mentioning to Supervisor)

| Decision | Rationale |
|---|---|
| **Single unified Gemini first-layer call** | Reduces LLM round-trips; returns intent + entity + language + ambiguity flag in one shot |
| **Clarification state machine in session** | Preserves ask-back across HTTP requests without server-side request state |
| **3-tier session persistence (memory → Redis → disk)** | No data loss on Redis failure; disk acts as durable backup |
| **Slot-based deterministic rewrite (no LLM for simple follow-ups)** | Saves ~1-2s latency when user provides enough parseable context |
| **Rolling LLM summary of evicted turns** | Gives infinite effective conversation memory without sending full history every request |
| **Topic-switch guard before rewriting** | Prevents polluting new topics with old slot values (iPhone vs truck) |
| **Language pinning** | User can request a language once and every subsequent response respects it |
| **Confidence-based ask-back matrix (7-row)** | Tuned per-intent; avoids over-asking for trade queries while still catching ambiguous calculations |

---

## 12. Data Flow Summary (One Request)

```
POST /query { question, session_id }
│
├─ Endpoint: run first_layer_service (Gemini unified NLU) → cache result
├─ Endpoint: acquire session lock (per session_id)
│
└─ coordinator.process_query()
   │
   ├─ translate Khmer → English (if needed)
   │
   └─ _process_query_core()
      ├─ [1]  Create WorkflowContext
      ├─ [2]  Normalize, detect currency, load session, typo-correct
      ├─ [3]  Product-spec merge (if awaiting spec clarification)
      ├─ [5]  Validate input + scope check
      ├─ [7]  Resolve ask-back clarification (if session was waiting)
      ├─ [8]  Classify intent (cache → LLM → keywords)
      ├─ [9]  Filter non-core intents → small talk
      ├─ [10] Trigger ask-back if ambiguous (returns early)
      ├─ [11] Rewrite query with session context (deterministic or LLM)
      ├─ [12] Route to backend microservice
      ├─ [13] Update session + save to DB
      └─ Build response → return
   │
   └─ translate English → Khmer (if target_language == km)
   └─ batch-translate suggestions/clarifications

→ QueryResponse { answer, intent, sources, suggestion, metadata }
```

---

*All file paths are clickable. Generated from live source code on 2026-08-14.*
