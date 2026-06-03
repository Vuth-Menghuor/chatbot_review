# Integration Guidelines for Orchestrator Owner
## 8. HS Code Candidates Endpoint


Use the `/v1/hs-code-candidates` endpoint to retrieve all possible HS code candidates for a product description, with Gemini LLM-powered explanations for each candidate. This endpoint is recommended when the orchestrator or UI needs to display a broad candidate pool and provide users with clear, concise explanations for each option.

**Docker Compose Note:**
- Always set `QDRANT_HOST=qdrant` and `QDRANT_PORT=6333` in your `.env` when running under Docker Compose.
- If you see collection errors, ensure you have seeded the Qdrant Docker instance (not a local Qdrant) using the correct host/port.

**Troubleshooting:**
- If Qdrant is `unhealthy`, check logs with `sudo docker logs qdrant` and resolve any errors before retrying.

- The LLM does not summarize the HS code descriptions, but explains each clearly and concisely.
- If the context is broad, all possible candidates are returned (not just top 3/5).

**Recommended Orchestrator Behavior:**
- Display all candidates and their LLM explanations for user review/selection.
- Do not treat the LLM explanation as a final classification; use it for user guidance.

**Example request:**
```json
{
  "query": "cotton fabric",
  "generate_answer": true
}
```

**Example response:**
```json
{
  "documents": [ ... ],
  "final_answer": "5208: Used for woven cotton fabrics, typically plain weave. 5209: Unbleached cotton fabrics, often used for further processing.",
  "answer_source": "gemini_llm"
}
```
## Objective


Integrate the retrieval v2 service as the authoritative source for retrieval, HS candidate discovery, validation, and natural-language final answers (for non-HS flows). For HS lookups, retrieval returns all candidate codes and validation info; orchestration should display these to the user and handle final selection/clarification.

---

## 1. Invocation / Routing

For user queries the orchestrator should:

- Normalize the query (strip filler phrases) for HS-style lookups.
- Run light-rule intent detection (keeps high-precision rules for fee/service cases). If no rule match, fallback to LLM intent detection.
- Map intent to endpoints:

  - `HS_LOOKUP` → `POST /v1/hs-code-lookup` (returns candidate codes in `documents`, `candidate_docs`, and `candidates` fields)
  - `DEFINITION` → `POST /v1/definition`
  - `POLICY_QUERY` → `POST /v1/policy-inquiry`
  - `GENERAL` → `POST /v1/general`

---

## 2. Request Payload


Always include:

| Field | Type | Description |
|---|---|---|
| `query` | string | Normalized query |
| `top_k` | int | Desired candidate pool size (recommended default: `5`) |
| `generate_answer` | bool | Whether to produce `final_answer` (recommended: `true`) |
| `hs_mode` *(optional)* | string | `"best"` \| `"select"` \| `"compare"` |
| `selected_code` *(optional)* | string | A chosen HS code |
| `session_id` *(optional)* | string | Session identifier |
| `collection` *(optional)* | string | `"gdce_docs"` or `"gdce_hs_code"` |


**Example:**

```json
{
  "query": "muzzle-loading firearms",
  "top_k": 5,
  "generate_answer": true,
  "hs_mode": "best"
}
```

---


## 3. Response Consumption — Required Fields to Read

| Field | Type | Description |
|---|---|---|
| `status` | string | `success` \| `clarification_required` \| `not_found` \| `ambiguous` \| `inconsistent` \| `error` |
| `documents` | list | Retrieval candidate documents (always present for HS lookups; each may include `content`, `metadata`, and sometimes `hs_code`) |
| `candidate_docs` | list[object] *(HS flows)* | Preview candidate objects `{ rank, hs_code, description, score }` — recommended for UI provenance and review |
| `candidates` | list[string] *(HS flows)* | Top candidate HS codes |
| `final_answer` | string *(optional)* | LLM-crafted final natural-language response. **Present for non-HS flows or select-mode HS requests.** |
| `answer_source` | string *(optional)* | e.g., `"gemini_llm"` or `"extractive_fallback"` |
| `hs_validation` | object *(HS flows only, required)* | See sub-fields below |
| `clarification` | string *(optional)* | Clarification text to display or ask user |
| `missing_parameters` | list[string] *(optional)* | List of missing parameters |

### `hs_validation` Sub-fields

| Field | Type | Description |
|---|---|---|
| `status` | string | `success` \| `ambiguous` \| `inconsistent` \| `not_found` |
| `primary_code` | string \| null | Top rank-1 HS code detected |
| `candidates` | list[string] | Top candidate HS codes |
| `message` | string | Base validation message |
| `conflict` | string \| null | Semantic conflict guardrail message |
| `selected_status` *(optional)* | — | Validation for a chosen code |
| `selected_message` *(optional)* | — | Validation message for a chosen code |

---

## 4. Orchestrator Behavior Recommendations

- **For HS lookups, always display the `candidate_docs` and/or `documents` as the authoritative list of what was retrieved.**
- **Do not display a guessed HS code as the final answer unless the user has selected one or the retrieval service is in select mode.**
- **For non-HS flows, prefer `retrieval.final_answer` for the assistant reply.**
- If retrieval returns `status` in `{ambiguous, clarification_required, inconsistent, not_found}`, present `retrieval.clarification` or an orchestrator-generated clarification question — **not a guessed HS code.**

---

## 5. Provenance & UX

- Display `candidate_docs` (if present) as a clearly labeled **"Possible matches"** block beneath the assistant message for transparency.
- Show `answer_source` (e.g., `gemini_llm`) and endpoint used as system/debug metadata.

---

## 6. Error Handling and Timeouts

...existing content...

- **Stop performing LLM-based HS selection locally.** Instead:
  - Use `retrieval.hs_validation.primary_code` and `retrieval.selected_code` (if present).
  - If orchestrator still desires a confirmatory LLM selection, call the retrieval select-mode endpoint: `POST /v1/hs-code-lookup` with `hs_mode="select"` and `selected_code`.

- **For ambiguous / low-confidence flows:**
  - If retrieval returns `status` in `{ambiguous, clarification_required, inconsistent, not_found}`, present `retrieval.clarification` or an orchestrator-generated clarification question — **not a guessed HS code.**

- Always include `raw_retrieval` payload in logs to aid debugging.

---

## 5. Provenance & UX

- Display `final_answer` as the assistant message.
- Display `candidate_docs` (if present) as a clearly labeled **"Possible matches"** block beneath the assistant message for transparency.
- Show `answer_source` (e.g., `gemini_llm`) and endpoint used as system/debug metadata.

---

## 6. Error Handling and Timeouts

- Use a sensible HTTP timeout for calls to retrieval (e.g., `30s` default; allow override).
- If retrieval **times out**, return a clear error message to the user and log the exception.
- If retrieval returns `status: "error"` or HTTP `5xx`, surface a concise **"service unavailable"** message.

---

## 7. Security & Keys

- Retrieval's Gemini usage requires `GEMINI_API_KEY` on the **retrieval side**.
- Orchestrator should **not** send keys; only pass `session_id` / trace metadata if needed.