# General Service Integration Report

## Step 1: Real General-Service Payload Review

Live orchestrator capture status: not available from this workspace.

Checked endpoints:

- `http://localhost:8001/health`: connection refused.
- `http://orchestrator-service-orches:8001/health`: host did not resolve.
- `http://orchestrator-service:8001/health`: host did not resolve.

Because the orchestrator is not reachable here, this report uses the existing
captured upstream fixture at:

```text
backend/api-layer/tests/fixtures/service_responses/general_orchestrator_example.json
```

Do not replace this fixture with a hand-written or corrected response. Refresh
it only from an actual orchestrator `/query` response.

## Current General Flow

1. User submits a chat message through the Nuxt/Vue chat UI.
2. The frontend sends the request to the API layer chat endpoint.
3. `backend/api-layer/app/api/v1/endpoints/chat.py` creates or touches the
   local chat thread.
4. The API layer forwards the request to the orchestrator using `POST /query`.
5. The orchestrator returns a complete response payload.
6. `normalize_chat_response()` identifies the payload as `general`.
7. The general normalizer keeps the upstream answer text unchanged.
8. The API layer returns the normalized v1 response contract to the frontend.
9. The frontend renders `message.content` blocks, with `response.content` as the
   plain-text fallback.

## Upstream Endpoint

```text
POST {MAIN_CHATBOT_SERVICE_URL}/query
```

Current default base URL:

```text
http://orchestrator-service-orches:8001
```

## Request Payload

The API layer builds the orchestrator request in
`orchestrator_query_payload()`:

```json
{
  "question": "What documents do I need to import goods into Cambodia?",
  "session_id": "chat-id"
}
```

## Response Payload

Existing captured fixture:

```json
{
  "request_id": "8afaa949-4c7a-43a4-b9b4-77aa61dbc832",
  "session_id": "debug-session",
  "question": "What documents do I need to import goods into Cambodia?",
  "answer": "When importing goods into Cambodia...",
  "intent": "general",
  "status": "completed",
  "citations": [
    {
      "doc_id": "1021",
      "title": null,
      "snippet": "Conditions for Import or Export...",
      "score": 0.9358
    }
  ],
  "clarifications": [],
  "errors": [],
  "latency_ms": 21995.5,
  "suggestion": [
    "How do I classify my goods?",
    "How is customs duty calculated?",
    "What documents do I need to import?"
  ]
}
```

## Important Fields

- `request_id`: preserved as the normalized response request id.
- `session_id`: preserved unless it is missing or templated.
- `question`: mapped to normalized `query`.
- `answer`: primary upstream answer; preserved unchanged in
  `response.content` and the first `markdown` block.
- `intent`: identifies the response as `general`.
- `status`: normalized to the stable status enum.
- `citations`: normalized to top-level `citations` for frontend source display.
- `clarifications`: normalized to top-level clarifications and a
  `clarification` block when present.
- `errors`: normalized to public error content and `error` blocks when present.
- `latency_ms`: preserved in `metrics.latency_ms`.
- `suggestion`: accepted as an upstream alias for normalized `suggestions` and a
  `suggestions` block.

## Missing Or Inconsistent Fields

- The captured fixture has no explicit `service` field; the API layer infers
  `service == "general"` from `intent`.
- The fixture uses singular `suggestion` instead of `suggestions`; the API layer
  supports this alias.
- Citation entries use `doc_id`; the citation normalizer maps that to the
  normalized citation id.
- Citation `title` may be `null`; the normalized citation keeps available
  upstream fields without inventing a title.
- The fixture does not include `metadata`, `table`, `visualization`, or a nested
  `response` object.
- The fixture answer is short and may be a truncated captured example. It should
  be refreshed only from a real orchestrator `/query` response when the
  orchestrator is reachable.

## Step 2: General Response Normalization

General responses use the existing normalized chat response contract v1.0. The
API layer may normalize envelope shape, block shape, citations, suggestions,
clarifications, errors, and metrics. It must not rewrite, summarize, or improve
the upstream general-service answer.

Canonical successful shape:

```json
{
  "api_version": "1.0",
  "request_id": "request-id",
  "session_id": "session-id",
  "status": "completed",
  "service": "general",
  "intent": "general",
  "response": {
    "type": "markdown",
    "content": "Original service answer",
    "limitations": []
  },
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "markdown",
        "text": "Original service answer"
      }
    ]
  },
  "citations": [],
  "suggestions": [],
  "clarifications": [],
  "errors": [],
  "metrics": {}
}
```

Rendering rules:

- `message.content` is the visual rendering source.
- `response.content` is the exact plain-text fallback for accessibility,
  copy/export, and unsupported clients.
- For plain general answers, the first visual block is a `markdown` block whose
  `text` equals the upstream `answer` or string `message`.
- General citations remain in top-level `citations`; they are not duplicated as
  references blocks.
- Suggestions, clarifications, coverage limitations, and errors may append
  typed blocks after the answer block when the upstream payload provides them.

## Step 3: Supported General Blocks

