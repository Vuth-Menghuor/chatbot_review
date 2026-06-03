# Orchestrator Service v2 - Complete Architecture Guide

## 📋 Overview

**Orchestrator Service v2** is the central query router and coordinator for the GDCE ChatBot system. It:

1. **Receives** natural language questions from users via chat interface
2. **Detects** the user's intent (calculation, trade query, definition lookup, policy question, etc.)
3. **Validates** and parses input to extract structured parameters
4. **Routes** queries to appropriate backend services (Calculator, Retrieval, Trade Data)
5. **Orchestrates** multi-service workflows for complex queries
6. **Formats** responses using LLM for improved readability
7. **Validates** output for safety and accuracy
8. **Returns** comprehensive answers with citations and metadata

---

## 🗣️ Natural Language to Response Flow

The complete journey from user question to formatted answer:

```
User Chat Question (Natural Language)
        ↓
"Calculate tax for HS 0102.29.11 CIF $800 from China"
        ↓
Orchestrator Service (Port 8001)
├─ Receive query: QueryRequest { question, session_id }
├─ Intent Detection (Two-Layer System)
│  │
│  ├─ Layer 1: LLM Intent Classifier (Primary)
│  │  ├─ Query LLM with question
│  │  ├─ Get: intent + confidence score
│  │  └─ If confidence ≥ 0.65 → ✓ Accept and use this intent
│  │
│  └─ Layer 2: Keyword/Rule-based Detection (Fallback)
│     ├─ If MiniLM confidence < 0.65 → trigger Layer 2
│     ├─ Match question against keyword patterns
│     ├─ Apply rule-based classifier
│     └─ Use matched intent (or "general" if no match)
├─ Parse question text
├─ Extract parameters (example for calculation):
│  ├─ hs_code: "0102.29.11"
│  ├─ origin: "China" → "CN"
│  ├─ value: "800"
│  └─ currency: (MiniLM identifies + PostgreSQL lookup)
│     ├─ LLM determines currency type from query
│     ├─ Query PostgreSQL for exchange rate
│     └─ Default to KHR if LLM cannot determine
├─ Select workflow sequence (example for calculation)
│  ├─ Primary service: Calculator
│  ├─ Fallback: Retrieval (if HS code lookup needed)
│  └─ Validation: Input validators
├─ Call downstream services
│  ├─ (Optional) Retrieval Service for HS code lookup
│  ├─ (Primary) Calculator Service for duty calculation
│  └─ (Metadata) Trade Data Service for origin country info
├─ Aggregate responses
├─ Validate outputs
├─ Format response with LLM (for retrieval service and trade_query)
├─ Build structured QueryResponse JSON
└─ Return to user
        ↓
User Receives Formatted Answer:
"For HS code 0102.29.11 (Live cattle) importing $800 USD from China:
 • Customs Duty: 0 KHR (0%)
 • Special Tax: 0 KHR (0%)
 • VAT: 321,760 KHR (10%)
 • Excise Tax: 0 KHR (0%)
 ─────────────────────────────
 TOTAL TAX: 321,800 KHR

 Sources: Qdrant (172.25.3.243:6333), PostgreSQL exchange rates
 Exchange Rate: 1 USD = 4,022 KHR"
```

---

## 🏗️ Architecture Layers

```
┌─────────────────────────────────────────────────────────────────┐
│ API LAYER (FastAPI HTTP Interface - Port 8001)                  │
├─────────────────────────────────────────────────────────────────┤
│ • endpoints.py    → HTTP routes (/query, /chat, /health, /info) │
│ • schemas.py      → Request/response Pydantic models            │
│ • routes.py       → Router configuration                        │
│ • deps.py         → Dependency injection (get_coordinator)      │
└────────────────────┬────────────────────────────────────────────┘
                     │ passes QueryRequest, gets QueryResponse
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ ORCHESTRATION LAYER (Business Logic & Coordination)             │
├─────────────────────────────────────────────────────────────────┤
│ • coordinator.py      → Query orchestration & service routing   │
│ • workflow_executor.py → Intent detection & workflow selection  │
│ • validators.py       → Input/output validation & safety checks │
│ • llm_formatter.py    → LLM-based response formatting           │
│ • models.py           → Domain data structures                  │
│ • config.py           → Settings from .env & YAML               │
└────────────────────┬────────────────────────────────────────────┘
                     │ calls async RPC clients
         ┌───────────┼───────────┬────────────────┐
         ↓           ↓           ↓                ↓
    ┌─────────┐  ┌──────────┐ ┌────────────┐ ┌─────────────┐
    │Calculator│ │Retrieval │ │Trade Data  │ │PostgreSQL   │
    │Service   │ │Service   │ │Service     │ │(Rates)      │
    │Port 8002 │ │Port 8003 │ │Port 8004   │ │172.25.3.243 │
    └─────────┘  └──────────┘ └────────────┘ └─────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ INFRASTRUCTURE LAYER (External Service Clients & DB)            │
├─────────────────────────────────────────────────────────────────┤
│ • clients.py                                                    │
│   ├─ BaseServiceClient       → Abstract base for all clients    │
│   ├─ HttpxServiceClient      → Async HTTP implementation        │
│   ├─ RetrievalServiceClient  → Retrieval service (Port 8003)    │
│   ├─ CalculatorServiceClient → Calculator service (Port 8002)   │
│   ├─ TradeDataServiceClient  → Trade data service (Port 8004)   │
│   ├─ ServiceClientFactory    → Client creation factory          │
│   └─ ServiceRegistry         → Client lifecycle management      │
│                                                                 │
│ • postgres_adapter.py    → PostgreSQL database adapter          │
│   ├─ Exchange rate lookups                                      │
│   ├─ HS code duty rate queries                                  │
│   └─ Database connection pooling                                │
│                                                                 │
│ • cache_service.py       → Query response caching               │
│   ├─ In-memory cache (with TTL)                                 │
│   ├─ Redis support (optional)                                   │
│   └─ Cache statistics & cleanup                                 │
└─────────────────────────────────────────────────────────────────┘

**❓ About Qdrant Vector Database:**

> **Qdrant is NOT called directly by the Orchestrator service.**
>
> ✓ **Qdrant (172.25.3.243:6333)** is used **internally by the Retrieval Service** for:
>   - HS code vector similarity search (collection: gdce_hs_code)
>   - Duty rate lookups (collection: gdce_hs_code)
>   - Definition query (collection: gdce_docs)
>   - Policy query (collection: gdce_docs)
>   - General information query (collection: gdce_docs)
>
> ✓ **PostgreSQL (172.25.3.243)** IS called directly by Orchestrator for:
>   - Exchange rate lookups (conversion to KHR)
>   - Real-time rate caching
>
> **Service Separation:**
> - **Orchestrator** → Routes questions to services (does NOT access databases directly)
> - **Retrieval Service** → Handles HS code lookups, talks to Qdrant internally
> - **Calculator Service** → Gets rates from PostgreSQL, computes taxes
>

---

## 📊 Data Flow: Complete Query Processing

### Step 0: User Asks Question (Natural Language)

Real users don't send structured JSON. They ask questions like:

```

User Input Examples:
────────────────────────────────────────────────────────────

1. "Calculate tax for HS 0102.29.11 CIF $800 from China"
2. "What is the customs duty on oxen from Thailand?"
3. "How to import Honda motorcycles? Tax calculation needed."
4. "What's the HS code for tomatoes? And the duty rate?"
5. "Define 'CIF' in customs terminology"
6. "What documents do I need for FTA imports?"
7. "Tell me about customs procedures for Cambodia"

````

### Step 1: Receive Query at Orchestrator

```python
# api/endpoints.py → POST /query

@router.post("/query", response_model=QueryResponse)
async def process_query(
    req: QueryRequest,  # { "question": "...", "session_id": "..." }
    app_request: Request,
    coordinator=Depends(get_coordinator)
) -> QueryResponse:
````

**QueryRequest Schema:**

```json
{
  "question": "Calculate tax for HS 0102.29.11 cif $800 from China",
  "session_id": "session_abc123"
}
```

### Step 2: Input Validation & Scope Check

```python
# core/validators.py → InputValidator.validate_input()

QueryRequest {question, session_id}
        │
        ▼
1. CHECK SECURITY (Injection Detection)
   ├─ SQL injection patterns → REJECT if detected
   ├─ Prompt injection attempts → REJECT if detected
   └─ Command injection patterns → REJECT if detected

        │ (if safe)
        ▼
2. CHECK SCOPE (Is this a customs question?)

    In-Scope Keywords:

    ├─ HS Code Related:
    │  "hs code", "hs", "classify", "classification",
    │  "tariff code", "product code", "customs code"

    ├─ Trade / Tax Related:
    │  "import", "export", "duty", "tax", "tariff",
    │  "customs", "fee", "charge", "cost", "rate"

    ├─ Product Related:
    │  "product", "item", "goods", "thing",
    │  "laptop", "phone", "clothes"   ← (IMPORTANT: real items)

    ├─ Location / Trade Flow:
    │  "from", "to", "origin", "destination",
    │  "china", "usa", "vietnam", "thailand"

    ├─ Money / Value:
    │  "$", "usd", "riel", "€", "¥",
    │  "price", "value", "worth", "how much"

    ├─ Question Patterns (VERY IMPORTANT):
    │  "how much", "what is", "find", "calculate",
    │  "give me", "show me"

   Scope Decision:
   ├─ Has 1+ in-scope keywords → PROCEED (in_scope = true)
   └─ No in-scope keywords → MARK OUT_OF_SCOPE and REFUSE (in_scope = false)

   Example In-Scope:
   ✓ "What is the HS code for chicken?"              → in_scope (has "HS code", "chicken")
   ✓ "How much duty on $500 CIF from China?"        → in_scope (has "duty", "$", "from")
   ✓ "Calculate import tax for electronics"         → in_scope (has "import", "tax")

   Example Out-of-Scope:
   ✗ "How do I learn Python programming?"           → out_of_scope (no keywords)
   ✗ "Tell me about sports in Cambodia"             → out_of_scope (no keywords)

        │ (if in_scope)
        ▼
3. CHECK LENGTH VALIDATION
   ├─ Min length: 10 characters
   └─ Max length: 5000 characters

4. CHECK CHARACTER WHITELIST
   ├─ Allow: alphanumeric, spaces, currency symbols ($, ¥, €, ₹, ₽)
   ├─ Allow: common punctuation (., -, :, ;, ?)
   └─ Deny: script tags, special commands, etc.

        │ (passed all checks)
        ▼
RESULT:
├─ is_valid: true
├─ in_scope: true
├─ is_safe: true
└─ proceed_to_intent_detection: true

        │ (if in_scope ONLY)
        ▼
         **LLM NOW DECIDES THE USER'S SPECIFIC INTENT**
        │
        ├─ Question has customs keywords ✓
        ├─ Safe from injection ✓
        ├─ Valid format ✓
        └─ → Send to MiniLM for intent classification
        │
        ▼
        See Step 3 (Intent Detection with MiniLM)

