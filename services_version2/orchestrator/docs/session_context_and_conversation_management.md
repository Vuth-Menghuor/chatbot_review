# Session Context & Conversation Management Guide

This document provides a comprehensive breakdown of **Session Context**, **Conversation Memory**, **Multi-Tier Storage Architecture**, **Gating Rules**, and **End-to-End Query Processing** within the **GDCE Chatbot Orchestrator Service**.

---

## 1. High-Level User Flow & Pipeline Journey

The diagram below shows the streamlined 4-phase journey of a user message through the Orchestrator system:

```mermaid
flowchart TD
    %% Custom Node Styling
    classDef intake fill:#3498DB,stroke:#1F618D,stroke-width:2px,color:#fff;
    classDef ai fill:#8E44AD,stroke:#5B2C6F,stroke-width:2px,color:#fff;
    classDef gate fill:#F39C12,stroke:#B9770E,stroke-width:2px,color:#fff;
    classDef service fill:#2ECC71,stroke:#1E8449,stroke-width:2px,color:#fff;
    classDef memory fill:#16A085,stroke:#117A65,stroke-width:2px,color:#fff;

    subgraph PHASE1 ["1️⃣ INTAKE & PREPARATION"]
        User([👤 User Request]) --> Security{Passes Security?}:::intake
        Security -- No --> Blocked[🛑 Security Block]:::intake
        Security -- Yes --> LoadSession[📖 Load Session Memory & Lock Session]:::intake
        LoadSession --> TranslateIn[🌐 Translate Khmer ➔ English if needed]:::intake
    end

    subgraph PHASE2 ["2️⃣ CONTEXT & REWRITING"]
        TranslateIn --> CheckSpec{Follow-up Spec?}:::ai
        CheckSpec -- Yes --> MergeContext[🧩 Merge Spec Answer with Saved Context]:::ai
        CheckSpec -- No --> SmallTalk{Small-Talk?}:::ai
        MergeContext --> SmallTalk
        
        SmallTalk -- Yes --> FastReply[⚡ Polite Instant Reply]:::ai
        SmallTalk -- No --> Rewrite[🤖 Smart Rewriter: Strip Filler & Flesh Out Query]:::ai
    end

    subgraph PHASE3 ["3️⃣ ROUTING & GATING"]
        Rewrite --> Ambiguous{Clear or Ambiguous?}:::gate
        Ambiguous -- Ambiguous < 0.60 --> AskBack[❓ Ask-Back Gate: Ask User to Clarify Intent]:::gate
        
        Ambiguous -- Clear Intent --> Route[🎯 Microservice Router & Hybrid Cache]:::service
        Route --> Calc[🧮 Calculator Service<br/>Duties & Taxes]:::service
        Route --> Trade[📊 Trade Data Service<br/>Import/Export Stats]:::service
        Route --> Retrieval[🔍 Retrieval Service<br/>HS Tariff Codes]:::service
        Route --> General[📄 General Policy Service<br/>Rules & Regulations]:::service
    end

    subgraph PHASE4 ["4️⃣ RESPONSE & MEMORY UPDATE"]
        Calc & Trade & Retrieval & General & FastReply & AskBack --> Format[✨ Format Markdown Answer & Translate back to Khmer]:::memory
        Format --> Stream[🚀 SSE Token Stream to UI]:::memory
        Stream --> MemoryUpdate[💾 Update Memory Tiers<br/>• Active Window (Last 8 turns)<br/>• Rolling Summary (Evicted turn 9+)<br/>• Sync to Redis, Disk & Database]:::memory
    end
```

---

## 2. System Architecture & Memory Model

To maintain sub-300ms Time-To-First-Token and minimize LLM token costs, the Orchestrator employs a **two-tier memory model** combined with a **three-tier storage architecture**.

```mermaid
graph TD
    User([👤 User Request]) --> Step1[1. Security Validation & Session Retrieval]
    Step1 --> ActiveMem[Active Window Memory: Last 8 Turns]
    
    ActiveMem -- Turn 9+ Overflow Eviction --> Summarizer[Background Async Gemini Summarizer]
    Summarizer --> RollingSummary[Rolling Summary String <= 1600 chars]
    RollingSummary --> ActiveMem
    
    ActiveMem --> Tier1[(Tier 1: Instant Memory <br/> In-Memory + Redis Cache & Streams)]
    ActiveMem --> Tier2[(Tier 2: Disk Backup <br/> Atomic Local JSON Files)]
    ActiveMem --> Tier3[(Tier 3: Permanent Archive <br/> PostgreSQL Database)]
```

### Memory Tiers & Lifecycle

