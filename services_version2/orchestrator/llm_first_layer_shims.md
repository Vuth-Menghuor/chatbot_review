# GDCE Chatbot: LLM First Layer & Shim Architecture Guide

This document explains the technical design, architectural connections, and rationale behind the **`llm_first_layer`** subsystem and its **shims** in the GDCE Chatbot Orchestrator service.

---

## 1. Context: The Latency Challenge

In earlier iterations of the GDCE Chatbot Orchestrator, processing a user request required executing multiple independent linguistic evaluations using Large Language Models (LLMs like Gemini):

```
User Query
    │
    ├── Step 1: Input Validation (LLM Call #1)
    │           - checks scope boundaries and security exploits
    │
    ├── Step 2: Intent Classification (LLM Call #2)
    │           - categorizes the query (e.g. calculation, trade query)
    │
    └── Step 3: Query Rewriting (LLM Call #3)
                - rephrases the prompt using multi-turn conversational history
```

Because each task operated as a standalone class invoking the LLM independently, **network round-trip latency was cumulative**. A single user message could take 2–3 seconds simply navigating these front-door checks before the orchestrator even invoked the primary database, retrieval indexes, or calculator microservices.

---

## 2. The Solution: Unified `llm_first_layer`

To optimize performance, the system consolidated these front-door NLP tasks under the [`llm_first_layer`](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/llm_first_layer) package.

This unified layer coordinates:
* Input validation (safety, injection, scope checks).
* Intent classification (Gemini classification with fallback).
* Currency detection.
* Conversational query rewriting.

Instead of three isolated LLM round-trips, the subsystem handles validations and query cleaning in a unified pipeline (`llm_first_layer/pipeline.py`), drastically reducing processing overhead.

---

## 3. The Compatibility Bridge: The Shim Pattern

Although the underlying logic was consolidated into `llm_first_layer`, refactoring every single reference across the orchestrator (e.g., in [`coordinator.py`](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/core/coordinator.py), other submodules, and various test suites like `tests/test_validator_service.py`) would introduce high regression risk and break existing APIs.

To resolve this, the developers implemented **Shims** under [`llm_first_layer/shims/`](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/llm_first_layer/shims). A "shim" is a lightweight structural bridge that mimics legacy APIs while redirecting execution to the new consolidated service.

```
Legacy Imports in coordinator.py                  Consolidated Subsystem
┌─────────────────────────────────┐               ┌──────────────────────────────────────┐
│  OrchestratorIntentService      ├──────┐        │                                      │
├─────────────────────────────────┤      │        │                                      │
│  RewriterService                ├──────┼───────►│  LLMFirstLayerService (Singleton)     │
├─────────────────────────────────┤      │        │  (Coordinates all NLP pipeline steps)│
│  ValidatorService /             │      │        │                                      │
│  InputValidator                 ├──────┘        │                                      │
└─────────────────────────────────┘               └──────────────────────────────────────┘
```

---

## 4. Breakdown of Shims & File Structure

Here is how the legacy components are wired into the unified layer under `llm_first_layer/shims`:

### A. Intent Service Shim ([`shims/intent_service.py`](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/llm_first_layer/shims/intent_service.py))
```python
class IntentServiceConfig:
    def __init__(self, **kwargs):
        self.provider = kwargs.get("provider", "gemini")
        self.timeout = kwargs.get("timeout", 60)
        # Keeps legacy configurations passing through without throwing errors

def get_intent_service(config=None) -> Any:
    # Returns the unified singleton instance instead of a separate service
    return get_llm_first_layer_service()
```
* **Why it exists:** Keeps `WorkflowExecutor` (which expects a standalone `llm_detector` with a `detect_intent()` method) working without modifications.

### B. Rewriter Service Shim ([`shims/rewriter_service.py`](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/llm_first_layer/shims/rewriter_service.py))
```python
class RewriterServiceConfig:
    def __init__(self, **kwargs):
        # Maps legacy config kwargs to maintain compatibility
        ...

def get_rewriter_service(config=None) -> Any:
    # Routes to the consolidated first-layer service
    return get_llm_first_layer_service()
```
* **Why it exists:** `ServiceCoordinator` still calls `self.rewriter_service.rewrite_input(...)`. The shim ensures this call maps directly to the unified service instance.

### C. Validator Service Shim ([`shims/validator_service.py`](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/llm_first_layer/shims/validator_service.py))
* **Why it exists:** This contains the main validation class structure (`InputValidator` / `ValidatorService`) and standalone utility wrappers like `extract_certificate_type()` or `is_short_rate_reply()`. It enables rule-based local fast-passes and handles async Gemini calls for prompt-driven scope/injection evaluations.

---

## 5. Architectural Benefits

1. **Zero Breaking Changes:** External scripts, CLI commands, and unit tests continue to import classes like `ValidatorService` and run without failure.
2. **Centralized Lifecycle:** The `LLMFirstLayerService` singleton acts as the single point of initialization, reducing connection leaks or API key conflicts.
3. **DRY (Don't Repeat Yourself) Prompts:** Shared structures (e.g. knowing whether a query is raw commodity description) are identified once and reuse context fields across the pipeline.
