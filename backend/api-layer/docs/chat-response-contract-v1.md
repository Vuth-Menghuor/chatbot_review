# Chat Response Contract v1

The API layer returns a stable frontend-safe response for chatbot requests. The
contract version is independent from the application release version.

```json
{
  "api_version": "1.0"
}
```

## Responsibility Boundaries

Architecture:

```text
Frontend
  -> API Layer
  -> Main Chatbot Orchestrator
  -> Services Team Services
```

The API layer is responsible for authentication, authorization, chat/project
metadata, rate limiting, request logging, calling the orchestrator, normalizing
orchestrator responses, and returning a stable frontend response.

The API layer normalizes service responses but does not generate or alter the
service answer. It must not run RAG, perform NLU, choose documents, recalculate
confidence, implement HS/customs/trade logic, or rewrite the orchestrator answer
content.

## Request Example

```http
POST /api/v1/chat/send
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json
```

```json
{
  "message": "What documents do I need to import goods into Cambodia?",
  "chat_id": null,
  "project_id": null,
  "attachments": [],
  "metadata": {}
}
```

## Rendering Source Of Truth

The frontend renders `message.content`.

Each item in `message.content` has a `type`. The frontend selects renderers by
block type through the renderer registry. It must not branch on `intent` or
`service` for general-question UI.

Do not render the full plain-text answer and structured blocks at the same time.
For v1.0, rendering follows this precedence:

```text
if message.content has blocks:
  render message.content by block.type
else:
  render response.content as markdown
```

`message.content` is the primary structured frontend rendering source.
`response.content` is the plain-text fallback for accessibility, export, copy,
or clients that cannot render structured blocks. Upstream fields such as
`answer` and string `message` are normalization inputs only and are not exposed
as duplicate top-level fields in the normalized response.

Current renderer mapping:

| Block type | Renderer |
| --- | --- |
| `markdown` | MarkdownRenderer |
| `coverage` | CoverageRenderer |
| `suggestions` | SuggestionsRenderer |
| `clarification` | InteractionRenderer |
| `interaction` | InteractionRenderer |
| `table` | TableRenderer |
| `chart` | Chart renderer |
| `error` | ErrorRenderer |
| unknown future type | safe fallback content |

Citations are rendered from the top-level `citations` field as sources. Do not
duplicate the same sources inside `message.content` unless a documented frontend
reason exists.

## General Success Response

For a successful general response, block order is:

1. `markdown`
2. `clarification`, when relevant
3. `suggestions`, when relevant
4. `coverage`, when relevant

```json
{
  "api_version": "1.0",
  "request_id": "8afaa949-4c7a-43a4-b9b4-77aa61dbc832",
  "session_id": "debug-session",
  "status": "completed",
  "service": "general",
  "intent": "general",
  "query": "What documents do I need to import goods into Cambodia?",
  "coverage": "unknown",
  "response": {
    "type": "markdown",
    "coverage": "unknown",
    "content": "When importing goods into Cambodia...",
    "limitations": []
  },
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "markdown",
        "text": "When importing goods into Cambodia..."
      },
      {
        "type": "suggestions",
        "title": "Suggested follow-ups",
        "items": [
          "How do I classify my goods?",
          "How is customs duty calculated?"
        ]
      }
    ]
  },
  "citations": [],
  "suggestions": [
    "How do I classify my goods?",
    "How is customs duty calculated?"
  ],
  "clarifications": [],
  "errors": [],
  "metrics": {
    "latency_ms": 21995.5
  }
}
```

## General Clarification Response

```json
{
  "api_version": "1.0",
  "request_id": "req-clarify",
  "session_id": "session-1",
  "status": "completed",
  "service": "general",
  "intent": "general",
  "coverage": "unknown",
  "response": {
    "type": "markdown",
    "coverage": "unknown",
    "content": "I need a little more information.",
    "limitations": []
  },
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "markdown",
        "text": "I need a little more information."
      },
      {
        "type": "clarification",
        "title": "More information is needed",
        "questions": [
          "What product are you importing?",
          "Which country is the product coming from?"
        ]
      }
    ]
  },
  "citations": [],
  "suggestions": [],
  "clarifications": [
    "What product are you importing?",
    "Which country is the product coming from?"
  ],
  "errors": [],
  "metrics": {}
}
```

## General Failure Response

```json
{
  "api_version": "1.0",
  "request_id": "req-failed",
  "session_id": "session-1",
  "status": "failed",
  "service": "general",
  "intent": "general",
  "coverage": "unknown",
  "response": {
    "type": "markdown",
    "coverage": "unknown",
    "content": "",
    "limitations": []
  },
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "error",
        "message": "The general service is temporarily unavailable."
      }
    ]
  },
  "citations": [],
  "suggestions": [],
  "clarifications": [],
  "errors": [
    {
      "code": "GENERAL_SERVICE_UNAVAILABLE",
      "message": "The general service is temporarily unavailable.",
      "retryable": true
    }
  ],
  "metrics": {}
}
```

## Calculator Response

Calculator responses use the same v1.0 envelope as every other service. Small
upstream payload differences must normalize into this shape without changing the
contract version:

```json
{
  "api_version": "1.0",
  "request_id": "request-id",
  "session_id": "session-id",
  "chat_id": "chat-id",
  "status": "completed",
  "service": "calculator",
  "intent": "calculation",
  "query": "original user question",
  "response": {
    "type": "markdown",
    "content": "plain fallback answer",
    "limitations": []
  },
  "message": {
    "role": "assistant",
    "content": []
  },
  "citations": [],
  "suggestions": [],
  "clarifications": [],
  "errors": [],
  "metrics": {
    "latency_ms": 0
  }
}
```

