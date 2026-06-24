# Fix Two-Turn Intent Rewriting & Ask-Back Orchestration

## Background

The orchestrator routes raw user queries to intent services (trade, hs_code, general, calculation) via `ServiceCoordinator.process_query()` in [`coordinator.py`](file:///e:/GDCE-Intern/Repo/services_version2/orchestrator/core/coordinator.py). A first-layer pipeline in [`pipeline.py`](file:///e:/GDCE-Intern/Repo/services_version2/orchestrator/llm_first_layer/pipeline.py) handles intent detection, ambiguity checking, and optional query rewriting.

---

## Audit Findings

### Step 1 – Places Where hs_code/trade/calculation Queries Are Unnecessarily Rewritten

| Location | Lines | Problem |
|---|---|---|
| `coordinator.py` – Step 11 | 499 | Rewrite is skipped for `TRADE_QUERY` and `HS_CODE_LOOKUP` — **this is already correct** |
| `coordinator.py` – Step 11 | 499 | `CALCULATION` is **not skipped** from rewriting — `raw_detected_intent != WorkflowIntent.TRADE_QUERY and raw_detected_intent != WorkflowIntent.HS_CODE_LOOKUP` leaves calculation through the rewriter |
| `pipeline.py` – Step 5 | 232 | `skip_rewrite_for_intents` config defaults only to `["hs_code_lookup", "trade_query"]` — **calculation is not skipped** |
| `config.py` | 94-95 | `skip_rewrite_for_intents` default list excludes `calculation` |

**Flag for removal / fix:** The coordinator's rewrite guard at line 499 must also exclude `WorkflowIntent.CALCULATION`.

### Step 2 – Conversation State Gaps

**Existing fields in `SessionContext`:**
- ✅ `pending_clarification` (≈ `awaiting_clarification`)
- ✅ `clarification_intents` (≈ candidate intents)
- ✅ `pending_rewritten_query` (stores the ambiguous fragment)
- ✅ `ask_back_count`
- ⚠️ **Missing `last_intent`** — `update_session_context` sets `last_intent` as a dynamic key, but `SessionContext` dataclass has no typed field for it
- ⚠️ **Missing `last_entity`** — no field to hold the subject ("car", "boat") extracted from turn 1 or turn 2
- ⚠️ **Missing `last_raw_query`** — no field for the unmodified raw query from the previous turn
- ⚠️ **`_merge_pending_with_clarification`** — extracts entity only from the fragment (`pending_query`), not from turn-1 session state; if turn 2 is purely topicless ("and for boat?"), the boat entity is correctly in `pending_query`, but for more complex cases the turn-1 entity fallback is missing
- ⚠️ **Turn-2 ambiguity check fires on ALL turn-2 queries** (line 461: `_turn_number >= 2 and not _already_resolved`) regardless of whether the query already states a self-sufficient intent. This triggers unnecessary ask-back even when intent confidence is high.

### Step 3 – Required Behavior Gaps

| Requirement | Current State |
|---|---|
| Turn-1: hs_code/trade/calculation take raw query (no rewrite) | **Partially done.** hs_code and trade are skipped; calculation is not |
| Turn-1: Only `general` goes through rewrite | **Partially correct.** Rewrite is allowed for both `general` and `calculation` |
| Turn-2 self-sufficient (own intent stated) → route directly, no ask-back | **Gap.** Ask-back fires on all turn-2 queries if confidence is even slightly ambiguous |
| Turn-2 fragment (no own intent) → ask-back for clarification | **Works,** but ask-back trigger condition is too broad |
| Clarification round-trip: merge chosen intent + entity → final query | **Works** via `_merge_pending_with_clarification`, but does not fall back to turn-1 entity |
| Unrecognized clarification → re-ask, don't guess | **Works** via the `ask_back_count` retry logic |
| Store `last_intent`, `last_entity`, `last_raw_query` | **Missing** typed fields on `SessionContext` |

---

## Proposed Changes

### Component 1: `SessionContext` — add missing state fields

#### [MODIFY] [input_rewriter.py](file:///e:/GDCE-Intern/Repo/services_version2/orchestrator/core/input_rewriter.py)

Add three new typed fields to `SessionContext`:

```python
last_intent: Optional[str] = None        # intent from the previous processed turn
last_entity: Optional[str] = None        # subject entity from last substantive turn
last_raw_query: Optional[str] = None     # raw user text from last turn (unmodified)
```

Update `resolve_clarification()` to preserve `last_entity` and `last_raw_query` after clearing pending state.

---

### Component 2: `LLMFirstLayerConfig` — fix `skip_rewrite_for_intents`

#### [MODIFY] [config.py](file:///e:/GDCE-Intern/Repo/services_version2/orchestrator/llm_first_layer/config.py)

Change the default list to include `calculation`:

```python
self.skip_rewrite_for_intents = ["hs_code_lookup", "trade_query", "calculation"]
```

---

### Component 3: `ServiceCoordinator` — fix rewrite guard + turn-2 ask-back logic

#### [MODIFY] [coordinator.py](file:///e:/GDCE-Intern/Repo/services_version2/orchestrator/core/coordinator.py)

**3a. Fix raw pass-through for calculation (line 499):**

Change:
```python
if (self.use_input_rewriter and raw_detected_intent != WorkflowIntent.TRADE_QUERY and raw_detected_intent != WorkflowIntent.HS_CODE_LOOKUP):
```
To:
```python
if (self.use_input_rewriter
        and raw_detected_intent != WorkflowIntent.TRADE_QUERY
        and raw_detected_intent != WorkflowIntent.HS_CODE_LOOKUP
        and raw_detected_intent != WorkflowIntent.CALCULATION):
```

**3b. Fix Step 10 ask-back condition (lines 460-489):**  
Only trigger ask-back on turn 2+ if the query is actually a fragment (low confidence AND no explicit self-sufficient intent). Add a `_is_self_sufficient_query()` helper that checks whether the current query already states its own intent via explicit keywords — if so, skip ask-back and route directly.

```python
# New helper method:
def _is_self_sufficient_query(self, query: str, intent: WorkflowIntent, confidence: float) -> bool:
    """
    Returns True if the query states its own intent clearly enough to skip ask-back.
    High confidence OR explicit intent keywords → self-sufficient.
    """
    SELF_SUFFICIENT_THRESHOLD = 0.75
    if confidence >= SELF_SUFFICIENT_THRESHOLD:
        return True
    return self._query_has_explicit_intent(query)
```

Update Step 10 guard:
```python
if (context.session_context and _turn_number >= 2 and not _already_resolved
        and not self._is_self_sufficient_query(normalized_question, context.intent, _intent_confidence)):
    # ... existing ask-back logic
```

**3c. Fix `_merge_pending_with_clarification` to fall back to `session.last_entity`:**

When `pending_query` has no parseable entity, fall back to `context.session_context.last_entity` (the entity stored from turn 1).

```python
# After entity extraction from pending_query, if entity is still None:
if entity is None and context_session_entity:
    entity = context_session_entity
```

Pass `session_last_entity` as an optional parameter or access it via `context.session_context`.

**3d. Update session state writes (Step 13) to populate new fields:**

After processing each turn, store:
```python
update_kwargs["last_intent"] = context.intent.value if context.intent else None
update_kwargs["last_raw_query"] = context.original_input
update_kwargs["last_entity"] = _extract_entity_from_query(context.original_input)
```

Add a lightweight `_extract_entity_from_query(query)` helper that strips intent keywords and returns the core noun phrase.

**3e. Fix `_get_rewrite_skip_reason` to reflect calculation skip:**

```python
if intent == WorkflowIntent.CALCULATION:
    return "calculation_rule"
```

---

### Component 4: New test file

#### [NEW] [test_two_turn_rewriting.py](file:///e:/GDCE-Intern/Repo/services_version2/orchestrator/tests/test_two_turn_rewriting.py)

Tests to add (all in one new file to keep them isolated):

1. **`test_turn1_hs_code_passthrough`** — hs_code intent: assert `rewritten_query == raw_query`
2. **`test_turn1_trade_passthrough`** — trade intent: assert `rewritten_query == raw_query`
3. **`test_turn1_calculation_passthrough`** — calculation intent: assert `rewritten_query == raw_query`
4. **`test_turn1_general_rewrites`** — general intent: assert `rewritten_query != raw_query` (or at least that rewrite was attempted)
5. **`test_turn2_self_sufficient_no_ask_back`** — turn 2 with clear intent ("what's the import duty for boat?") → no ask-back, direct route
6. **`test_turn2_fragment_triggers_ask_back`** — turn 2 fragment ("what about boat?") → ask-back fires with candidate intents
7. **`test_clarification_roundtrip`** — full flow: turn1=hs_code/car → turn2="what about boat?" → ask-back → user says "hs code" → final merged query = "hs code of boat"
8. **`test_unrecognized_clarification_re_asks`** — user answers clarification with garbage → re-ask fires (ask_back_count < MAX), does not guess

---

## Verification Plan

### Automated Tests
```bash
cd e:\GDCE-Intern\Repo\services_version2\orchestrator
python -m pytest tests/test_two_turn_rewriting.py -v
python -m pytest tests/test_input_rewriter.py -v
python -m pytest tests/test_coordinator.py -v
```

### Manual Verification
- [ ] Confirm `CALCULATION` queries pass the raw string to calculator service unchanged
- [ ] Confirm `TRADE_QUERY` queries pass the raw string to trade_data service unchanged
- [ ] Confirm `HS_CODE_LOOKUP` queries pass the raw string to retrieval service unchanged
- [ ] Confirm `GENERAL` queries still go through the rewriter
- [ ] Confirm turn-2 self-sufficient queries are routed without ask-back
- [ ] Confirm turn-2 fragments trigger ask-back with the fixed candidate list
- [ ] Confirm the full clarification round-trip assembles the correct merged query

---

## Open Questions

> [!IMPORTANT]
> **Q1:** The `_merge_pending_with_clarification` method currently lives in `ServiceCoordinator`. Should `last_entity` extraction also be placed there (inline), or should it be promoted to a utility on `SessionContext` itself? The latter would make it more reusable across turns, but touches the dataclass.

> [!IMPORTANT]
> **Q2:** The turn-2 self-sufficiency threshold is proposed at `0.75`. The existing `ambiguity_confidence_threshold` in `LLMFirstLayerConfig` is also `0.65`. Should both thresholds be unified, or kept separate (turn-2 ask-back is stricter than the pipeline-level ask-back)?

> [!NOTE]
> **Q3:** Should `last_raw_query` store the pre-standardization or post-standardization string? (Currently the HS code standardizer runs first, before session context is loaded.) Post-standardization is safer for entity extraction.
