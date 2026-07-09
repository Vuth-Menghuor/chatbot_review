# Reasoning Renderer — Agent Prompt

**Block type:** `reasoning`  
**Component:** `app/components/common/TypingIndicator.vue` (via registry)  
**Adapter:** `unifiedToolResponse.ts` → `reasoningToBlocks()`

---

## Copy-paste prompt

````
Implement/refactor the Reasoning block renderer in Chat-Bot-GDCE. Block type `reasoning` maps to `TypingIndicator` in `rendererMap` — enhance or replace with a dedicated collapsible reasoning panel if needed.

## Context
- Chain-of-thought / thinking tokens from API `type: "reasoning"`.
- Should feel like ChatGPT "Thinking..." but can expand to show full reasoning text.

## Data contract

```json
{
  "toolName": "Reasoning",
  "type": "reasoning",
  "mode": "stream",
  "status": "success",
  "streamChunks": [
    { "chunk": "Let me analyze the invoice...", "done": false },
    { "chunk": " HS code likely 1001.", "done": true }
  ]
}
```

### MessageBlock
```ts
{
  type: 'reasoning';
  content: string;  // aggregated reasoning text
  isComplete?: boolean;
}
```

## UX requirements
- Collapsed by default after complete (optional expand).
- Show pulsing indicator while `isComplete: false`.
- Muted styling (not main answer) — Tailwind `text-muted`.
- i18n label: "Thinking...", "Reasoning"
- Auto-hide or minimize when main `chat` blocks arrive (optional).

## Streaming
- Merge `streamChunks` incrementally like chat.
- `isStreamingVisible('reasoning')` → true.

## Rules
- No hardcoded reasoning text.
- Registry entry in `useRenderer.ts` must stay aligned with `blockTypeLabels`.
- Do not block markdown render while reasoning streams.

## Files
- `TypingIndicator.vue` or new `ReasoningRenderer.vue`
- `unifiedToolResponse.ts` → `reasoningToBlocks()`
- `useChatMessageRenderFlow.ts`

## Acceptance
- [ ] Streaming reasoning updates live.
- [ ] Distinct visual from main markdown answer.
- [ ] Accessible (aria-expanded on collapse).
````
