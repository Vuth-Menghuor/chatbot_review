# Tool Output Renderer — Agent Prompt

**Block types:** `tool_output`, `structured` (via adapter)  
**Component:** `app/components/renderers/CodeBlockRenderer.vue`  
**Adapter:** `structuredToBlocks()`, `fallbackToBlocks()` in `unifiedToolResponse.ts`

---

## Copy-paste prompt

````
Refactor structured/tool output rendering in Chat-Bot-GDCE. Today `type: "structured"` maps to `tool_output` → CodeBlockRenderer with `meta.language: 'json'`. Improve without hardcoding payloads.

## Context
- Fallback for unknown tool types (`fallbackToBlocks`).
- Structured formatter merges into prediction when possible (`pickStructuredPayload`).
- Consider dedicated `StructuredRenderer.vue` for key-value cards vs raw JSON.

## Data contract

### Structured tool
```json
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
    },
    "schema": { "type": "object", "properties": { ... } }
  }
}
```

### MessageBlock (current)
```ts
{
  type: 'tool_output';
  content: string;  // JSON.stringify(formattedOutput)
  meta: { language: 'json', toolName, schema? };
}
```

### Target (optional enhancement)
```ts
{
  type: 'tool_output';
  content: { formattedOutput: Record<string, unknown>, ...envelope };
  meta: { view: 'json' | 'cards', schema? };
}
```

## UX options (pick one via meta/schema, not hardcode)
1. **JSON view** — Shiki-highlighted JSON (current)
2. **Card view** — key-value grid for flat objects
3. **Table view** — if `formattedOutput` is array of objects

## Rules
- If `structured` + prediction in same envelope, merge into prediction (keep existing `mergeStructuredIntoPrediction`).
- Only standalone structured → render tool_output.
- Schema in `meta.schema` drives card labels (data-driven).
- Unknown tools → `fallbackToBlocks` never throws.

## Files
- `unifiedToolResponse.ts` — `structuredToBlocks`, `fallbackToBlocks`
- `CodeBlockRenderer.vue` or new `StructuredRenderer.vue`
- `useRenderer.ts` — register if new component
- `toolResponseContract.ts` — matrix entry

## Acceptance
- [ ] Example structured JSON renders.
- [ ] Merges into prediction when both present (no duplicate UI).
- [ ] Unknown tool type shows readable JSON/text fallback.
- [ ] Optional card view from schema (no HS-specific hardcode).
````