REJECTION RESPONSE (if failed any check):
├─ reason: "out_of_scope" | "injection_detected" | "too_short" | "too_long" | "invalid_characters"
├─ status: 400 (scope/validation) or 403 (injection)
└─ message: "Your question is outside the scope of this customs agent. Please ask about HS codes, import/export duties, tariffs, or similar customs topics."
```

### Step 3: Intent Detection (MiniLM-based - In-Scope Questions Only)

**Purpose:** Determine what the user wants to do (Classification, Lookup, Calculation, etc.)

**ONLY CALLED IF:**

- ✓ Question passed security check (no injection)
- ✓ Question passed scope check (has customs keywords)
- ✓ Question passed format validation (length, characters)

**Process:**

```python
# core/workflow_executor.py → detect_intent_with_scope_check()
# workflow_executor.py → detect_intent()

In-Scope Validated Question {passed Step 2}
        │
        ▼
**Intent Classification: MiniLM Embeddings & Semantic Matching (Primary)**
        │
        ├─ Compute question embedding using MiniLM
        ├─ Compare against known intent patterns
        ├─ Return: (intent, confidence_score)
        │
        ├─ If confidence ≥ 0.65 → ✓ ACCEPT (use detected intent)
        │
        └─ If confidence < 0.65
                ▼
        Layer 2: Keyword / Rule-based Intent Detection (Fallback)
                │
                ├─ Match found → assign intent
                └─ No match → fallback to "general"
```

**Implementation Flow:**

````python
async def detect_intent(question: str) -> tuple[Intent, float]:
    """
    Two-layer intent detection system:
    Layer 1: MiniLM Embeddings (primary) - Fast, reliable semantic matching
    Layer 2: Keyword/Rule-based (fallback) - Regex pattern backup
    """

    intent = None
    confidence = 0.0

    # LAYER 1: MINILM INTENT CLASSIFIER (Primary)

    if MINILM_INTENT_DETECTION_ENABLED:
        try:
            minilm_result = await detect_intent_with_minilm(question)
            intent = minilm_result.intent
            confidence = minilm_result.confidence  # 0.0 - 1.0

            logger.debug(
                f"Layer 1 (MiniLM): intent={intent.value}, "
                f"confidence={confidence:.2f}"
            )

            # If MiniLM is confident enough, use it
            if confidence >= CONFIDENCE_THRESHOLD:  # 0.65
                logger.info(
                    f"✓ Layer 1 accepted: {intent.value} "
                    f"(confidence: {confidence:.2%})"
                )
                return intent, confidence
            else:
                logger.info(
                    f"⚠ Layer 1 low confidence: {intent.value} "
                    f"({confidence:.2%}) < threshold (75%) → "
                    f"Triggering Layer 2"
                )

        except Exception as e:
            logger.warning(f"Layer 1 (MiniLM) failed: {e} → Falling back to Layer 2")

    # LAYER 2: KEYWORD/RULE-BASED DETECTION (Fallback)

    logger.debug("Layer 2 (Keyword/Rule-based): Starting classification")

    # Preprocess question
    question_lower = question.lower()

    # 2a: Check exact keyword matches (highest priority)
    for detected_intent, keywords in KEYWORD_RULES.items():
        if any(kw in question_lower for kw in keywords):
            confidence = 0.85  # Rule-based detection confidence
            logger.info(
                f"✓ Layer 2 matched: {detected_intent.value} "
                f"(via keywords, confidence: 85%)"
            )
            return detected_intent, confidence

    # 2b: Check regex patterns
    for detected_intent, patterns in PATTERN_RULES.items():
        for pattern in patterns:
            if pattern.search(question):
                confidence = 0.80  # Pattern-based detection confidence
                logger.info(
                    f"✓ Layer 2 matched: {detected_intent.value} "
                    f"(via pattern, confidence: 80%)"
                )
                return detected_intent, confidence

    # 2c: Check compound rules (combinations)
    for detected_intent, rule_func in COMPOUND_RULES.items():
        if rule_func(question):
            confidence = 0.65  # Compound rule confidence
            logger.info(
                f"✓ Layer 2 matched: {detected_intent.value} "
                f"(via compound rule, confidence: 75%)"
            )
            return detected_intent, confidence

    # 2e: Check for GENERAL intent characteristics (Information Queries)
    # BEFORE defaulting - explicitly identify general/informational queries
    detected_general = check_general_intent(question)
    if detected_general:
        confidence = 0.65  # General intent medium confidence
        logger.info(
            f"✓ Layer 2 matched: Intent.GENERAL "
            f"(via general intent detection, confidence: 65%)"
        )
        return Intent.GENERAL, confidence

    # 2f: Final fallback - nothing matched
    # This should rarely happen if keywords are comprehensive
    logger.warning(
        f"⚠ Layer 2 no match found → Defaulting to Intent.GENERAL (fallback)"
    )
    return Intent.GENERAL, 0.50


def check_general_intent(question: str) -> bool:
    """
    Detect GENERAL intent (informational queries).

    ⚠️ CRITICAL: Double-check for HS code keywords!
    ========================================================

    Even if question starts with "what is", if it contains HS code keywords,
    it's HS_CODE_LOOKUP, NOT GENERAL!

    Examples:
    ✗ "What is the HS code for chickens?"
      → Has "what is" (general indicator)
      → BUT also has "HS code" keyword
      → Classification: HS_CODE_LOOKUP (not GENERAL)
      → Should NOT return True here!

    ✓ "What is an HS code?"
      → Has "what is" (general indicator)
      → NO specific HS code parameters
      → Classification: GENERAL ✓
      → Return True

    GENERAL intent characteristics:
    ├─ Asks for explanation/definition (what is, explain, how does)
    ├─ Seeks background information (describe, background on)
    ├─ NO specific intent parameters (no HS codes, no calculations, no lookups)
    ├─ No HS code keywords (classify, tariff code, product code, code for)
    ├─ No calculation keywords (calculate, compute, how much, duty, tax)
    └─ Broad informational scope (introduction, overview, concept)

    Returns True if question appears to be general/informational.
    """
    question_lower = question.lower()

    # General intent indicators (information-seeking)
    general_indicators = [
        "what is", "what are", "how does", "how is", "explain",
        "define", "meaning of", "describe", "tell me about",
        "information", "background", "overview", "introduction",
        "basics of", "concept of", "what does", "how come", "why"
    ]

    # Check if question contains general inquiry indicators
    has_general_indicator = any(ind in question_lower for ind in general_indicators)

    if has_general_indicator:
        # ⚠️ CRITICAL: Double-check for SPECIFIC intent keywords
        # Even with general indicators, these keywords indicate specific intent

        # HS Code keywords - these OVERRIDE "what is" indicator!
        hs_code_keywords = [
            "hs code", "classify", "classification", "tariff code",
            "product code", "code for", "hs ", "ahtn"
        ]
        has_hs_keywords = any(kw in question_lower for kw in hs_code_keywords)

        # Calculation keywords
        calc_keywords = [
            "calculate", "compute", "how much", "total", "cost",
            "duty", "tax", "import tax", "import duty"
        ]
        has_calc_keywords = any(kw in question_lower for kw in calc_keywords)

        # HS code pattern (e.g., "0102.29.11")
        has_hs_code_pattern = bool(re.search(r'\d{4}\.\d{2}\.\d{2}', question))

        # If question has ANY specific intent keywords → NOT GENERAL
        if has_hs_keywords or has_calc_keywords or has_hs_code_pattern:
            # Log the reason for rejection
            reason = []
            if has_hs_keywords:
                reason.append("HS code keywords")
            if has_calc_keywords:
                reason.append("calculation keywords")
            if has_hs_code_pattern:
                reason.append("HS code pattern")
            logger.debug(f"Rejected GENERAL classification due to: {', '.join(reason)}")
            return False

        # If it has general indicators but NO specific parameters:
        # → It's a GENERAL/INFORMATIONAL query
        return True

    return False


**Layer 2 Detection Strategy (All 5 Steps):**

| Step | Name | Detection Method | Confidence | Use Case |
|------|------|------------------|------------|----------|
| 2a | Keyword Match | Exact keyword search from 7 scope categories | 0.85 | Clear keyword matches (customs, HS, finance, docs, trade, policy, regions) |
| 2b | Pattern Match | Regex patterns (HS codes, currency, numbers) | 0.80 | Specific formats like `0102.29.11`, `$USD`, numeric values |
| 2c | Compound Rules | Multi-signal logic combinations | 0.65 | Complex patterns: "calculate duty for HS X", multi-keyword sequences |
| 2d | **GENERAL Intent** | **Information-seeking + 4-category double-check** | **0.65** | **"What is", "explain" BUT NO HS/calc/trade/policy keywords** |
| 2e | Fallback | Default when no pattern matches | 0.50 | Unclassifiable edge cases (rare) |

**Layer 1 vs Layer 2 Comparison:**

| Aspect                | Layer 1 (MiniLM)     | Layer 2 (Keyword/Rule) |
| --------------------- | -------------------- | ---------------------- |
| **Speed**             | < 100ms              | <10ms                  |
| **Accuracy**          | High (85-90%)        | High (85-90%)          |
| **Complex Questions** | ◐ Good for semantics | ◐ Limited              |
| **Confidence Score**  | 0.0-1.0 (semantic)   | 0.50-0.85 (fixed)      |
| **Fallback**          | → Layer 2 if low     | → GENERAL intent       |
| **Robustness**        | Always available     | Always available       |
| **Cost**              | Very low (local)     | Very low (local)       |

**Keyword Rules (Layer 2):**

```python
KEYWORD_RULES = {
    Intent.CALCULATION: [
        "calculate", "tax", "duty", "HS code", "$", "CIF", "FOB",
        "customs value", "import duty", "how much do I pay", "total tax",
        "customs duty calculation"
    ],
    Intent.DEFINITION: [
        "what is", "define", "meaning", "classified as",
        "what does", "explain", "describes"
    ],
    Intent.TRADE_QUERY: [
        "trade value", "trade data", "trade volume",
        "import value", "export value",
        "how much trade", "total export", "total import",
        "between", "from", "to",
        "by country", "trade statistics",
        "bilateral trade", "trade flow"
    ]
    Intent.POLICY_INQUIRY: [
        "regulation", "rule", "requirement", "FTA", "agreement",
        "policy", "law", "restricted", "prohibited", "allowed",
        "how do I", "steps for", "process of"
    ]
}

PATTERN_RULES = {
    Intent.CALCULATION: [

        # Natural language tax/duty questions
        re.compile(r'how much.*(tax|duty)', re.IGNORECASE),
        re.compile(r'(tax|duty).*(how much|calculate)', re.IGNORECASE),

        # Import + quantity + tax
        re.compile(r'import.*\d+.*(tax|duty)', re.IGNORECASE),

        # HS code related queries
        re.compile(r'HS\s*\d{4}\.\d{2}\.\d{2}.*(tax|duty|calculate)', re.IGNORECASE),

        # Incoterm + value
        re.compile(r'(CIF|FOB).*\d+', re.IGNORECASE),
    ],

    Intent.DEFINITION: [
        re.compile(r'what is .*', re.IGNORECASE),
        re.compile(r'define .*', re.IGNORECASE),
        re.compile(r'explain .*', re.IGNORECASE),
    ],

    Intent.TRADE_QUERY: [
        re.compile(r'(import|export|trade).*(from|to|between)', re.IGNORECASE),
        re.compile(r'(trade|import|export).*(value|volume|data)', re.IGNORECASE),
    ],

    Intent.POLICY_INQUIRY: [
        re.compile(r'(regulation|law|policy|rule)', re.IGNORECASE),
        re.compile(r'(restricted|prohibited|allowed)', re.IGNORECASE),
        re.compile(r'(FTA|agreement)', re.IGNORECASE),
    ]
}

