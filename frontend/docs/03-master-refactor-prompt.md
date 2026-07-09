# Master Refactor Prompt

Copy everything inside the code fence below into Cursor Agent for a full data-driven refactor.

---

````
You are a senior Nuxt 4 / Vue 3 / Vuetify 4 / Tailwind 4 engineer refactoring the existing chatbot SPA at `D:/GDCE-chatbot/Chat-Bot-GDCE`. Do NOT rebuild from scratch. Extend and refactor so every API tool type renders correctly, supports streaming/async, and can ask the user back — without hardcoded tool logic in components or giant system prompts.

## Read first

- `docs/01-architecture-overview.md`
- `docs/02-unified-api-contract.md`
- `app/types/unified.ts`
- `app/utils/tool/unifiedToolResponse.ts`
- `app/utils/tool/toolResponseContract.ts`
- `app/composables/renderers/useRenderer.ts`
- `app/composables/chat/useChatStreaming.ts`
- `app/services/chat-api/chatApiAdapter.ts`

## Hard rules

1. No hardcoded tool UI in `ChatMessageRenderer.vue` — registry only.
2. No 100+ line system prompt in `useChatStreaming.ts` — move to `app/config/lmStudioTeachingPrompt.ts` or remove.
3. No `if (toolName === '...')` in components — use `type` + `mode` + schema config.
4. All parse paths converge on `UnifiedToolResponse` → `MessageBlock[]`.
5. One data-driven registry: `{ type, component, normalizeData, supportsStream, supportsAsync }`.
6. Populate `Message.blocks[]` on every assistant update; sync `content` for localStorage.
7. Vuetify for interactive primitives; Tailwind for layout. i18n for new strings.
8. Minimal diff — refactor in place.

## Pipeline target

```
API → UnifiedToolResponse → unifiedToolsToMessageBlocks() → MessageBlock[]
    → upsertAssistantMessage({ blocks, content })
    → ChatMessageRenderer → rendererMap[type] → component
```

## Goals

### G1 — Canonical data path
- Fix `Message.blocks` usage end-to-end.
- `normalizeRawTextBlocks` = legacy fallback only.

### G2 — Streaming tools
- Incremental block merge during OpenAI SSE.
- Enable `isStreamingVisible()` per registry config for `chat`, `reasoning`, `workflow`, `chart` skeleton.

### G3 — Async lifecycle
- Wire `useAsyncToolTaskPoll.ts` with runtimeConfig.
- chart/report/image: pending → processing → completed.
- Local defer (`local-chart:*`) behind env flag only.

### G4 — Ask-back UI
- Schema-driven interaction blocks (see `docs/06-interactive-ask-back.md`).
- `sendUserReply({ requestId, values })` for continuation.

### G5 — LM Studio teaching layer
- `app/services/chat-api/lmStudioTeachingAdapter.ts`
- Dev mocks: `app/mocks/unifiedResponses/*.json` + `NUXT_PUBLIC_USE_MOCK_API`

### G6 — Renderer registry
- Extend `useRenderer.ts` or `app/config/rendererRegistry.ts`
- New tool = schema + registry entry + component (if new)

### G7 — Tool schemas
- `app/types/toolSchemas/*.ts` with `normalizeToolData(type, data)`

### G8 — File upload → OCR
- Wire `app/utils/file/pdfOcr.ts` into send flow.

### G9 — calculator/math/code/table via envelope
- Extend `unifiedToolResponse.ts` switch cases.

## Phases

1. Types & registry
2. Parse pipeline + slim system prompt
3. Streaming & async polling
4. Interactive ask-back
5. OCR wire-up + cleanup + mocks

## Acceptance criteria

- [ ] Example envelope from `docs/02-unified-api-contract.md` renders all blocks without code changes.
- [ ] New tool = registry + schema only.
- [ ] System prompt < 30 lines or externalized.
- [ ] `ChatMessageRenderer` has no tool-specific branches.
- [ ] SSE updates chat markdown live.
- [ ] Async widgets complete via poll or env-gated local defer.
- [ ] Ask-back form submits continuation.
- [ ] Works with LM Studio + mock fixtures.
- [ ] No TS errors; `/` and `/chat/[id]` load.
- [ ] i18n for new labels.

## Per-renderer work

Use individual prompts in `docs/renderers/*.md` when focusing on one block type.

## Do NOT

- Rebuild in another framework.
- Add a second rendering system.
- Hardcode HS/wheat/invoice examples in components.
- Create extra markdown unless asked.
- Commit secrets.

Start by reading key files, then implement Phase 1 → 5 in order.
````

---

## One-line version

> Refactor Chat-Bot-GDCE: data-driven `UnifiedToolResponse` → `MessageBlock[]` → renderer registry; sync/stream/async tools; incremental SSE; async polling; schema ask-back; LM Studio adapter + mocks; no hardcoding. Reuse `app/components/renderers/*`. Minimal diff.