For v1.0, `message.content` remains the renderer source of truth. Top-level
`clarifications` and `errors` are stable machine-readable arrays that mirror
upstream state and any corresponding clarification/error blocks.

Calculator failures use safe public error objects in `errors`:

```json
{
  "code": "CALCULATOR_SERVICE_UNAVAILABLE",
  "message": "The calculator service is temporarily unavailable.",
  "retryable": true
}
```

Allowed calculator error codes are:

- `CALCULATOR_VALIDATION_ERROR`
- `CALCULATOR_MISSING_INPUT`
- `CALCULATOR_SERVICE_UNAVAILABLE`
- `CALCULATOR_TIMEOUT`
- `INVALID_CALCULATOR_RESPONSE`
- `INTERNAL_API_ERROR`

Raw upstream calculator errors are logged internally with the request ID and are
not exposed in the normalized response.

## Streaming

The current `/chat/stream` implementation is an SSE progress wrapper around the
same non-streaming orchestrator `/query` request used by `/chat/send`. It is not
true token streaming from the calculator service or orchestrator.

The stable calculator streaming contract is metadata at start and structured
only at completion:

```text
event: start
data: {"chat_id":"...","request_id":"..."}

event: done
data: {complete normalized v1 response}
```

The frontend uses its thinking indicator after `start`, then renders
`message.content` blocks from the final normalized `done` event. The API layer
does not stream partial calculator table rows unless an upstream structured
streaming contract is provided.

## Citation Structure

Normalized citation shape:

```json
{
  "id": "1021",
  "marker": 1,
  "label": "Source 1",
  "title": "Conditions for Import or Export",
  "snippet": "Conditions for Import or Export...",
  "score": 0.9788,
  "url": null,
  "document_id": "1021",
  "metadata": {}
}
```

Supported upstream ID fields are `id`, `doc_id`, `document_id`, and
`citation_id`.

Supported title fields are `title`, `document_title`, `filename`, and `name`.
Title fallback order is:

```text
title
-> metadata.document_title
-> metadata.filename
-> filename
-> first useful heading from snippet
-> Customs reference
```

The API avoids using a long UUID as the visible title when better display text is
available. Identifiers remain in `id`, `citation_id`, or `document_id`.

Deduplication priority:

```text
URL
-> document ID plus chunk when present
-> citation ID
-> normalized title + snippet
```

Different chunks with the same title must not be removed merely because their
titles match.

`citation.marker` is currently the normalized source display index used by the
frontend sources section. It must not be assumed to map to inline answer text
such as `Document 1` unless the orchestrator explicitly provides that mapping.

Keep the orchestrator answer unchanged. Do not rewrite inline text such as
`([Document 1])`, and do not use regex or other guessing logic to convert it
into links. Preserve the service-generated answer exactly and display citations
separately.

The services team should eventually return explicit answer markers such as
`[1]`, `[2]` and matching citation `marker` values.

## Services Team Follow-Ups

The following issues are owned by the orchestrator or services team, not the API
layer. The API layer must not fix them by rewriting the service-generated
answer, filtering answer content, changing retrieval order, recalculating
coverage, or repairing service NLU metadata.

- Overly specific retrieval results for a general import question.
- Inline `Document N` markers have no explicit source mapping.
- Some upstream citation titles are null.
- `nlu_entity` is null while `has_nlu_entity` is true.
- `coverage` is unknown.
- Response latency is approximately 26 seconds.

## Suggestion Structure

The API accepts upstream `suggestions`, `suggestion`, `follow_up_questions`, and
`followups`, but the frontend contract returns only:

```json
{
  "suggestions": [
    "How do I classify my goods?",
    "How is customs duty calculated?"
  ]
}
```

Empty strings and duplicates are removed. Do not return both `suggestion` and
`suggestions`.

## Coverage And Limitations

Coverage values are limited to:

```text
complete
partial
unknown
```

Coverage is read from upstream when available. The API must not infer answer
completeness from answer length.

Limitations are normalized from `limitations`, `missing`, `missing_data`, and
`warnings`.

Partial answers with limitation data include a coverage block:

```json
{
  "type": "coverage",
  "title": "Information limitation",
  "tone": "warning",
  "items": [
    "The exact requirements depend on the product and HS code."
  ]
}
```

For `coverage: "unknown"` with no limitations, do not show a warning block.

## Debug Rules

Production responses omit `debug` by default. When debug is disabled, the field
is omitted rather than returned as an empty structure.

Debug is available only when explicitly enabled by the API route and authorized:

- development/local environments
- authorized administrator access

Normal users cannot enable debug through an unrestricted query parameter.

Debug metadata must not expose secrets, API keys, internal URLs, raw tokens, or
complete internal prompts.

## Versioning Rules

`api_version` is the response-contract version. It is not the project
application version.

Version `1.0` promises that the frontend can safely validate and render the
documented fields. Breaking response-contract changes require a new contract
version.

## Unknown-Block Behavior

The frontend validates normalized responses at runtime. Unknown future block
types must not crash chat rendering.

Unknown blocks are converted to safe fallback content:

```json
{
  "type": "fallback",
  "content": "Unsupported response content"
}
```

Do not display raw JSON to normal users unless it is inside a development-only
tool-output view.