COMPOUND_RULES = {

    Intent.CALCULATION: [
        lambda q: (
            ("tax" in q.lower() or "duty" in q.lower()) and
            ("how much" in q.lower() or "calculate" in q.lower() or any(char.isdigit() for char in q))
        ),
    ],

    Intent.TRADE_QUERY: [
        lambda q: (
            ("import" in q.lower() or "export" in q.lower() or "trade" in q.lower()) and
            ("from" in q.lower() or "to" in q.lower() or "between" in q.lower())
        ),
    ],

    Intent.POLICY_INQUIRY: [
        lambda q: (
            any(word in q.lower() for word in ["law", "regulation", "policy", "rule"]) or
            any(word in q.lower() for word in ["restricted", "prohibited", "allowed"])
        ),
    ]
}
````

**Detected Intents & Service Routing (6 Intents, 3 Services):**

| Intent             | Layer 1 MiniLM | Layer 2 Keyword/Rule | Primary Service    | Example Query                              |
| ------------------ | -------------- | -------------------- | ------------------ | ------------------------------------------ |
| **hs_code_lookup** | 0.80-0.90      | 0.85                 | Retrieval (8003)   | "What is the HS code for chickens?"        |
| **calculation**    | 0.65-0.88      | 0.85                 | Calculator (8002)  | "Calculate tax for HS 0102.29.11 CIF $800" |
| **definition**     | 0.80-0.90      | 0.85                 | Retrieval (8003)   | "Define CIF in customs"                    |
| **policy_query**   | 0.65-0.88      | 0.85                 | Retrieval (8003)   | "What are FTA requirements with ASEAN?"    |
| **trade_query**    | 0.70-0.85      | 0.80                 | Trade Data (8004)  | "Trade data: export textiles to Thailand"  |
| **general**        | <0.65          | 0.50                 | Retrieval (8003)\* | "Tell me about Cambodia customs"           |

**Service Routing Summary:**

- **Calculator (8002)**: calculation
- **Retrieval (8003)**: hs_code_lookup, definition, policy_query, general
- **Trade Data (8004)**: trade_query

**Example Detection Flows:**

**Example 1: Clear Calculation Query (Layer 1 MiniLM Succeeds)**

```
Query: "Calculate tax for HS 0102.29.11 CIF $800 from China"

Layer 1 (MiniLM):
├─ Analysis: "Clear tax calculation request via semantic matching"
├─ Intent: "calculation"
├─ Confidence: 0.86
└─ ✓ Result: ACCEPTED (0.86 ≥ 0.65 threshold)

Reasoning: MiniLM correctly matches question semantics to calculation intent
```

**Example 2: Ambiguous Query (Layer 1 Low Confidence, Layer 2 Succeeds)**

```
Query: "Tell me about duty tax I need to pay for importing items from China"

Layer 1 (MiniLM):
├─ Analysis: Could be definition or calculation
├─ Intent: "calculation"
├─ Confidence: 0.68
└─ ⚠ Result: REJECTED (0.68 < 0.65 threshold) → Trigger Layer 2

Layer 2 (Keyword/Rule):
├─ Keyword check: "duty" + "importing" matched in CALCULATION keywords
├─ Intent: "calculation"
├─ Confidence: 0.80
└─ ✓ Result: ACCEPTED

Final Intent: calculation (via Layer 2 fallback)
```

**Example 3: Unclear Query (Both Layers Uncertain)**

```
Query: "Tell me about Cambodia"

Layer 1 (MiniLM):
├─ Analysis: Generic country information (not customs-specific)
├─ Intent: "general"
├─ Confidence: 0.55
└─ ⚠ Result: REJECTED (0.55 < 0.65 threshold) → Trigger Layer 2

Layer 2 (Keyword/Rule):
├─ Keyword check: No matches in any intent category
├─ Pattern check: No patterns matched
├─ Compound check: No compound rules matched
└─ ⚠ Result: NO MATCH

Final Intent: general (default fallback, confidence: 0.50)
Routing: Multi-service or user prompt for clarification
```

---

## 📋 Scope Checking Reference (Step 2.2: Keywords)

**In-Scope Questions** (must contain ≥1 keyword):

| Category                   | Keywords                                                                                                                                             |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Core Customs**           | customs, import, export, duty, tax, tariff, cd, clearance, declaration, customs broker, valuation, classification                                    |
| **HS Code/Classification** | HS code, HS, ahtn, qip, sez, atiga, schedule, chapter, subheading, harmonized, classifier                                                            |
| **Financial/Value**        | CIF, FOB, VAT, exemption, excise, special tax, price, cost, total tax, custom duty, rate, %, percentage, currency, USD, KHR, EUR, THB, VND           |
| **Documents**              | invoice, packing list, bill of lading, form D, form E, certificate of origin, prakas                                                                 |
| **Trade/Movement**         | cargo, freight, shipping, transport, shipment, consignment, goods, merchandise, commodity                                                            |
| **Policies/Regulation**    | policy, procedure, regulation, requirement, process, steps, rule, mechanism, guideline, instruction, restricted, prohibited, allowed                 |
| **Regions/Agreements**     | Cambodia, ASEAN, RCEP, ATIGA, FTA, African, AANZFTA, ACFTA, diplomatic, NGO                                                                          |
| **Common Products**        | livestock (oxen, cattle, beef), poultry (chicken, fish), electronics (smartphone, laptop, phone), textile, metal, machinery, vehicle, food, medicine |

**Out-of-Scope Examples:**

- ✗ "How do I learn Python programming?" → No customs keywords
- ✗ "What's the score of the football match?" → Not customs-related
- ✗ "Tell me a recipe for pasta" → Cooking, not customs

**In-Scope Examples:**

- ✓ "What is the HS code for chicken?" → Has "HS code" + "chicken"
- ✓ "How much duty on $500 product from China?" → Has "duty", "$", "from" (implying country)
- ✓ "Is this product restricted under ASEAN trade rules?" → Has "restricted", "product", "ASEAN", "trade rules"

---

### Step 4a: Parameter Extraction (For Calculations)

```python
# core/workflow_executor.py → parse_calculation_request()

Pattern Matching for Calculation Queries:

Named Entity Recognition:
├─ HS Code:  Regex pattern: \b\d{4}\.\d{2}\.\d{2}\b
│            Example: "0102.29.11"
├─ Value:    Regex pattern: \$?[\d,]+(?:\.\d{1,2})?
│            Example: "$800", "2000", "1,200.50"
├─ Currency: LLM-based detection with PostgreSQL lookup
│            ├─ LLM analyzes query to identify currency type
│            ├─ Query PostgreSQL exchange_rates table for conversion rate
│            ├─ If LLM cannot determine currency → Default to KHR
│            └─ Examples: "USD", "$", "Khmer riel", "Thai baht", "Yuan"
├─ Origin:   Country mapping: "China" → "CN", "Singapore" → "SG"
│            Example: "from China"
└─ Date:     Regex pattern: \d{4}-\d{2}-\d{2}
             Example: "2026-04-01"

Fallback Extraction:
├─ If HS code not found: Call Retrieval Service
│  └─ Query: Product name (e.g., "oxen", "Honda Dream", "Iphone", "Horse", "Car")
│  └─ Returns: HS code + description (if could not find exact HS code return the 3 closest one base on description)
├─ If currency not found: LLM unable to determine + PostgreSQL lookup fails
│  └─ Default currency: KHR (Khmer riel)
│  └─ Log warning: "Currency not specified, using default KHR"
└─ If origin not found: Assume "unknown" country

Validation:
├─ HS code format valid: Must be 8 digits + 2 dots
├─ Value > 0: Must be positive number
├─ Currency supported: Check against approved list
└─ Origin country valid: Check ISO 3166 country codes

Example Extraction:

Query: "Calculate tax for HS 0102.29.11 CIF $800 from China"
Extracted:
├─ hs_code: "0102.29.11" ✓
├─ customs_value: 800 ✓
├─ currency: "USD" ✓ (LLM detected "$" → USD, PostgreSQL rate: 1 USD = 4,022 KHR)
├─ origin_country: "CN" ✓
└─ calculation_date: "2026-04-01" (today) ✓
```

### Step 4b: Workflow Selection

```python
# core/workflow_executor.py → get_workflow_sequence()

Based on detected intent, select service sequence:

Workflow 1: CALCULATION (Most Common)
├─ 1. Validate parameters (has HS code, value, currency)
├─ 2. (If needed) Lookup HS code from given product name
│     └─ Call Retrieval Service: /lookup/hs-code
├─ 3. Primary: Call Calculator Service: /calculate_import_taxes
├─ 4. Parse response
├─ 5. Format response
└─ 6. Return to user
Time: ~500ms-2s (depends on service latency)

Workflow 2: DEFINITION LOOKUP
├─ 1. Extract search term (HS code or given product name)
├─ 2. Call Retrieval Service: /lookup/hs-info
├─ 3. Return description + related info
└─ Time: ~200-500ms

Workflow 3: POLICY / PROCEDURE QUESTION
├─ 1. Classify question type (FTA, documentation, procedures, etc.)
├─ 2. Call Retrieval Service: /search/policy
├─ 3. Return relevant policy info
└─ Time: ~300-800ms

Workflow 4: TRADE DATA QUERY
├─ 1. Extract search parameters
├─ 2. Call Trade Data Service: /query
├─ 3. Return statistics / trends
└─ Time: ~500ms-2s

Workflow 5: FALLBACK (Unclassified / Complex)
├─ 1. Try Calculator Service
├─ 2. Try Retrieval Service
├─ 3. Try Trade Data Service
└─ Return first successful result
```

### Step 5: Call Downstream Services

````python
# core/coordinator.py → process_query()

Example: Calculation Workflow

1. Build CalculationRequest JSON (internal format)
   ```json
   {
     "calculation_date": "2026-04-01",
     "regime": "normal",
     "goods": {
       "hs_code": "0102.29.11",
       "description": "Live cattle"
       "origin_country": "CN",
     },
     "valuation": {
       "customs_value": 800,
       "currency": "USD"
     }
   }
````

2. Call Calculator Service (async, with timeout)

   ```python
   async with httpx.AsyncClient() as client:
       response = await client.post(
           "http://calculator:8002/v1/calculate_import_taxes",
           json=calculation_request,
           timeout=10.0
       )
       calculator_result = response.json()
   ```

3. Handle success/failure:

   ```
   If status 200:
   ├─ Extract: total, breakdown, line_items, assumptions
   └─ Continue to response aggregation

   If status 4xx/5xx:
   ├─ Log error
   ├─ Try fallback service (if configured)
   └─ Return error response to user
   ```

### Step 6: Output Validation

```python
# core/validators.py → OutputValidator.validate_response()

