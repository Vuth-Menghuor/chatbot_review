# Orchestrator Service v2 — Summary

## Overview

A FastAPI-based orchestration layer that receives user questions, validates input, detects intent, and routes requests across dependent services (Retrieval v2, Calculator v2, Trade Query v2). It centralizes workflow control, fallback behavior, timeout policies, caching, and response shaping for a unified chat/query API.

## Key files

- main.py — Uvicorn entrypoint for orchestrator startup
- app.py — FastAPI app factory, middleware, startup wiring, background health checks
- api/endpoints.py — HTTP endpoints (/query, /chat, /health, /status, /info)
- core/coordinator.py — Main orchestration flow, routing handlers, response assembly/formatting
- core/workflow.py — Intent/currency detection, workflow context, query cleanup and validation helpers
- core/llm_intent_detector.py — LLM-based intent classification with fallback behavior
- core/minilm_intent_detector.py — MiniLM-based semantic support for currency/intent signals
- core/input_rewriter.py — Session-aware input rewriting for multi-turn conversations
- core/timeout_config.py — Intent/service-specific timeout strategy
- infrastructure/clients.py — Service HTTP clients (retrieval/calculator/trade), retry/circuit-breaker logic, Gemini helper client
- infrastructure/cache_service.py — In-memory cache layer with TTL by intent
- config.py — Environment-driven orchestrator configuration and config JSON loading
- tests/ — Unit/integration tests for workflow, coordinator, endpoints, and client behavior

## Capabilities

- Unified API surface: single /query and /chat entrypoints for all supported intents
- Intent detection pipeline: LLM-first (if enabled) with keyword fallback
- Multi-intent routing: calculation, trade_query, hs_code_lookup, definition/policy, general fallback
- Retrieval v2 contract support:
  - /v1/hs-code-lookup
  - /v1/definition
  - /v1/policy-inquiry
  - /v1/general
- HS lookup guardrails:
  - Query cleanup (filler phrase removal)
  - Critical discriminator checks (vehicle/food/textile)
  - Semantic conflict checks and clarification prompts
- HS selection enhancements:
  - Candidate ranking + optional Gemini-based best-code selection
  - User-friendly description rewriting for returned HS options
- Currency handling for calculations:
  - Pattern/keyword detection
  - LLM/MiniLM fallback
  - Country-to-currency inference
  - Default to KHR when unresolved
- Trade query response adaptation:
  - Handles updated trade_query response variants (aggregate/ranking/monthly/comparison/anomaly)
  - Builds anomaly summary blocks from payload or from returned records when needed
- Reliability controls:
  - Per-intent and per-service timeout enforcement
  - Retry and circuit-breaker in HTTP clients
  - Cache-first reads for expensive/repeated retrieval queries
  - Startup and periodic health checks for downstream services

## Recent fixes / work

- Migrated orchestrator retrieval integration to the Retrieval v2 endpoint contract (intent-specific endpoints).
- Added 4-tier currency detection flow with conservative confidence handling and KHR-safe default.
- Implemented HS query cleanup and critical discriminator validations before/around HS lookup handling.
- Added Gemini-backed HS best-candidate selection and description rewriting (with score-based fallback).
- Refactored trade response formatting to align with newly updated trade_query outputs, including anomaly-style rendering and comparison payloads.
- Added env alias tolerance in trade*query config for TRADE_SERVICE*_ and TRADE*DATA*_ naming consistency.
- Synchronized retrieval local env port/url mapping with orchestrator service URL expectations.

## Gaps & Risks

- External dependency sensitivity: orchestrator quality depends on retrieval/trade/calculator uptime and remote DB availability.
- Trade response shape drift risk: trade_query evolves quickly; formatter needs regression tests for new/changed response schemas.
- LLM variability: Gemini/Ollama output differences can affect deterministic formatting or selection behavior.
- Startup coupling: app.py still includes direct cross-service adapter initialization paths; full HTTP-only isolation is not complete.
- Test coverage gaps remain for end-to-end anomaly/comparison formatting through orchestrator /query.

## Suggested next steps

1. Add orchestrator integration tests for trade_query anomaly/comparison payloads (including sample-format assertions).
2. Add contract tests for retrieval v2 endpoints and orchestrator response fields.
3. Add feature flags to toggle Gemini HS selection/description rewrite at runtime.
4. Harden observability: emit structured metrics for intent distribution, downstream latency, fallback rates, and cache hit ratio.
5. Run a full smoke suite with service_scripts start flow and representative multi-intent queries, then capture golden outputs.

---

Generated on 2026-04-23
