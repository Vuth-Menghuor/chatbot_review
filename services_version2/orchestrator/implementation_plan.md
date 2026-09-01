# Implementation Plan - General Route & Format Optimization

The goal of this plan is to ensure that user queries phrased as questions are routed to the `general` service/intent, and that general intent queries skip orchestrator-side LLM formatting **only if** the microservice's JSON response contains `final_answer`. If `final_answer` is not present, formatting will be applied normally.

## User Review Required

> [IMPORTANT]
> The general microservice (on port 8005) must have its Gemini client enabled (`GEMINI_ENABLED=true` in `general/.env`) so it can generate the `final_answer`. This is already configured in the environment.
> We bypass the second LLM formatting call in the Orchestrator for `general` intent iff `final_answer` is present, which will speed up response times and reduce API usage.

## Proposed Changes

### Intent Detection Rules

#### [MODIFY] [tasks.yaml](file:///e:/GDCE-Intern/Local/orchestrator/prompts/core_tasks/gemini/tasks.yaml)
- In the `gemini_unified_first_layer` prompt, add specific instructions to route general questions (e.g. queries starting with "what", "how", "why", "is", "can", "where", or containing a "?") to the `general` intent if they do not match the specific `calculation`, `trade_query`, or `hs_code_lookup` rules.

#### [MODIFY] [workflow.py](file:///e:/GDCE-Intern/Local/orchestrator/app/services/workflow.py)
- Update keyword-based intent detection in `detect_intent_with_confidence` to map question words and "?" to `general` when no other specific keywords are present.

### Service Client & Coordinator Configuration

#### [MODIFY] [clients.py](file:///e:/GDCE-Intern/Local/orchestrator/app/infrastructure/clients.py)
- Update `GeneralServiceClient._ask` to set `"generate_answer": generate_answer` in the payload passed to the general microservice (so it generates `final_answer`).
- Add a check `if generate_answer and not result.get("final_answer"):` in `GeneralServiceClient._ask` to skip local orchestrator-side LLM generation if the microservice has already provided `final_answer`.

#### [MODIFY] [coordinator.py](file:///e:/GDCE-Intern/Local/orchestrator/app/services/coordinator.py)
- In `_build_response`, set `response["metadata"]["has_final_answer"] = True` if `context.retrieval_result` is present and contains a non-empty `final_answer`.

#### [MODIFY] [endpoints.py](file:///e:/GDCE-Intern/Local/orchestrator/app/api/endpoints.py)
- In `/query/stream`, pass `metadata` or `has_final_answer` through the `context` dictionary into the formatter call.

### Formatter Optimization

#### [MODIFY] [summarizer.py](file:///e:/GDCE-Intern/Local/orchestrator/app/ai/summarizer.py)
- In `format_response_stream`, if the intent is general (e.g. `'general'`, `'definition'`, `'policy'`, `'policy_query'`) **and** `has_final_answer` is `True`, yield the `base_answer` directly and return, bypassing the orchestrator-side formatter LLM call. Otherwise, format normally.

---

## Verification Plan

### Automated Tests
- Run `pytest tests/test_general_entity_grounding.py` to ensure existing general entity fallback tests pass.
- Run `pytest tests/test_orchestrator_scenarios.py` to verify general integration scenarios.

### Manual Verification
- Send a general query (e.g., "what is the duty exemption for QIP?") to `/query` or `/query/stream` and verify that the response uses the `final_answer` directly from the general microservice.
- Mock a response from general microservice without `final_answer` and verify that orchestrator formats it normally.