Checks performed on response content:

1. Content Safety
   ├─ Check for harmful content
   ├─ Check for misleading information
   └─ Check for confidential data exposure

2. Format Validation
   ├─ Is total a positive number?
   ├─ Are all tax components present?
   ├─ Are breakdowns consistent with total?
   └─ Example: CD + ST + VAT + ET = Total (within rounding)

3. Accuracy Checks
   ├─ Exchange rate reasonable? (between 0.1 and 10000)
   ├─ Tax rates reasonable? (between 0% and 100%)
   └─ Values in expected range?

4. Citation Validation
   ├─ All sources present?
   ├─ References valid?
   └─ Data freshness acceptable?

Result:
├─ is_safe: true/false
└─ issues: ["..." ] (if any)
```

### Step 7: LLM Response Formatting (Optional)

```python
# llm_formatter.py → format_response_with_llm()

This step IMPROVES readability but is OPTIONAL:

Base Answer (from Calculator):
"Total: 321800 KHR. Breakdown: CD=0, ST=0, VAT=321760, ET=0"

LLM Prompt:
```

You are a customs expert. Format this tax calculation in a clear, user-friendly way.
Base answer: "Total: 321800 KHR. Breakdown: CD=0, ST=0, VAT=321760, ET=0"
Question: "Calculate tax for HS 0102.29.11 CIF $800 from China"
HS Code info: "0102.29.11 - Live cattle (excluding buffalo)"

Create a response that:

1. Is clear and professional
2. Explains the tax components
3. Includes the total amount prominently
4. Mentions assumptions

```

LLM-Formatted Answer:
```

For importing live cattle (HS 0102.29.11) valued at $800 USD from China:

TOTAL TAX: 321,800 KHR (rounded from 321,760 KHR)

Tax Breakdown:
• Customs Duty: 0 KHR (0% rate - no duty on cattle)
• Special Tax: 0 KHR (not applicable)
• VAT: 321,760 KHR (10% tax on $800 USD equivalent)
• Excise Tax: 0 KHR (not applicable)

The VAT is calculated on the CIF value (Cost, Insurance, Freight).
Exchange rate used: 1 USD = 4,022 KHR

```

Skip LLM formatting if:
├─ LLM service unavailable
├─ Response already well-formatted
└─ Config setting disables it
```

### Step 7b: Enhanced Response Formatting for CALCULATION Intent

**Goal:** Display step-by-step calculations with formulas so users understand the tax breakdown.

For CALCULATION intents specifically, the LLM formatter should include:

```python
# llm_formatter.py → format_calculation_response()

Enhanced LLM Prompt for Calculations:
"""
You are a customs expert. Format this tax calculation showing step-by-step formulas.

Base Answer: Total: 321800 KHR. Breakdown: CD=0, ST=0, VAT=321760, ET=0
Question: Calculate tax for HS 0102.29.11 CIF $800 from China
HS Code Info: 0102.29.11 - Live cattle (excluding buffalo)

✓ INCLUDE in response:
1. Product information and HS code details
2. Input parameters (CIF value, currency, origin)
3. Exchange rate conversion IF currencies differ
4. STEP-BY-STEP calculation with FORMULAS:
   - Step 1: Convert CIF value to KHR if needed (formula: value_usd × exchange_rate)
   - Step 2: Calculate duty (formula: cif_value_khm × duty_rate)
   - Step 3: Calculate VAT (formula: (cif_value_khm + duty) × vat_rate)
   - Step 4: Calculate special taxes if applicable
5. Line-by-line breakdown with rates and percentages
6. TOTAL TAX prominently displayed

✓ FORMAT:
- Use simple, clear language
- Show all calculations step-by-step with formulas
- Use professional formatting (║, ─, etc.)

✗ DO NOT:
- Use abbreviations without explanation first time (explain CD, ST, VAT, ET)
- Skip steps - show every calculation
"""

Enhanced User Response Example:
```

─────────────────────────────────────────────────────────────
IMPORT TAX CALCULATION
─────────────────────────────────────────────────────────────

PRODUCT INFORMATION:
• HS Code: 0102.29.11 (Live cattle excluding buffalo)
• Origin Country: China (CN)
• Incoterm: CIF (Cost, Insurance, Freight)

INPUT PARAMETERS:
• CIF Value: $800 USD
• Exchange Rate: 1 USD = 4,022 KHR
• Customs Regime: Normal (standard rates)
• Calculation Date: 2026-04-01

─────────────────────────────────────────────────────────────
STEP 1: CURRENCY CONVERSION (USD → KHR)
─────────────────────────────────────────────────────────────
Formula: CIF Value (USD) × Exchange Rate
= $800 × 4,022 KHR/USD
= 3,217,600 KHR

─────────────────────────────────────────────────────────────
STEP 2: CUSTOMS DUTY CALCULATION
─────────────────────────────────────────────────────────────
Formula: CIF Value (KHR) × Duty Rate
CIF Value: 3,217,600 KHR
Duty Rate for HS 0102.29.11: 0% (No duty on live cattle)
= 3,217,600 × 0%
= 0 KHR

─────────────────────────────────────────────────────────────
STEP 3: SPECIAL TAX (if applicable)
─────────────────────────────────────────────────────────────
Formula: CIF Value (KHR) × Special Tax Rate
Special Tax Rate: 0% (Not applicable for live cattle)
= 3,217,600 × 0%
= 0 KHR

─────────────────────────────────────────────────────────────
STEP 4: VALUE ADDED TAX (VAT)
─────────────────────────────────────────────────────────────
Formula: (CIF Value + Duty + Special Tax) × VAT Rate

Taxable Base = CIF Value + Customs Duty + Special Tax
= 3,217,600 + 0 + 0
= 3,217,600 KHR

VAT Rate: 10%
VAT = 3,217,600 × 10%
= 321,760 KHR

─────────────────────────────────────────────────────────────
STEP 5: EXCISE TAX (if applicable)
─────────────────────────────────────────────────────────────
Formula: (CIF Value + Duty + Special Tax + VAT) × Excise Rate
Excise Tax Rate: 0% (Not applicable for live cattle)
= (3,217,600 + 0 + 0 + 321,760) × 0%
= 0 KHR

─────────────────────────────────────────────────────────────
FINAL TAX BREAKDOWN
─────────────────────────────────────────────────────────────
│ Tax Component │ Amount (KHR) │ Rate │ Status │
├─────────────────────────────────────────────────────────────┤
│ Customs Duty │ 0 │ 0% │ No duty │
│ Special Tax │ 0 │ 0% │ Not applied │
│ VAT │ 321,760 │ 10% │ Applied │
│ Excise Tax │ 0 │ 0% │ Not applied │
├─────────────────────────────────────────────────────────────┤
│ TOTAL TAX │ 321,760 KHR │ │ │
└─────────────────────────────────────────────────────────────┘

SUMMARY:
To import 1 consignment of live cattle (HS 0102.29.11) valued at
$800 CIF from China, you must pay 321,760 KHR in import taxes.
The majority is VAT (10% tax on the imported value).

ASSUMPTIONS & NOTES:
✓ Exchange rate as of 2026-04-01: 1 USD = 4,022 KHR (from PostgreSQL)
✓ HS Code confirmed from Qdrant database
✓ Duty rate: 0% - Live cattle imports are duty-free under current regulations
✓ Calculation assumes standard import regime (normal imports)
✓ All rates current as of April 1, 2026

DATA SOURCES:
• HS Code Database: Qdrant (172.25.3.243:6333/collections/gdce_hs_code)
• Exchange Rates: PostgreSQL (172.25.3.243/gdce_rates)
• Duty Rates: Qdrant (172.25.3.243:6333/collections/gdce_hs_code)

────────────────────────────────────────────────────────────

````

**Implementation Details:**

```python
# llm_formatter.py

def format_calculation_response(
    original_question: str,
    calculator_response: CalculatorResponse,
    hs_code_info: HSCodeInfo,
    exchange_rate: float,
    llm_client: LLMClient
) -> str:
    """
    Format calculation response with step-by-step formulas.

    For CALCULATION intents, this creates an educational output
    showing every calculation step with formulas.
    """

    # Build detailed calculation breakdown with formulas
    calculation_details = build_detailed_breakdown(
        calculator_response=calculator_response,
        exchange_rate=exchange_rate,
        hs_code_info=hs_code_info
    )

    # Create enhanced LLM prompt with formulas
    llm_prompt = f"""
    {FORMAT_CALCULATION_PROMPT_TEMPLATE}

    Base Answer: {calculator_response.summary}
    Question: {original_question}
    HS Code Info: {hs_code_info.description}
    Exchange Rate: 1 USD = {exchange_rate} KHR

    Detailed Breakdown with Formulas:
    {calculation_details}
    """

    # Get LLM to format nicely
    formatted_response = await llm_client.format_text(llm_prompt)

    return formatted_response
```

**When to Use Full Formula Breakdown:**
- ✓ CALCULATION intent with numeric computations
- ✓ When exchange rate conversion is needed
- ✓ When multiple tax components apply
- ✓ When user asks "how" or "show me the calculation"

**When to Use Simplified Format:**
- ◐ When only one tax component applies (simplify to 2-3 key steps)
- ◐ If response is already very long (keep summary only)
- ◐ If configuration disables detailed mode
````

### Step 8: Build Response JSON

````python
# core/coordinator.py → aggregation logic

```json
{
  "request_id": "req_20260401_1142_xyz789",
  "question": "Calculate tax for HS 0102.29.11 CIF $800 from China",
  "answer": "For importing live cattle (HS 0102.29.11)...",
  "intent": "calculation",
  "status": "completed",
  "latency_ms": 847.5,

  "citations": [
    {
      "source_name": "Qdrant HS Code Database",
      "source_url": "http://172.25.3.243:6333/dashboard#/collections/gdce_hs_code",
      "reference": "HS code 0102.29.11 - Live cattle",
      "confidence": "high",
      "accessed_at": "2026-04-01T11:42:30Z"
    },
    {
      "source_name": "PostgreSQL Exchange Rates",
      "source_url": "172.25.3.243/gdce_hs_code",
      "reference": "USD to KHR: 4,022",
      "confidence": "high",
      "accessed_at": "2026-04-01T11:42:32Z"
    }
  ],

  "metadata": {
    "intent_confidence": 0.95,
    "workflow_duration_ms": 847.5,
    "services_called": ["calculator"],
    "session_id": "session_abc123",
    "conversation_turn": 1
  },

  "errors": [],
  "clarifications": []
}
````

---

## 🔄 Service Integration Points

### 1. Calculator Service Client (`infrastructure/calculator_client.py`)

**Purpose**:

- Calculate total import duties and taxes (CD, ST, VAT, ET)
- Used when user asks about import cost, duty, or tax estimation

**Triggered When**:

- Intent = "tax_calculation"
- Required entities present:
  ├─ product (or HS code)
  ├─ origin country
  ├─ value (amount + currency)

