# Retrieval Service (v2) — Summary

---


## Purpose

The Retrieval Service v2 is the authoritative backend for document retrieval, HS candidate discovery, candidate validation, and (for non-HS intents) generation of a polished natural-language answer. It accepts normalized queries from an orchestrator, performs semantic/structured retrieval, applies HS-specific ranking and guardrails, and returns structured results for the orchestrator to consume.

**Docker Compose Note:**
- Always set `QDRANT_HOST=qdrant` and `QDRANT_PORT=6333` in your `.env` when running under Docker Compose.
- If you see collection errors, ensure you have seeded the Qdrant Docker instance (not a local Qdrant) using the correct host/port.

**Troubleshooting:**
- If Qdrant is `unhealthy`, check logs with `sudo docker logs qdrant` and resolve any errors before retrying.

---

## Key Responsibilities

### 1. Retrieval

- Execute semantic and structured search over configured collections (`gdce_docs`, `gdce_hs_code`).
- Normalize and expand HS-style queries to improve recall (synonyms, phrase expansions).
- Return a ranked set of documents with payload metadata (`content`, `metadata`, `hs_code`, `score`).

### 2. HS Candidate Discovery and Ranking

For HS lookup requests (`collection=gdce_hs_code`):

- Produce a broader candidate pool (higher internal `top_k`) and apply HS-specific ranking (heading boosts, keyword-to-heading mapping, lexical scoring).
- Merge direct exact-code fetches and heading-based scans when appropriate.
- Return an `HSSelectionResult` (documents list, predicted 4-digit heading, `missing_parameters`, optional clarification text).

### 3. HS Validation and Guardrails

Run conservative validation heuristics (migrated from orchestrator) to detect:

| Condition | Status |
|---|---|
| No parsable HS code in top docs | `not_found` |
| Top candidates span multiple chapters or are too close in score | `ambiguous` |
| Domain-specific mismatches (e.g., vehicle wording vs non-87xx primary) | `inconsistent` |
| Gendered textile or chemical-name mismatches between query and candidate | `inconsistent` (semantic conflict) |

Returns structured `hs_validation` containing: `status`, `primary_code`, `candidates` (list of code strings), `message`, `conflict`, and selected-code validation fields if applicable.

### 4. Candidate Previews and Provenance


Always include candidate previews for HS flows:

- `documents`: all retrieved candidate documents (each may include `content`, `metadata`, and sometimes `hs_code`)
- `candidate_docs`: top-N preview objects `{ rank, hs_code, description, score }`
- `candidates`: top-N HS code strings

These fields are the authoritative source for what was retrieved and should be displayed in the UI or used by the orchestrator for selection logic. Retrieval does not make the final HS code selection in best-mode; it returns all candidates and validation info for review.

### 5. Final-Answer Generation (LLM)

**Mandatory behavior:**

- **For non-HS intents** (`DEFINITION`, `POLICY_QUERY`, `GENERAL`): generate and return `final_answer` (LLM output) and `answer_source` (e.g., `gemini_llm`).
- **For `HS_LOOKUP`:**
  - Do **NOT** return a final HS classification `final_answer` in best-mode responses. Instead return `candidate_docs` and `hs_validation` for the orchestrator to run final selection and produce the final answer.
  - If `hs_mode="select"` (with a `selected_code` in the request), the retrieval service **MAY** generate a select-mode `final_answer` describing the provided selected code (used when the orchestrator asks retrieval to format a chosen code).
- Use Gemini as the primary LLM for answer generation when configured, falling back to other available mechanisms if needed.

---

## Response Fields (Most Important)

| Field | Description |
|---|---|
| `documents` | List of returned document objects (`content`, `metadata`, `score`) |
| `status` | Overall request status: `success` \| `clarification_required` \| `not_found` \| `ambiguous` \| `inconsistent` \| `error` |
| `hs_validation` | *(HS_LOOKUP only)* `{ status, primary_code, candidates, message, conflict, selected_status, selected_message }` |
| `candidate_docs` | *(HS_LOOKUP)* `[ { rank, hs_code, description, score }, ... ]` |
| `candidates` | *(HS_LOOKUP)* `[ "XXXX.XX.XX", ... ]` |
| `final_answer` | LLM-generated natural-language answer (non-HS intents, and `hs_mode="select"` requests) |
| `answer_source` | Provenance of `final_answer` (e.g., `gemini_llm`) |
| `clarification` / `missing_parameters` | Returned when additional input is required |
| `api_visibility`, `session_id`, `language`, `heading_4_digit`, `total_count`, `keywords`, `_endpoint_used` | Observability metadata |

---

## Design Principles and Recommendations

- **Retrieval is authoritative for HS candidates and validation.** Orchestrator should use `hs_validation` and `candidate_docs` as the source of truth for HS selection.
- **Retrieval must not guess or return a final HS classification** for `HS_LOOKUP` best-mode responses; orchestration (or a human) must perform final selection using `candidate_docs` and `hs_validation`.
- **Always return `candidate_docs`** for `HS_LOOKUP` responses (even if the service collapses documents internally) to preserve transparency.
- **For non-HS flows**, retrieval should produce a user-ready `final_answer` and mark the `answer_source`.
- **Keep guardrails conservative** — prefer asking for clarification over returning a potentially incorrect HS classification.

---

## Operational Notes

- Ensure `GEMINI_API_KEY` is configured on the retrieval host if Gemini is used.
- Use the `generate_answer` flag to control whether the service produces a `final_answer` for non-HS requests.
- Monitor and log `answer_source` and `hs_validation` fields for auditing and quality tracking.

---

*This summary documents the retrieval service's responsibilities and the exact division of labor: retrieval handles candidate discovery, ranking, validation, and non-HS final-answer generation; HS final classification (best-mode) remains the orchestrator's responsibility, with retrieval returning candidates and validation info to support that decision.*

---

## New Endpoint: `/v1/hs-code-candidates`

- Returns all possible HS code candidates for a product description, with Gemini LLM-powered explanations for each candidate.
- LLM explanations are clear and concise, not summaries of the descriptions.
- Use this endpoint for broad candidate pools and user-facing review/selection.