* **Active Window Memory (Last 8 Turns)**: The `SessionContext` maintains an active window array of up to 8 conversation turns (`max_turns = 8`). This keeps prompt payloads compact and prevents token bloat.
* **Eviction & Async Rolling Summary (Turn 9+)**: When conversation history exceeds 8 turns, the oldest turns are evicted from the active array. The `SessionManager` triggers an asynchronous background task (`async_summarize_evicted_turns`) using Gemini (`summarize_evicted_turns` prompt template) to update a running **Rolling Summary** text string (capped at 1,600 characters). If Gemini is unavailable, a deterministic fallback (`fallback_summary`) cleanly slices history on turn boundaries (`U:... B:...`).
* **Context Slots & Extended State**: Tracks domain parameters across turns:
  * `product_category`, `product_category_km`, `hs_code`, `cif_value`
  * `origin_country`, `destination_country`, `currency`, `commercial_description`
  * `year`, `month`, `trade_agreement`
  * `last_intent`, `last_entity`, `last_raw_query`, `last_normalized_query`

---

## 3. Three-Tier Storage Architecture

To ensure zero memory loss across server restarts, high throughput, and long-term analytics, state is saved across three tiers:

| Tier | Storage Layer | Mechanism & Implementation | Primary Purpose |
| :--- | :--- | :--- | :--- |
| **Tier 1** | **Instant Active Memory** | In-Memory `SessionContext` dict + Redis Cache (`session:{id}:context`, 1h TTL) + Redis Streams (`session:{id}:transcript` via `XADD`). | Ultra-fast context lookup (< 1ms) and real-time event streaming. |
| **Tier 2** | **Local Disk Backup** | Atomic JSON file persistence under `app/session_store/{session_id}.json`. Writes to `.tmp` file and atomically replaces. | Crash resilience and offline operation without external database dependencies. |
| **Tier 3** | **Permanent DB Archive** | PostgreSQL database persistence (`ChatSession`, `ChatMessage`, `transcript_archive`) via `ChatbotDBService` and background `session_flusher.py`. | Permanent storage, historical auditing, user history queries, and analytics. |

---

## 4. Dual Clarification & State Machine Architecture

The system features two independent, mutually exclusive state machines to handle conversation ambiguity:

```mermaid
graph TD
    Query[User Query] --> AmbiguityCheck{Is the Query Ambiguous or Incomplete?}
    
    AmbiguityCheck -- Low Intent Confidence < 0.60 --> IntentAskBack[Intent Ambiguity Ask-Back Gate]
    IntentAskBack --> AskUserIntent["❓ Prompt User to select intent <br/> (e.g., Calculate Tax vs Trade Data vs HS Lookup)"]
    AskUserIntent --> SaveState1[Set pending_clarification = True]
    
    AmbiguityCheck -- Missing Product Details --> SpecClarify[Product-Spec Clarification State Machine]
    SpecClarify --> AskUserSpec["❓ Prompt User for specific details <br/> (e.g., Engine CC, Electric/Petrol, CBU/CKD)"]
    AskUserSpec --> SaveState2["Set product_clarification_needed = True <br/> Save clarification_entity & expected_terms"]
    
    AmbiguityCheck -- Clear & Complete --> Rewrite[Smart Query Rewriter]
```

### A. Intent Ambiguity Ask-Back Gate
* **Trigger**: Low intent classification confidence ($< 0.60$) or multiple conflicting intents detected by `WorkflowExecutor`.
* **Behavior**: Halts downstream microservice routing immediately and prompts the user to clarify their request intention.
* **Tracked State**: `pending_clarification: bool`, `clarification_intents: List[str]`, `pending_rewritten_query: Optional[str]`, `ask_back_count: int`.

### B. Product-Spec Clarification State Machine
* **Trigger**: Required product technical specifications (e.g., engine CC, fuel type, vehicle assembly mode) are missing for accurate tariff lookup or calculation.
* **Retry Limit**: Capped at `MAX_PRODUCT_ASK_BACK_RETRIES = 2`.
* **Tracked State**: `product_clarification_needed: bool`, `clarification_entity: Optional[str]`, `clarification_last_query: Optional[str]`, `product_ask_back_count: int`, `clarification_expected_terms: List[str]`.
* **Spec Merging Logic**: Evaluates user input against `clarification_expected_terms` or category discriminators (`_SPEC_DISCRIMINATORS` for vehicle, food, textile). If valid detail is provided, it merges short answers with saved product entities:
  $$\text{"2000cc"} + \text{"Toyota Camry"} \longrightarrow \text{"2000cc Toyota Camry"}$$
* **Topic-Switch Guard**: If the user ignores the spec question and asks an unrelated question (e.g., *"Where is the customs office?"*), the state machine recognizes the topic switch, cancels spec clarification, resets state, and routes the new topic immediately.

---

## 5. Detailed Processing Pipeline Summary