**Connection Details:**

- Host: `CALCULATOR_HOST` (default: `127.0.0.1`)
- Port: `CALCULATOR_PORT` (default: `8002`)
- Protocol: HTTP/REST (async)
- Timeout: 10 seconds (configurable)

**Available Endpoints:**

```
POST /v1/calculate_import_taxes
├─ Purpose: Calculate import duties and taxes
├─ Request: { calculation_date, regime, goods, valuation }
├─ Response: { total, breakdown, line_items, assumptions }
└─ Time: ~300-800ms

GET /v1/lookup/duty-rate
├─ Purpose: Get duty rates for specific HS code
├─ Query: ?hs_code=0102.29.11&origin_country=CN
├─ Response: { cd_rate, st_rate, vat_rate, et_rate }
└─ Time: ~100-300ms

GET /v1/health
├─ Purpose: Health check
├─ Response: { status, version, qdrant_connected }
└─ Time: ~50ms
```

**Example Usage:**

```python
# orchestrator/infrastructure/calculator_client.py

async def calculate_taxes(
    hs_code: str,
    origin_country: str,
    customs_value: float,
    currency: str
) -> dict:
    """Call calculator service and return result."""

    request_payload = {
        "calculation_date": "2026-04-01",
        "regime": "normal",
        "goods": {
            "hs_code": hs_code,
            "origin_country": origin_country,
        },
        "valuation": {
            "customs_value": customs_value,
            "currency": currency
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://{CALCULATOR_HOST}:{CALCULATOR_PORT}/v1/calculate_import_taxes",
            json=request_payload,
            timeout=10.0
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise CalculationError(f"Calculator service error: {response.text}")
```

### 2. Retrieval Service Client (`infrastructure/retrieval_client.py`)

**Purpose:** Handles all lookup operations EXCEPT trade statistics:

- ✓ HS Code lookups (HS_CODE_LOOKUP intent)
- ✓ General information lookups (DEFINITION, GENERAL intents)
- ✓ Policy & procedure lookups (POLICY_QUERY intent)
- ✓ Regulatory & compliance information
- ✗ NOT trade statistics (use Trade Data Service for that)

**Connection Details:**

- Host: `RETRIEVAL_HOST` (default: `127.0.0.1`)
- Port: `RETRIEVAL_PORT` (default: `8003`)
- Protocol: HTTP/REST (async)
- Timeout: 15 seconds (configurable)
- Backend: Qdrant Vector Database (172.25.3.243:6333)
  - Collection 1: `gdce_hs_code` (HS codes & duty rates)
  - Collection 2: `gdce_docs` (general info & policies)

**Available Endpoints:**

```
POST /lookup/hs-code
├─ Purpose: Find HS code from product description
├─ Intent: HS_CODE_LOOKUP
├─ Qdrant Collection: gdce_hs_code
├─ Request: { product_name, origin_country, confidence_threshold }
├─ Response: { hs_code, confidence, description, related_codes }
├─ Fallback: Returns top 3 matches if exact match not found
└─ Time: ~1-3s (includes vector search in Qdrant)

GET /lookup/hs-info
├─ Purpose: Get HS code description & metadata + duty rates
├─ Intent: HS_CODE_LOOKUP, DEFINITION
├─ Qdrant Collection: gdce_hs_code
├─ Query: ?hs_code=0102.29.11
├─ Response: { hs_code, description, unit, classification,
│              cd_rate, st_rate, vat_rate, et_rate,
│              origin_country (optional) }
└─ Time: ~100-300ms

POST /search/general-info
├─ Purpose: Search for general customs information
├─ Intent: DEFINITION, GENERAL
├─ Qdrant Collection: gdce_docs
├─ Request: { query, category: ["definitions", "procedures", "requirements"] }
├─ Response: { results: [...], total_count }
└─ Time: ~500ms-2s

POST /search/policy
├─ Purpose: Search for policy, regulations, and compliance information
├─ Intent: POLICY_QUERY
├─ Qdrant Collection: gdce_docs
├─ Request: { query, filters: { type: "FTA|regulation|procedure", country: "..." } }
├─ Response: { results: [...], total_count, sources: [...] }
└─ Time: ~500ms-2s

GET /health
├─ Purpose: Health check
├─ Response: { status, version, qdrant_connected, collections: [...] }
└─ Time: ~50ms
```

**⚠️ IMPORTANT: This service queries TWO Qdrant collections:**

**Collection 1: gdce_hs_code** (HS Codes & Duty Rates)

- URL: `http://172.25.3.243:6333/dashboard#/collections/gdce_hs_code`
- Used by: `/lookup/hs-code`, `/lookup/hs-info`
- Contains: HS codes, descriptions, classifications, duty rates (CD, ST, VAT, ET)
- Search type: Vector search for fuzzy matching on product names
- Example queries:
  - Find HS code for "chickens"
  - Get duty rate for HS 0102.29.11

**Collection 2: gdce_docs** (General Info & Policies)

- URL: `http://172.25.3.243:6333/dashboard#/collections/gdce_docs`
- Used by: `/search/general-info`, `/search/policy`
- Contains: Definitions, procedures, regulations, FTA info, compliance requirements
- Search type: Vector search + keyword matching
- Example queries:
  - Define "CIF" in customs
  - What are FTA procedures with ASEAN?
  - Export requirements for Cambodia

### 3. Trade Data Service Client (`infrastructure/trade_data_client.py`)

**Purpose:** Handles ONLY trade statistics queries:

- ✓ Trade statistics (TRADE_QUERY intent)
- ✓ Import/export data
- ✓ Trade flows & bilateral trade
- ✓ Trade trends & analysis
- ✗ NOT HS code lookups (use Retrieval Service)
- ✗ NOT policies or regulations (use Retrieval Service)
- ✗ NOT tax calculations (use Calculator Service)

**Connection Details:**

- Host: `TRADE_DATA_HOST` (default: `127.0.0.1`)
- Port: `TRADE_DATA_PORT` (default: `8004`)
- Protocol: HTTP/REST (async)
- Timeout: 15 seconds (configurable)
- Backend: Remote PostgreSQL Database (172.25.3.243:5432)

**PostgreSQL Connection:**

- Host: `PG_HOST` (default: `172.25.3.243`)
- Port: `PG_PORT` (default: `5432`)
- Database: `postgres` (Trade Data DB)
- Schema: `trade_raw` (all tables prefixed with trade_raw)
- User: `postgres`
- Password: `postgres`

**Key Database Tables:**

The Trade Data Service queries from a complex PostgreSQL schema with reference and transaction tables:

```
Main Transaction Tables:
├─ trade_raw.trade_data_202603181513
│  └─ Columns: hs8_code, flow (import/export), partner_country,
│     export_country, value_khr, value_usd, ref_year, ref_month,
│     fta_typ (FTA type), regime, quantity, net_weight
│
├─ trade_raw.imts_public_202603181434
│  └─ Columns: hs8_code, hs4_code, hs2_code, flow, partner_country,
│     export_country, value_khr, value_usd, year, period, quantity

Reference Tables (for lookups):
├─ trade_raw.hs8_codes_202603181443
│  └─ HS codes with tariff rates: tar_t01 through tar_t15 (by origin)
│
├─ trade_raw.countries_202603181504
│  └─ Country codes, names (English & Khmer), country groups
│
├─ trade_raw.fta_type_202603181508
│  └─ FTA agreement types (RCEP, ATIGA, ASEAN, etc.)
│
└─ trade_raw.country_groups_has_countries_202603181507
   └─ Country membership in trade groups & regions
```

**Available Endpoints:**

```
GET /query/trade-statistics
├─ Purpose: Get trade statistics for country/HS code
├─ Intent: TRADE_QUERY
├─ Query: ?hs_code=0102.29.11&country=CN&year=2025
├─ Database Query: SELECT SUM(value_usd) FROM trade_raw.trade_data_202603181513
│  WHERE hs8_code LIKE '0102.29.11%' AND partner_country='CN'
│  AND EXTRACT(YEAR FROM ref_year)=2025
├─ Response: { imports, exports, avg_price, trends, data_source }
└─ Time: ~500ms-2s

GET /query/bilateral-trade
├─ Purpose: Get bilateral trade data between countries
├─ Intent: TRADE_QUERY
├─ Query: ?origin=CN&destination=KH&hs_code=0102.29.11&year=2025
├─ Database Query: SELECT flow, SUM(value_usd) FROM trade_raw.trade_data_202603181513
│  WHERE hs8_code LIKE '0102.29.11%' AND export_country=?
│  AND partner_country=? GROUP BY flow, ref_year
├─ Response: { trade_volume, direction, trend, monthly_breakdown: [...] }
└─ Time: ~500ms-2s

GET /query/origin-info
├─ Purpose: Get origin country info (name, FTA agreements, region)
├─ Intent: TRADE_QUERY (supplementary)
├─ Query: ?country_code=CN
├─ Database Query: SELECT name, name_kh FROM trade_raw.countries_202603181504
│  WHERE code='CN' UNION SELECT fta_typ FROM trade_raw.fta_type_202603181508
│  WHERE country_code='CN'
├─ Response: { country_name, country_name_kh, region, fta_agreements,
│             trading_profile }
└─ Time: ~100-300ms

GET /health
├─ Purpose: Health check + DB connectivity
├─ Response: { status, version, database_connected, tables_available: [...] }
└─ Time: ~50ms
```

**⚠️ IMPORTANT DATABASE COMPLEXITY:**

The Trade Data Service queries a **complex normalized schema** with:

- **Date-versioned tables**: `...202603181513` format (from different import batches)
- **Multiple HS code levels**: hs2, hs4, hs6, hs8 for hierarchical analysis
- **Bilateral relationships**: export_country + partner_country + flow (import/export)
- **FTA tracking**: fta_typ field + separate FTA reference tables
- **Multi-currency**: value_khr and value_usd in same records
- **Time series data**: ref_year + ref_month for trending analysis

Queries may involve:

- JOINs across trade_data, countries, FTA, and HS code reference tables
- GROUP BY operations on year/month/flow/country for aggregation
- String pattern matching on HS codes (0102.29.11%)
- UNION operations combining multiple reference tables

**⚠️ Service Comparison - Know Your Backend:**

| Aspect                 | Retrieval Service       | Trade Data Service           |
| ---------------------- | ----------------------- | ---------------------------- |
| **Backend**            | Qdrant (Vector DB)      | PostgreSQL (Relational DB)   |
| **Data Source**        | Qdrant collections      | PostgreSQL trade_raw schema  |
| **Query Type**         | Vector search + keyword | SQL joins & aggregations     |
| **Latency**            | 100ms-3s                | 500ms-2s                     |
| **Purpose**            | HS codes + policies     | Trade statistics & flows     |
| **Complexity**         | Simple lookup           | Complex multi-table queries  |
| **Collections/Tables** | 2 collections           | 10+ tables                   |
| **Use Cases**          | Definitions, HS lookup  | Trade trends, bilateral data |

---

### 4. PostgreSQL Exchange Rates (`infrastructure/postgres_adapter.py`)

**Connection Details:**