General responses use reusable normalized blocks only. Do not add a
service-specific `GeneralRenderer` in the frontend.

Supported block types:

1. `markdown`
2. `coverage`
3. `clarification`
4. `suggestions`
5. `references`
6. `error`

Default generated block order:

1. `markdown`
2. `clarification`, when needed
3. `suggestions`, when available
4. `coverage`, when needed

`references` blocks are supported by the v1 schema and frontend registry, but
ordinary General citations should remain in top-level `citations` so the UI does
not duplicate the same sources. `error` blocks are used for failed or unsafe
fallback responses.

Frontend rendering rule:

```text
renderer = rendererRegistry[block.type] || fallbackRenderer
```

The frontend must not select renderers based on `service == "general"` or
`intent == "general"`.

## Step 4: General Normalizer Priority

The General normalizer uses this priority:

1. Explicit upstream `message.content` blocks.
2. Explicit `answer` or `final_answer`.
3. Clarifications.
4. Suggestions.
5. Coverage or limitations.
6. Safe markdown fallback.
7. Stable error block.

Explicit upstream `message.content` blocks are authoritative for visual
rendering. When they are present, the API layer preserves supported block types
and does not append inferred clarification, suggestion, or coverage blocks.

The API layer does not generate new General answer content. If no answer text is
available, it may still render upstream clarifications, suggestions, limitations,
or a safe empty markdown/error fallback.

## Step 5: Clarification Handling

When the upstream General response asks for more information, the API layer
normalizes those questions into a first-class clarification block:

```json
{
  "type": "clarification",
  "title": "More information is needed",
  "questions": [
    "Are you asking about import or export?"
  ]
}
```

The same questions are also preserved in the machine-readable top-level
`clarifications` array.

Accepted upstream aliases:

- `clarifications`
- `clarifying_questions`
- `clarification_questions`
- `questions`

Clarification questions must not be reduced to ordinary markdown-only content.
If no answer text is provided, a General clarification response may contain a
`clarification` block without a preceding `markdown` block.

## Step 6: Suggestions Handling

When the upstream General response provides suggestions, the API layer preserves
them in the top-level machine-readable `suggestions` array and creates one
visual suggestions block:

```json
{
  "type": "suggestions",
  "title": "Suggested follow-ups",
  "items": [
    "Ask about import documents",
    "Calculate import tax"
  ]
}
```

The top-level `suggestions` array and the visual block items should contain the
same normalized values. The frontend renders the `suggestions` block from
`message.content`; it must not render top-level suggestions separately as a
second visual list.

Accepted upstream aliases:

- `suggestions`
- `suggestion`
- `follow_up_questions`
- `followups`

## Step 7: Coverage And Limitations

When the upstream General response reports partial or incomplete coverage, the
API layer creates a warning coverage block from the upstream limitation text:

```json
{
  "type": "coverage",
  "title": "Information limitation",
  "tone": "warning",
  "items": [
    "Some requested information was not available."
  ]
}
```

The API layer does not invent missing information, infer completeness from
answer length, or change the service answer. The original answer remains in
`response.content` and any `markdown` block.

Accepted limitation sources:

- `limitations`
- `missing`
- `missing_data`
- `warnings`

## Step 8: Citations

General citations normalize into the shared top-level `citations` contract.
Supported upstream citation entries include dictionaries and non-empty strings.
Empty string citations are ignored.

Rules:

- Keep inline service answer text unchanged.
- Do not guess mappings between phrases such as `Document 1` and citation
  markers.
- Do not rewrite service text into links.
- Avoid adding a duplicate `references` block when top-level citations exist.
- Render citations from top-level `citations` as shared frontend sources.

## Step 9: Error Handling

General failures normalize to safe public error objects. Raw upstream error
details may be logged internally by request ID, but they must not be returned to
the frontend.

Allowed public codes:

- `GENERAL_SERVICE_UNAVAILABLE`
- `GENERAL_TIMEOUT`
- `GENERAL_VALIDATION_ERROR`
- `INVALID_GENERAL_RESPONSE`
- `INTERNAL_API_ERROR`

Example:

```json
{
  "status": "failed",
  "errors": [
    {
      "code": "GENERAL_SERVICE_UNAVAILABLE",
      "message": "The general service is temporarily unavailable.",
      "retryable": true
    }
  ],
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "error",
        "message": "The general service is temporarily unavailable."
      }
    ]
  }
}
```

Never expose:

- internal URLs
- stack traces
- raw exceptions
- secrets
- internal prompts

## Step 12: Streaming

The `/api/v1/chat/stream` path uses the orchestrator streaming endpoint and
keeps the same final normalized response contract:

```text
event: start
event: delta
event: done
event: error
```

The API layer sends `start`, proxies live upstream text chunks as `delta`, and
normalizes the complete upstream response in `done`. Do not split a completed
General answer into fake chunks; real streaming chunks must originate in the
Main Chatbot / Orchestrator.

Keep the SSE event surface small. Add `progress` only when the frontend
genuinely displays RAG retrieval or service progress.