1. **Intake & Preparation**: Passes security validation, acquires per-session lock, loads session context (Redis/Disk), and translates Khmer queries to English.
2. **Context & Rewriting**: Checks for follow-up spec answers (merging with saved product context), checks for small-talk fast-paths, strips filler words, and rewrites incomplete queries using Gemini.
3. **Routing & Gating**: Evaluates query clarity. Ambiguous queries ($< 0.60$ confidence) trigger an Ask-Back gate. Clear queries check the hybrid cache and route to specialized microservices (Calculator, Trade Data, Retrieval, General Policy).
4. **Response & Memory Update**: Formats the response into markdown, translates back to Khmer if requested, streams real-time tokens via SSE, updates the 8-turn active window, triggers background Gemini rolling summary on evicted turns, and persists state across Redis, local disk, and PostgreSQL.

---

## 6. Step-by-Step Scenario Analysis

### Scenario A: Lexical Noise (Fast Local Track)
* **User Question**: *"Um, actually, can you please tell me what is the import tax on rice?"*
* **Analysis**: Filler words (*"um"*, *"actually"*, *"can you please"*) constitute lexical noise.
* **Action**: Stripped instantly using regex in local code (**0ms additional latency**).
* **Rewritten Result**: `"what is the import tax on rice?"` $\rightarrow$ Routed to Calculator Microservice (Port 8002).

### Scenario B: Semantic Narrative Noise (Clean-up Track)
* **User Question**: *"I was talking to my business partner yesterday, and he told me that we want to import laptops, what documents do we need?"*
* **Analysis**: Narrative story markers (*"talking to my business partner"*, *"he told me"*).
* **Action**: Handled by `RewriterService` using Gemini context prompt or pre-warmed cache to extract core intent.
* **Rewritten Result**: `"what documents do we need to import laptops?"` $\rightarrow$ Routed to General Policy Microservice (Port 8005).

### Scenario C: Contextual Follow-Up Query (Memory Track)
* **Turn 1 User**: *"What is the import duty for rice?"* (Calculator intent; `product_category: "rice"` saved in slots).
* **Turn 2 User**: *"And for laptops?"*
* **Analysis**: Starts with relative prefix (*"And for"*), missing core intent verb.
* **Action**: `RewriterService` retrieves `last_intent` (`CALCULATION`) and session context to rewrite query.
* **Rewritten Result**: `"What is the import duty for laptops?"` $\rightarrow$ Routed to Calculator Microservice (Port 8002).

### Scenario D: Mid-Conversation Spec Clarification Merge
* **Turn 1 User**: *"Import tax for Toyota Camry"*
* **Bot Response**: *"Could you please specify the engine size (e.g. 2000cc, 2500cc, hybrid)?"* (`product_clarification_needed = True`, `clarification_entity = "Toyota Camry"`).
* **Turn 2 User**: *"2000cc"*
* **Analysis**: Input matches spec discriminator `2000cc`.
* **Action**: Merges answer with saved entity $\rightarrow$ `"2000cc Toyota Camry"`. Resets spec clarification state and routes query.
* **Result**: Tax calculation completed for a 2000cc Toyota Camry.

### Scenario E: Low Intent Confidence (Ask-Back Guard Track)
* **User Question**: *"import thing"*
* **Analysis**: Intent confidence score $< 0.60$.
* **Action**: Triggers Intent Ask-Back Gate (`pending_clarification = True`). Halts routing immediately.
* **Bot Response**: *"I'm not sure which service you need. Would you like to calculate duty fees, look up an HS tariff code, or view import regulations?"*

---

## 7. Summary of Gating & Trigger Rules

| Gate / Module | Trigger Criteria | Action Taken | Latency Impact |
| :--- | :--- | :--- | :--- |
| **Lexical Noise Cleaner** | Contains filler words (*"um"*, *"actually"*, *"please"*). | Regex string stripping in local code. | **0ms** (Instant local regex) |
| **Smart Query Rewriter** | Relative prefix (*"what about"*, *"and for"*) OR pronoun (*"it"*, *"they"*) OR short query ($\le 3$ words). | Uses `RewriterService` with past context slots & rolling summary. | **~100-200ms** (LLM rewrite) |
| **Intent Ask-Back Gate** | Intent confidence score $< 0.60$ OR multiple candidate intents. | Stops routing pipeline; prompts user to select target intent. | **0ms** (Halts execution early) |
| **Product-Spec Clarification** | Missing required product parameters (engine CC, fuel type, assembly mode). | Asks clarifying spec question; saves entity and expected terms (`MAX_RETRIES = 2`). | **0ms** (Pauses until next user turn) |
| **Async Rolling Summarizer** | Active turns array exceeds `max_turns = 8`. | Evicts oldest turns; generates Gemini background summary (max 1600 chars); updates DB. | **0ms** (Runs in background event loop) |
| **Hybrid Response Cache** | Matching query & parameters in Redis/Memory Cache. | Returns pre-computed response deltas instantly; bypasses downstream microservices. | **< 5ms** (Instant cache hit) |