- Host: `PG_HOST` (default: `172.25.3.243`)
- Port: `PG_PORT` (default: `5432`)
- Database: `PG_DATABASE` (default: `gdce_hs_code`)
- User: `postgres` (default: `postgres`)
- Password: `PG_PASSWORD` (default: ``postgres`)

**Table: `exchange_rates`**

```sql
SELECT local_rate
FROM exchange_rates
WHERE currency = 'USD'
AND effective_date <= CURRENT_DATE
ORDER BY effective_date DESC
LIMIT 1;

-- Returns: 4022.0
```

**Query from Orchestrator:**

```python
# infrastructure/postgres_adapter.py

async def get_exchange_rate(currency: str) -> float:
    """Get exchange rate from PostgreSQL."""

    async with asyncpg.create_pool(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DATABASE,
        user=PG_USER,
        password=PG_PASSWORD
    ) as pool:
        async with pool.acquire() as conn:
            rate = await conn.fetchval(
                """
                SELECT local_rate FROM exchange_rates
                WHERE currency = $1
                AND effective_date <= CURRENT_DATE
                ORDER BY effective_date DESC LIMIT 1
                """,
                currency
            )
            return rate or 4022.0  # Fallback
```

---

## 🧭 Intent Detection System (Two-Layer Architecture)

### Overview

The Orchestrator uses a **two-layer intent detection system** to accurately classify user queries:

```
┌─────────────────────────────────────────────────────────┐
│ QueryRequest {question, session_id}                     │
└──────────────────┬──────────────────────────────────────┘
                   │
        ┌──────────▼────────── ┐
        │ LAYER 1: LLM (MiniLM)│ (Primary - High Accuracy)
        │ Intent Classifier    │
        │                      │
        │ Confidence ≥ 0.65?   │
        └─┬─────────┬───────── ┘
          │ YES     │ NO
          │         │
        ✓ ACCEPT  ▼ TRIGGER LAYER 2
          │     ┌──────────────────────────┐
          │     │ LAYER 2: Keyword/Rule    │ (Fallback - Always Available)
          │     │ Based Detection          │
          │     │                          │
          │     │ 1. Keyword matching      │
          │     │ 2. Pattern matching      │
          │     │ 3. Compound rules        │
          │     │ 4. Fallback to "general" │
          │     └─────────┬────────────────┘
          │               │
          └───────────────┴────────────┤
                                       ▼
                        ┌──────────────────────────┐
                        │ Final Intent + Confidence│
                        │ {intent, confidence}     │
                        └──────────────────────────┘
```

### Intent Categories with Routing

| Intent             | Layer 1 LLM | Layer 2 Keyword/Rule | Primary Service    | Example Query                              |
| ------------------ | ----------- | -------------------- | ------------------ | ------------------------------------------ |
| **hs_code_lookup** | 0.80-0.95   | 0.85                 | Retrieval (8003)   | "What is the HS code for chickens?"        |
| **calculation**    | 0.65-0.98   | 0.85                 | Calculator (8002)  | "Calculate tax for HS 0102.29.11 CIF $800" |
| **definition**     | 0.80-0.95   | 0.85                 | Retrieval (8003)   | "Define CIF in customs"                    |
| **policy_query**   | 0.65-0.94   | 0.85                 | Retrieval (8003)   | "What are FTA requirements with ASEAN?"    |
| **trade_query**    | 0.70-0.92   | 0.80                 | Trade Data (8004)  | "Trade data: export textiles to Thailand"  |
| **general**        | <0.65       | 0.50                 | Retrieval (8003)\* | "Tell me about Cambodia customs"           |

### Layer 1: LLM Intent Classifier (Primary)

**How it works:**

```python
async def detect_intent_with_llm(question: str) -> IntentResult:
    """
    Use LLM to classify intent with confidence score.

    Advantages:
    - Handles complex, nuanced queries well
    - Contextually aware
    - Detects multi-intent queries
    - Handles synonyms and paraphrasing

    Disadvantages:
    - Slower (500-2000ms)
    - May produce low confidence scores on edge cases
    - Requires LLM availability
    """

    prompt = f"""
    You are a customs and trade classification expert.
    Classify this SINGLE PRIMARY INTENT for the question.

    Possible intents:
    - calculation: User wants to calculate import taxes/duties
    - definition: User wants HS code definitions or terminology
    - trade_query: User wants trade data, statistics, or procedures
    - policy_inquiry: User wants regulations, rules, or requirements
    - general: For non-customs questions or unclear intent

    Question: "{question}"

    Respond ONLY with: intent:confidence
    Example: "calculation:0.95"
    """

    response = await llm_client.generate(
        prompt=prompt,
        temperature=0.3,  # Lower = more consistent
        max_tokens=20
    )

    # Parse response
    intent_str, conf_str = response.strip().split(":")
    return IntentResult(
        intent=Intent[intent_str.upper()],
        confidence=float(conf_str)
    )
```

**Confidence Thresholds:**

```
Confidence  | Decision
────────────┼──────────────────────────
   ≥ 0.85   │ Very High - Accept immediately
  0.65-0.85 │ High - Accept, use as-is
  0.65-0.65 │ Medium - Marginal, trigger Layer 2
   < 0.65   │ Low - Always use Layer 2
```

### Layer 2: Keyword/Rule-Based Detection (Fallback)

**When it triggers:**

- Layer 1 confidence < 0.65 (threshold)
- Layer 1 unavailable or fails
- Always available as safety net

_Note: Refer to Section 2a-2d under the initial Layer 2 detection explanation for detailed keyword, pattern, and compound rule definitions._

### Detection Examples

**Example 1: Clear Calculation (Layer 1 Succeeds)**

```
Query: "Calculate tax for HS 0102.29.11 CIF $800 from China"

Layer 1 (LLM):
├─ Analysis: Clear tax calculation with HS code + currency
├─ Intent: "calculation"
├─ Confidence: 0.96
└─ ✓ Result: ACCEPTED (0.96 ≥ 0.65) → Use this intent

Reasoning: LLM - (MiniLM) recognizes keywords (calculate, tax, HS, $, CIF) and context
```

**Example 2: Ambiguous Query (Layer 1 Low, Layer 2 Succeeds)**

```
Query: "Tell me about duty rates for items from China"

Layer 1 (LLM):
├─ Analysis: Could be definition, rate lookup, or trade query
├─ Intent: "rate_lookup"
├─ Confidence: 0.62
└─ ⚠ Result: REJECTED (0.62 < 0.65) → Trigger Layer 2

Layer 2 (Keyword/Rule):
├─ Keyword check: "duty rates" matches RATE_LOOKUP keywords
├─ Intent: "rate_lookup"
├─ Confidence: 0.80
└─ ✓ Result: ACCEPTED

Final: rate_lookup (via Layer 2 fallback)
```

**Example 3: Unclear Query (Fallback to "general")**

```
Query: "Tell me about Cambodia"

Layer 1 (LLM):
├─ Confidence: 0.55 (not customs-specific)
└─ REJECTED → Trigger Layer 2

Layer 2 (Keyword/Rule):
├─ No keyword matches
├─ No pattern matches
├─ No compound rules match
└─ NO MATCH → Fallback

Final: general (default, confidence: 0.50)
Action: Route to multi-service or ask for clarification
```

---

## ⚙️ Configuration

### Configuration Files Location: `configs/orchestrator/`

```
configs/
└── orchestrator/
    ├── intent_detection_rules.json      ← Keywords and regex patterns
    ├── service_routing.json             ← Workflow sequences
    ├── validation_rules.json            ← Input/output validation
    └── response_formatting.json         ← Output formatting rules
```

### Configuration Files Reference

**1. `intent_detection_rules.json`** - Two-Layer Intent Detection Config

```json
{
  "detection_method": "two_layer",
  "description": "Primary: LLM | Fallback: Keyword/Rule-based",

  "layer_1_llm": {
    "enabled": true,
    "comment": "Set to false if LLM unavailable (will use Layer 2 for all)",
    "confidence_threshold": 0.65,
    "confidence_ranges": {
      "very_high": { "min": 0.85, "max": 1.0, "action": "accept_immediately" },
      "high": { "min": 0.65, "max": 0.85, "action": "accept_use_as_is" },
      "medium": { "min": 0.65, "max": 0.65, "action": "trigger_layer_2" },
      "low": { "min": 0.0, "max": 0.65, "action": "trigger_layer_2" }
    },
    "llm_prompt_template": "Classify this customs question by intent. Return format: intent:confidence",
    "timeout_ms": 2000,
    "fallback_to_layer_2_on_timeout": true
  },

  "layer_2_keyword_rules": {
    "enabled": true,
    "comment": "Always available, used when Layer 1 < 0.65 or unavailable",
    "confidence_fixed": 0.85,
    "priority": "highest_to_lowest",

    "keywords": {
      "calculation": [
        "calculate",
        "tax",
        "duty",
        "HS code",
        "$",
        "CIF",
        "FOB",
        "customs value",
        "import duty",
        "how much",
        "total tax",
        "charges",
        "payment",
        "cost"
      ],
      "definition": [
        "what is",
        "define",
        "meaning",
        "HS code",
        "classified as",
        "what does",
        "explain what",
        "describes",
        "definition of",
        "tell me about"
      ],
      "trade_query": [
        "export",
        "import",
        "procedure",
        "document",
        "requirement",
        "how do I",
        "steps for",
        "process of",
        "guide to"
      ],
      "policy_inquiry": [
        "regulation",
        "rule",
        "requirement",
        "FTA",
        "agreement",
        "policy",
        "law",
        "restricted",
        "prohibited",
        "allowed"
      ]
    }
  },

  "layer_2_pattern_rules": {
    "priority": "second",
    "confidence_fixed": 0.8,

    "patterns": {
      "calculation": [
        "\\b\\d{4}\\.\\d{2}\\.\\d{2}\\b.*?(\\$|USD|KHR|EUR|CNY).*?\\d+",
        "\\b(CIF|FOB|FCA|CPT|DDP|DAP)\\b.*?\\$?[\\d,]+",
        "(calculate|compute).*?HS.*?\\d{4}\\.\\d{2}\\.\\d{2}"
      ],
      "rate_lookup": [
        "HS\\s+\\d{4}\\.\\d{2}\\.\\d{2}.*?\\brate\\b",
        "\\bduty.*?rate.*?%|\\brate.*?%.*?\\bduty\\b"
      ]
    }
  },

  "layer_2_compound_rules": {
    "priority": "third",
    "confidence_fixed": 0.65,
    "description": "Complex logic combinations",

    "rules": [
      {
        "intent": "comparison",
        "logic": "keyword_present(vs|compare|versus) AND hs_codes_count >= 2"
      },
      {
        "intent": "trade_query",
        "logic": "keyword_present(import|export) AND keyword_present(procedure|document|how)"
      },
      {
        "intent": "policy_inquiry",
        "logic": "keyword_present(FTA|agreement) AND keyword_present(require|eligible|qualify)"
      }
    ]
  },

  "layer_2_fallback": {
    "default_intent": "general",
    "confidence": 0.5,
    "action": "route_to_multi_service_or_ask_clarification"
  }
}
```

**2. `service_routing.json`**

```json
{
  "workflows": [
    {
      "intent": "calculation",
      "workflow_id": "calculation_normal",
      "description": "Calculate import duties and taxes",
      "sequence": [
        {
          "step": 1,
          "service": "validator",
          "action": "validate_calculation_inputs",
          "required": true
        },
        {
          "step": 2,
          "service": "retrieval",
          "action": "lookup_hs_code_if_needed",
          "required": false,
          "condition": "hs_code_missing"
        },
        {
          "step": 3,
          "service": "calculator",
          "action": "calculate_import_taxes",
          "required": true,
          "timeout_ms": 10000
        },
        {
          "step": 4,
          "service": "formatter",
          "action": "format_response",
          "required": false
        }
      ],
      "fallback": "retrieval",
      "timeout_ms": 30000
    },
    {
      "intent": "definition",
      "workflow_id": "definition_lookup",
      "sequence": [
        {
          "step": 1,
          "service": "retrieval",
          "action": "lookup_hs_info",
          "required": true
        }
      ],
      "timeout_ms": 15000
    }
  ]
}
```

**3. `validation_rules.json`**

```json
{
  "input_validation": {
    "min_length": 10,
    "max_length": 5000,
    "injection_detection": true,
    "scope_checking": true,

    "injection_patterns": [
      "DROP TABLE",
      "DELETE FROM",
      "INSERT INTO",
      "<script>",
      "javascript:",
      "union select"
    ],

    "scope_keywords": [
      "customs",
      "duty",
      "tax",
      "import",
      "export",
      "HS code",
      "tariff",
      "trade",
      "commerce"
    ],

    "allowed_characters": "[a-zA-Z0-9\\s$€¥₹₽.,:-]+"
  },

  "output_validation": {
    "check_safety": true,
    "check_accuracy": true,
    "check_consistency": true,

    "sanity_checks": {
      "total_equals_sum": true,
      "tax_rates_0_to_100": true,
      "exchange_rate_reasonable": { "min": 0.1, "max": 10000 },
      "values_positive": true
    }
  }
}
```

**4. `response_formatting.json`**

```json
{
  "llm_formatting": {
    "enabled": false,
    "comment": "Set enabled=true if LLM formatter available",
    "provider": "local_llm",
    "timeout_ms": 5000,
    "fallback_to_base_answer": true
  },

  "response_structure": {
    "include_citations": true,
    "include_assumptions": true,
    "include_metadata": true,
    "include_conversion_details": true
  },

  "answer_format": {
    "calculation": "structured_breakdown",
    "definition": "narrative",
    "policy": "bullet_points"
  },

  "citation_format": {
    "show_source_url": true,
    "show_access_time": true,
    "show_confidence": true
  }
}
```

### Environment Variables (from `.env`)

```bash
# Orchestrator Service Port
ORCHESTRATOR_HOST=127.0.0.1
ORCHESTRATOR_PORT=8001

# Downstream Service Connections
CALCULATOR_HOST=127.0.0.1
CALCULATOR_PORT=8002
RETRIEVAL_HOST=127.0.0.1
RETRIEVAL_PORT=8003
TRADE_DATA_HOST=127.0.0.1
TRADE_DATA_PORT=8004

# PostgreSQL (Exchange Rates)
PG_HOST=172.25.3.243
PG_PORT=5432
PG_DATABASE=gdce_hs_code
PG_USER=postgres
PG_PASSWORD=postgres

# ===== Layer 1: LLM-Based Intent Detection (Primary) =====
LLM_INTENT_DETECTION_ENABLED=true
LLM_API_URL=http://localhost:8005
LLM_API_KEY=your_key_here

# Layer 1 Confidence Thresholds
# Queries above high_confidence_threshold (0.85) are accepted immediately
# Queries between medium_confidence_threshold (0.65) and threshold (0.65) trigger Layer 2
# Queries below low_confidence_threshold (0.65) always trigger Layer 2
LLM_CONFIDENCE_THRESHOLD=0.65
LLM_CONFIDENCE_HIGH=0.85
LLM_CONFIDENCE_MEDIUM=0.65
LLM_TIMEOUT_MS=2000

# Layer 1 Fallback Behavior
LLM_FALLBACK_TO_LAYER_2_ON_TIMEOUT=true
LLM_FALLBACK_TO_LAYER_2_ON_LOW_CONFIDENCE=true

# ===== Layer 2: Keyword/Rule-Based Intent Detection (Fallback) =====
# Layer 2 is always active and serves as fallback to Layer 1
KEYWORD_DETECTION_ENABLED=true

# Layer 2 Confidence Thresholds (for different matching methods)
KEYWORD_CONFIDENCE_EXACT_MATCH=0.85      # Exact keyword match in Query
KEYWORD_CONFIDENCE_PATTERN_MATCH=0.80    # Regex pattern match (e.g., "HS\s+\d{6}")
KEYWORD_CONFIDENCE_COMPOUND_RULE=0.65    # Compound rule (e.g., "+ for calculation")
KEYWORD_CONFIDENCE_FALLBACK=0.50         # Fallback intent (general queries)

# Layer 2 Timeout (used for any synchronous keyword matching)
KEYWORD_MATCH_TIMEOUT_MS=500

# ===== Response Formatting =====
LLM_RESPONSE_FORMATTING_ENABLED=true
LLM_RESPONSE_FORMAT=structured_json
LLM_FORMAT_TIMEOUT_MS=3000

# ===== Validation & Security =====
INPUT_VALIDATION_ENABLED=true
OUTPUT_VALIDATION_ENABLED=true
SECURITY_CHECK_ENABLED=true

# ===== Logging & Debugging =====
LOG_LEVEL=INFO
LOG_FORMAT=json
DEBUG_MODE=false
INTENT_DETECTION_DEBUG=false      # Log Layer 1 vs Layer 2 decisions

# ===== Service Timeouts =====
REQUEST_TIMEOUT_MS=30000
CALCULATOR_TIMEOUT_MS=10000
RETRIEVAL_TIMEOUT_MS=15000
TRADE_DATA_TIMEOUT_MS=15000

# ===== Caching (Optional) =====
CACHE_ENABLED=false
CACHE_TTL_SECONDS=3600
INTENT_CACHE_ENABLED=false       # Cache intent detection results
INTENT_CACHE_TTL_SECONDS=300     # 5 minutes
```

---

## 📊 API Endpoints Reference

### Public Endpoints

| Endpoint         | Method | Purpose                           | Example                            |
| ---------------- | ------ | --------------------------------- | ---------------------------------- |
| `/query`         | POST   | Process user query                | `{"question": "Calculate tax..."}` |
| `/chat`          | POST   | Chat interface (alias for /query) | Same as /query                     |
| `/health`        | GET    | Service health check              | Returns status + service statuses  |
| `/status`        | GET    | Detailed status info              | Returns config + component states  |
| `/info`          | GET    | Service information               | Returns capabilities + endpoints   |
| `/query/explain` | POST   | Debug: explain routing            | Shows intent + workflow            |

### Internal Endpoints (Not exposed publicly)

| Endpoint                     | Service    | Purpose                   |
| ---------------------------- | ---------- | ------------------------- |
| `/v1/calculate_import_taxes` | Calculator | Perform calculation       |
| `/lookup/hs-code`            | Retrieval  | Find HS code from product |
| `/query/trade-statistics`    | Trade Data | Get trade statistics      |

---

## 🤖 LLM Models & Technology Stack

### Deployed Models

| Model                 | Purpose                                          | Use Case                                                               |
| --------------------- | ------------------------------------------------ | ---------------------------------------------------------------------- |
| **all-MiniLM-L12-v2** | Intent detection & currency identification       | Fast intent classification, currency type detection, semantic matching |
| **Llama 3.2 3B**      | Explanation, interpretation, response formatting | User-friendly answer generation, complex reasoning, intent explanation |

### Model Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR SERVICE (Port 8001)                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ User Query                                                  │
│    ↓                                                        │
│ Input Validation → Security Check → Scope Check             │
│    ↓                                                        │
│ Intent Detection (Primary)                                  │
│    └─ MiniLM - Fast intent classification                   │
│       ├─ Analyze user intent from question                  │
│       ├─ Confidence scoring (0.0-1.0)                       │
│       └─ If confidence ≥ 0.65 → Use intent                  │
│                                                             │
│ Currency Identification (Primary)                           │
│    └─ MiniLM - Identify currency type                       │
│       ├─ Detect currency from question                      │
│       ├─ Query PostgreSQL for exchange rate                 │
│       └─ If unable to detect → Default to KHR              │
│    ↓                                                        │
│ Route to appropriate service (Calculator, Retrieval, etc)   │
│    ↓                                                        │
│ Aggregate responses                                         │
│    ↓                                                        │
│ Response Interpretation & Formatting with Llama 3.2 3B      │
│    ├─ Generate user-friendly explanation                    │
│    ├─ Interpret results for clarity                         │
│    └─ Add citations and metadata                            │
│    ↓                                                        │
│ Return formatted response to user                           │
└─────────────────────────────────────────────────────────────┘
```

### Model Specifications

**MiniLM (Microsoft) - Primary Decision Maker**

- **Model**: `all-MiniLM-L12-v2` (SentenceTransformers)
- Purpose: Fast intent classification and currency identification
- Dimensions: 384 embedding vector size
- Latency: < 100ms for inference
- Memory: ~400MB (on-disk), ~300MB loaded
- Use Cases:
  - **Intent classification** (determining user's goal: calculation, definition, etc.)
  - **Currency identification** (detecting currency type: USD, KHR, THB, etc.)
  - Query embedding generation
  - Semantic similarity matching for pattern recognition

**Llama 3.2 3B (Meta) - Explanation & Interpretation**

- Purpose: Explanation, interpretation, and user-friendly response generation
- Parameters: 3 Billion
- Latency: 500-2000ms for inference
- Use Cases:
  - **Response explanation** (converting raw results to natural language)
  - **Result interpretation** (explaining what the numbers mean)
  - Response formatting and citation generation
  - Complex reasoning for ambiguous queries
  - Chat-style answer enhancement

### Configuration

The models are deployed via SentenceTransformers (for MiniLM) and Ollama (for Llama 3.2 3B):

```bash
# LLM Service Configuration
LLM_API_URL=http://localhost:8005          # Ollama API endpoint
LLM_INTENT_DETECTION_ENABLED=true          # Use intent detection

# Intent Detection: all-MiniLM-L12-v2 Settings
INTENT_DETECTION_MODEL=all-MiniLM-L12-v2   # SentenceTransformers MiniLM model
INTENT_CONFIDENCE_THRESHOLD=0.75           # Accept if confidence > this
INTENT_DETECTION_TIMEOUT_MS=500            # Max response time

# Currency Identification: all-MiniLM-L12-v2 Settings
CURRENCY_DETECTION_MODEL=all-MiniLM-L12-v2 # SentenceTransformers MiniLM model
CURRENCY_CONFIDENCE_THRESHOLD=0.70         # Accept if confidence > this
POSTGRESQL_EXCHANGE_RATE_ENABLED=true      # Query DB for rates

# Response Interpretation: Llama 3.2 3B Settings
RESPONSE_FORMATTING_MODEL=llama32          # Response explanation & formatting
RESPONSE_FORMATTING_ENABLED=true           # Enable interpretation
RESPONSE_FORMATTING_TIMEOUT_MS=2000        # Max response time
```

### Performance Characteristics

| Metric                 | MiniLM   | Llama 3.2 3B |
| ---------------------- | -------- | ------------ |
| **Inference Latency**  | < 100ms  | 500-2000ms   |
| **Memory Requirement** | ~300MB   | ~6-8GB       |
| **Accuracy**           | 85-90%   | 95%+         |
| **GPU Recommended**    | No       | Yes          |
| **Cost**               | Very low | Low-Medium   |

### Model Usage Flow in Orchestrator (example)

1. **User asks question** → "Calculate tax for HS 0102.29.11 CIF $800 from China"
2. **Security/Scope validation** → Passed ✓
3. **Intent Detection (MiniLM - Fast)**
   - MiniLM classifies user intent from question
   - Returns intent with confidence score
   - If confidence ≥ 0.65 → Use detected intent (e.g., "calculation")
   - If confidence < 0.65 → Default to "general" intent
4. **Currency Identification (MiniLM - Fast)**
   - MiniLM identifies currency type (USD, KHR, THB, etc.)
   - Query PostgreSQL exchange_rates table
   - If unable to determine → Default to KHR
5. **Parameter Extraction & Validation**
   - Extract HS code, value, origin, date
   - Validate all parameters
6. **Route to appropriate service** → Calculator Service (Port 8002)
7. **Call downstream service** → Get calculation results
8. **Response Interpretation (Llama 3.2 3B - Explanation)**
   - Explain what the tax numbers mean
   - Generate user-friendly formatted response
   - Add citations and metadata
   - Convert raw results to natural language
9. **Return formatted answer** → User

---

## 💬 Usage Examples

### Example 1A: Calculate Tax Query (Chat)

**User Question:**

```
"Calculate tax for HS 0102.29.11 CIF $800 from China"
```

**HTTP Request:**

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Calculate tax for HS 0102.29.11 CIF $800 from China",
    "session_id": "session_abc123"
  }'
```

**Processing Steps (Orchestrator):**

1. Input validation → ✓ Safe
2. Intent detection → "calculation" (0.95 confidence)
3. Parameter extraction → hs_code="0102.29.11", value=800, currency="USD", origin="CN"
4. Workflow selection → Call Calculator Service
5. Call Calculator → `/v1/calculate_import_taxes`
6. Output validation → ✓ Valid response
7. Response formatting → Add citations and metadata
8. Build JSON response

**HTTP Response (200 OK):**

```json
{
  "request_id": "req_20260401_1142_xyz789",
  "question": "Calculate tax for HS 0102.29.11 CIF $800 from China",
  "answer": "For HS code 0102.29.11 (Live cattle) importing $800 USD from China:\n\n• Customs Duty: 0 KHR (0%)\n• Special Tax: 0 KHR (0%)\n• VAT: 321,760 KHR (10%)\n• Excise Tax: 0 KHR (0%)\n\nTOTAL TAX: 321,800 KHR (rounded from 321,760)\n\nExchange Rate: 1 USD = 4,022 KHR\nSource: Qdrant (172.25.3.243:6333), PostgreSQL",
  "intent": "calculation",
  "status": "completed",
  "latency_ms": 847.5,
  "citations": [
    {
      "source_name": "Qdrant HS Code Database",
      "reference": "HS 0102.29.11 - Live cattle",
      "confidence": "high"
    },
    {
      "source_name": "PostgreSQL Exchange Rates",
      "reference": "USD to KHR: 4,022",
      "confidence": "high"
    }
  ],
  "metadata": {
    "intent_confidence": 0.95,
    "services_called": ["calculator"],
    "workflow_duration_ms": 847.5
  }
}
```

---

### Example 1B: Definition Lookup Query (Chat)

**User Question:**

```
"What is HS code 0702.00.00?"
```

**Processing Steps:**

1. Intent detection → "definition" (0.98 confidence)
2. Workflow selection → Call Retrieval Service
3. Call Retrieval → `/lookup/hs-info?hs_code=0702.00.00`
4. Retrieve HS description, unit, classification
5. Format response

**Response Example:**

```json
{
  "request_id": "req_20260401_1143_abc456",
  "question": "What is HS code 0702.00.00?",
  "answer": "HS Code 0702.00.00: Tomatoes\n\nUnit: kg (kilograms)\nClassification: Edible vegetables\nDescription: Tomatoes, fresh or chilled, whether or not peeled or cut.\n\nDuty Rates (Cambodia):\n• Customs Duty: 20%\n• Special Tax: 0%\n• VAT: 10%\n• Excise Tax: 0%",
  "intent": "definition",
  "status": "completed",
  "latency_ms": 245,
  "citations": [
    {
      "source_name": "Qdrant HS Code Database",
      "reference": "HS 0702.00.00",
      "confidence": "high"
    }
  ]
}
```

---

### Example 2: Product Name → Tax Calculation

**User Question:**

```
"Calculate tax for oxen, CIF $500 from Thailand"
```

**Processing Steps:**

1. Intent detection → "calculation" (0.92 confidence)
2. Parameter extraction:
   - product = "oxen"
   - value = 500
   - currency = USD
   - origin = "TH"
   - hs_code = NOT FOUND ❌
3. Fallback: Call Retrieval Service to find HS code
   - Query: "oxen from Thailand"
   - Returns: HS 0102.29.11 ✓

4. Now call Calculator with hs_code="0102.29.11"
5. Get calculation result
6. Return response with note: "HS code auto-detected: 0102.29.11 (Live cattle)"

**Response:**

```json
{
  "request_id": "req_20260401_1145_def789",
  "question": "Calculate tax for oxen, CIF $500 from Thailand",
  "answer": "For oxen (HS 0102.29.11) importing $500 USD from Thailand:\n\n• Customs Duty: 0 KHR (0%)\n• Special Tax: 0 KHR (0%)\n• VAT: 160,880 KHR (10%)\n• Excise Tax: 0 KHR (0%)\n\nTOTAL TAX: 160,900 KHR\n\nNote: HS code auto-detected from product name 'oxen'",
  "intent": "calculation",
  "status": "completed",
  "latency_ms": 1240,
  "metadata": {
    "services_called": ["retrieval", "calculator"],
    "hs_code_auto_detected": true,
    "auto_detected_hs": "0102.29.11"
  }
}
```

---

## 🔍 Debugging & Troubleshooting

### Issue 1: Intent Detection Failing

```bash
# Check intent detection rules
curl -X POST http://localhost:8001/query/explain \
  -H "Content-Type: application/json" \
  -d '{"question": "Your test question here"}'

# Response shows:
{
  "question": "...",
  "intent": "unclassified",  # ← Problem
  "intent_confidence": 0.42,
  "intended_workflow": "fallback_multiple_services"
}

# Solution:
# 1. Enable LLM-based intent detection if available
#    → LLM_INTENT_DETECTION_ENABLED=true in .env
# 2. Check keyword rules in configs/orchestrator/intent_detection_rules.json
# 3. Review question for unusual phrasing
```

### Issue 2: Calculator Service Not Responding

```bash
# Check Calculator health
curl http://localhost:8002/v1/health

# Expected response:
{ "status": "healthy", "qdrant_connected": true }

# If unhealthy:
# 1. Check Calculator service is running
#    → docker ps | grep calculator
# 2. Check Qdrant connection (Calculator depends on it)
#    → curl http://172.25.3.243:6333/health
# 3. View Calculator logs
#    → docker logs calculator_service

# Orchestrator will timeout and fallback after 10 seconds
```

### Issue 3: Exchange Rate Lookup Failing

```bash
# Check PostgreSQL connection
psql -h 172.25.3.243 -U postgres -d gdce_hs_code

# Check exchange_rates table
SELECT * FROM exchange_rates WHERE currency = 'USD' LIMIT 1;

# If no data or connection fails:
# 1. Check .env PostgreSQL credentials
# 2. Verify network connectivity to 172.25.3.243:5432
# 3. Fallback rate will be used from config

# Check fallback in .env:
grep USD_TO_KHR_RATE_FALLBACK .env
```

### Issue 4: Response Not Formatted (LLM Disabled)

```bash
# Check if LLM formatting is enabled
echo $LLM_RESPONSE_FORMATTING_ENABLED

# If false, response will be unformatted:
"Total: 321800 KHR. CD=0, ST=0, VAT=321760, ET=0"

# Enable LLM formatting:
# 1. Set LLM_RESPONSE_FORMATTING_ENABLED=true in .env
# 2. Ensure LLM service is available at LLM_API_URL
# 3. Check LLM timeout: LLM_TIMEOUT_MS=5000

# If LLM unavailable, response falls back to unformatted answer
```

### Issue 5: Security Validation Rejecting Query

```bash
# Example rejection:
{
  "status": "refused",
  "answer": "I cannot process that request...",
  "metadata": {"security": "Injection detected: DROP TABLE"}
}

# Debug:
# 1. Review query for injection patterns
# 2. Check validation_rules.json injection_patterns list
# 3. If false positive, update patterns
# 4. Disable validation (not recommended for production):
#    → INPUT_VALIDATION_ENABLED=false
```

---

## 📈 Next Steps (Phase 2/3)

- [ ] Implement response caching (Redis)
- [ ] Add conversation history support (multi-turn)
- [ ] Implement request queuing for high load
- [ ] Add authentication/authorization
- [ ] Implement rate limiting
- [ ] Add webhook support for async responses
- [ ] Implement batch query processing
- [ ] Add analytics & metrics collection
- [ ] Support for multiple language queries
- [ ] Implement feedback loop for response quality

---

## 📞 Quick Reference

| Component    | Host         | Port | Purpose                         |
| ------------ | ------------ | ---- | ------------------------------- |
| Orchestrator | 127.0.0.1    | 8001 | Query coordinator (entry point) |
| Calculator   | 127.0.0.1    | 8002 | Tax calculations                |
| Retrieval    | 127.0.0.1    | 8003 | HS code lookup & definitions    |
| Trade Data   | 127.0.0.1    | 8004 | Trade statistics                |
| PostgreSQL   | 172.25.3.243 | 5432 | Exchange rates database         |
| Qdrant       | 172.25.3.243 | 6333 | HS code embeddings & rates      |

| Endpoint           | Method | Time       |
| ------------------ | ------ | ---------- |
| `/query` / `/chat` | POST   | 500ms - 2s |
| `/health`          | GET    | 50-100ms   |
| `/status`          | GET    | 25-50ms    |
| `/info`            | GET    | 25-50ms    |
| `/query/explain`   | POST   | 100-300ms  |

| Config File                   | Purpose                     |
| ----------------------------- | --------------------------- |
| `intent_detection_rules.json` | Intent classification logic |
| `service_routing.json`        | Workflow sequences          |
| `validation_rules.json`       | Input/output validation     |
| `response_formatting.json`    | Output formatting           |
