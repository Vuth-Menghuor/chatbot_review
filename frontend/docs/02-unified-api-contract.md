# Unified API Contract

All backends (LM Studio teaching mode, future REST API) must normalize to this envelope before rendering.

## Top-level envelope

```json
{
  "requestId": "uuid-12345",
  "mode": "sync | stream | async",
  "status": "success | pending | error | partial",
  "tools": [ /* UnifiedToolItem[] */ ],
  "timestamp": "2026-02-18T12:30:00Z",
  "error": null
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `requestId` | string | Unique id for this request (used in block ids) |
| `mode` | `sync \| stream \| async` | Overall request mode |
| `status` | `success \| pending \| error \| partial` | Overall status |
| `tools` | array | Ordered list of tool results (UI renders in order) |
| `timestamp` | ISO-8601 | Optional |
| `error` | object \| string \| null | Top-level failure |

## Tool item (base)

Every tool shares:

```json
{
  "toolName": "Human-readable name",
  "type": "workflow | chat | ocr | ...",
  "mode": "sync | stream | async",
  "status": "success | pending | processing | error | cancelled",
  "data": {},
  "error": null,
  "meta": {}
}
```

### Mode-specific fields

**Sync** — `data` contains the payload.

**Stream** — `streamChunks`:

```json
"streamChunks": [
  { "chunk": "partial text", "done": false, "index": 0 },
  { "chunk": " more text", "done": true, "index": 1 }
]
```

**Async** — `taskId`:

```json
"taskId": "task-789"
```

## Tool type → UI mapping

| `type` | `mode` | Block type | Renderer |
|--------|--------|------------|----------|
| `workflow` | sync/stream | `workflow` | WorkflowRenderer |
| `chat` | stream | `markdown` (+ sub-blocks) | MarkdownRenderer |
| `reasoning` | stream | `reasoning` | TypingIndicator |
| `ocr` | sync | `ocr` | OCRRenderer |
| `prediction` | sync | `prediction` | PredictionRenderer |
| `report` | async | `report` | ReportTaskRenderer |
| `chart` | async/sync | `chart` | ChartTaskRenderer |
| `image` | async/sync | `image` | ImageRenderer |
| `structured` | sync | `tool_output` | CodeBlockRenderer |
| `table` | sync | `table` | TableRenderer |
| `code` | sync | `code` | CodeBlockRenderer |
| `calculator` | sync | `markdown` | MarkdownRenderer (via `calculatorDataToMarkdown`) |
| `math` | sync | `markdown` | MarkdownRenderer (via `mathDataToMarkdown`) |
| `interaction` | sync | `interaction` | InteractionRenderer |
| `error` | any | `error` | ErrorRenderer |
| unknown | any | `tool_output` | CodeBlockRenderer (fallback) |

## Full example (multi-tool)

```json
{
  "requestId": "uuid-12345",
  "mode": "async",
  "status": "partial",
  "tools": [
    {
      "toolName": "Intent / Workflow Planner",
      "type": "workflow",
      "mode": "sync",
      "status": "success",
      "data": {
        "intent": "Generate HS report",
        "workflowSteps": ["Extract data", "Predict HS codes", "Generate report"]
      }
    },
    {
      "toolName": "RAG",
      "type": "chat",
      "mode": "stream",
      "status": "success",
      "streamChunks": [
        { "chunk": "HS code 1001", "done": false },
        { "chunk": " is wheat.", "done": true }
      ]
    },
    {
      "toolName": "OCR",
      "type": "ocr",
      "mode": "sync",
      "status": "success",
      "data": { "text": "Invoice 1234: 100 units" }
    },
    {
      "toolName": "HS Prediction",
      "type": "prediction",
      "mode": "sync",
      "status": "success",
      "data": { "hsCode": "1001", "confidence": 0.95, "productName": "Wheat" }
    },
    {
      "toolName": "Future Prediction",
      "type": "prediction",
      "mode": "sync",
      "status": "success",
      "data": { "predictedVolume": 1500, "year": 2026 }
    },
    {
      "toolName": "Report Generation",
      "type": "report",
      "mode": "async",
      "status": "pending",
      "taskId": "task-789"
    },
    {
      "toolName": "Chart Generation",
      "type": "chart",
      "mode": "async",
      "status": "pending",
      "taskId": "task-790"
    },
    {
      "toolName": "Image Generation",
      "type": "image",
      "mode": "async",
      "status": "pending",
      "taskId": "task-791"
    },
    {
      "toolName": "Structured Response Formatter",
      "type": "structured",
      "mode": "sync",
      "status": "success",
      "data": {
        "formattedOutput": {
          "hsCode": "1001",
          "productName": "Wheat",
          "category": "Agriculture"
        }
      }
    }
  ],
  "timestamp": "2026-02-18T12:30:00Z",
  "error": null
}
```

## Marker text format (storage)

Blocks can also be stored as fenced markers:

```
---workflow
{"title":"Generate HS report","steps":[...]}
---

---chart
{"title":"Volume forecast","status":"pending","taskId":"task-790"}
---
```

Or markdown code fences for inline content. See `app/utils/message/blockMarkerSerialization.ts`.

## TypeScript types

- `UnifiedToolResponse` — `app/types/unified.ts`
- `MessageBlock` — `app/types/chat.ts`
- Tool data shapes — `app/types/message.ts` (re-exports)

## Validation

Use `isUnifiedToolResponse(value)` before parsing. Invalid envelopes should produce an `error` block, not crash the UI.
