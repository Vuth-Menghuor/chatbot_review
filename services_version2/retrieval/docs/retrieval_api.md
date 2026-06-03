### `POST /v1/hs-code-candidates`


**Purpose:**
Return all possible HS code candidates for a product description, with Gemini LLM-powered explanations for each candidate. The LLM does not summarize the HS code descriptions, but explains each clearly and concisely, especially when the context is broad.

**Docker Compose Note:**
- Always set `QDRANT_HOST=qdrant` and `QDRANT_PORT=6333` in your `.env` when running under Docker Compose.
- If you see collection errors, ensure you have seeded the Qdrant Docker instance (not a local Qdrant) using the correct host/port.

**Troubleshooting:**
- If Qdrant is `unhealthy`, check logs with `sudo docker logs qdrant` and resolve any errors before retrying.

**Request body:**

```json
{
  "query": "cotton fabric",
  "generate_answer": true
}
```

**Response fields:**

- `documents`: All candidate HS code documents (with `content`, `metadata`, and `hs_code`)
- `final_answer`: LLM-generated explanations for each candidate (not a summary)
- `answer_source`: e.g., `gemini_llm`
- `status`, `api_called`, `session_id`, etc.

**Notes:**
- If the context is broad, all possible candidates are returned (not just top 3/5).
- The LLM is instructed to explain each candidate clearly and concisely, not to summarize the description.
- Use this endpoint when you want both the candidate pool and LLM explanations for user-facing review/selection.

**Example response:**

```json
{
  "query": "cotton fabric",
  "documents": [
    { "id": "1", "content": "Woven fabrics of cotton", "score": 0.95, "source": "semantic", "metadata": { "hs_code": "5208" } },
    { "id": "2", "content": "Unbleached cotton fabrics", "score": 0.91, "source": "semantic", "metadata": { "hs_code": "5209" } }
  ],
  "final_answer": "5208: Used for woven cotton fabrics, typically plain weave. 5209: Unbleached cotton fabrics, often used for further processing.",
  "answer_source": "gemini_llm",
  "status": "success",
  "api_called": "/v1/hs-code-candidates",
  "total_count": 2
}
```
# Retrieval Service (v2) API Contract — Quick Reference


**Base path:** `/v1`
**Default port:** retrieval service typically runs at `:8003` (confirm with host)

---


## Common Request Fields (JSON)

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | **Yes** | The search query |
| `top_k` | int | No | Candidate pool size (server default used if omitted) |
| `generate_answer` | bool | No | If `true`, retrieval will attempt to generate `final_answer` via LLM |
| `collection` | string | No | `"gdce_docs"` or `"gdce_hs_code"` |
| `hs_mode` | string | No | HS calls only: `"best"` (default) \| `"select"` \| `"compare"` |
| `selected_code` | string | Required for `hs_mode="select"` | A specific HS code to validate |
| `compare_codes` | list[string] | Required for `hs_mode="compare"` | HS codes to compare |
| `session_id` | string | No | Optional trace/session identifier |

---

## Primary Endpoints


### `POST /v1/hs-code-lookup`

**Purpose:** HS classification/discovery. Returns all candidate codes in the `documents`, `candidate_docs`, and `candidates` fields. The orchestrator or UI should display these for user review and selection.

**Example request body:**

```json
{
  "query": "muzzle-loading firearms",
  "top_k": 10,
  "generate_answer": true,
  "collection": "gdce_hs_code",
  "hs_mode": "best"
}
```


**Successful response (200) — key fields:**

```json
{
  "query": "...",
  "documents": [
    {
      "id": "...",
      "score": 0.95,
      "content": "...",
      "metadata": {
        "hs_code": "9303.00.00",
        "description": "muzzle-loading firearms"
      }
    }
  ],
  "total_count": 5,
  "hs_mode": "best",
  "heading_4_digit": "9303",
  "missing_parameters": [],
  "status": "success",
  "hs_validation": {
    "status": "success",
    "message": "Validated retrieval result.",
    "primary_code": "9303.00.00",
    "candidates": ["9303.00.00", "9303.20.00", "9302.00.00"],
    "conflict": null
  },
  "candidates": ["9303.00.00", "9303.20.00", "9302.00.00"],
  "candidate_docs": [
    { "rank": 1, "hs_code": "9303.00.00", "description": "...", "score": 0.95 }
  ],
  "final_answer": null,
  "answer_source": null,
  "api_visibility": {
    "api_called": "v1/hs-code-lookup",
    "collection_used": "gdce_hs_code",
    "processing_path": "semantic+structured"
  },
  "session_id": "...",
  "language": "en",
  "_endpoint_used": "/v1/hs-code-lookup"
}
```

**Notes:**

- For HS lookups, the `documents`, `candidate_docs`, and `candidates` fields provide the actual HS code candidates. The orchestrator or UI should display these for user review and selection.
- `final_answer` is only present for non-HS flows or select-mode HS requests.
- `hs_validation.{status, primary_code, candidates, conflict}` must be provided for `HS_LOOKUP` flows so the orchestrator can trust retrieval's selection/validation.
- `candidate_docs` and `candidates` are recommended for UI provenance; `final_answer` can also embed a "Possible matches" block if desired.

---

### `POST /v1/definition`

**Purpose:** Definition / FAQ / Policy retrieval.

**Request body:**

```json
{
  "query": "...",
  "top_k": 5,
  "generate_answer": true
}
```

**Response fields:** `documents`, `total_count`, `final_answer`, `answer_source`, `status`, `api_visibility`, `session_id`, `language`, `_endpoint_used`

---

### `POST /v1/policy-inquiry`

**Purpose:** Policy / procedural queries.

Behavior similar to `/v1/definition` — returns `documents` + `final_answer` + `status`.

---

### `POST /v1/general`

**Purpose:** General free-form retrieval using primary documents.

Same response shape as `/v1/definition`.

---

## Error Responses

| HTTP Code | Cause | Response body |
|---|---|---|
| `400` | Validation errors (e.g., missing `selected_code` in select mode) | `{"error": "...", "status": "invalid_request"}` |
| `500` | Internal errors | `{"error": "internal error", "status": "error"}` |

---

## Best Practices for Consumers

- **Always display `final_answer`** if present.
- If `final_answer` is missing, fallback to:
  - `hs_validation` info for HS flows — **do not guess a code.**
  - `documents` preview for non-HS flows with a clear "I could not find a direct answer" message.
- **Respect `status` flags:** when `status` is `clarification_required` or `ambiguous`, ask for clarification instead of attempting to classify.

---

## Appendix — Example End-to-End HS Flow (Muzzle-loading Firearms)

1. Orchestrator sends `POST /v1/hs-code-lookup` with `generate_answer=true`.
2. Retrieval returns `final_answer` and `hs_validation` showing `primary_code` and `candidate_docs`.
3. Orchestrator displays `final_answer` to the user and prints `candidate_docs` as **"Possible matches"** for provenance.
4. If `status=ambiguous` or `hs_validation.status != success`, orchestrator asks for clarification.