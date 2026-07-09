# Architecture Overview

## Stack

| Layer | Technology |
|-------|------------|
| Framework | Nuxt 4 (SPA, `ssr: false`) |
| UI | Vue 3 + Vuetify 4 |
| Styling | Tailwind CSS 4 |
| State | Pinia + localStorage |
| Backend (dev) | LM Studio via `/api/lmstudio` proxy |
| Charts | ECharts 6 |
| Formulas | Markdown code fences (ChatGPT-style; no LaTeX) |
| Code highlight | Shiki |
| Diagrams | Mermaid (inside markdown) |

## Data pipeline

```
User message
    ↓
useChat() → useChatStreaming()
    ↓
LM Studio / API (native or OpenAI SSE)
    ↓
chatApiAdapter → UnifiedToolResponse
    ↓
normalizeUnifiedToolResponse() → MessageBlock[]
    ↓
upsertAssistantMessage({ blocks, content })
    ↓
ChatMessageRenderer → rendererMap[type] → Vue component
```

## Design principles

1. **Envelope-first** — API returns `UnifiedToolResponse`; UI never guesses tool shape from free text alone.
2. **Registry-driven** — `rendererMap` in `useRenderer.ts` maps `MessageBlock.type` → component. No `if (type === 'ocr')` in chat shells.
3. **Normalize once** — All parsers converge on `normalizeUnifiedToolResponse` or `normalizeRawAiResponse`.
4. **Marker compatibility** — `content` string uses `---type` fences for localStorage; prefer `Message.blocks[]` in memory.
5. **Vuetify + Tailwind** — Vuetify for inputs/dialogs/progress; Tailwind for layout and dark mode.
6. **i18n** — New user-facing strings via `useI18n()` (en + km).

## MessageBlock types (canonical)

Defined in `app/utils/message/canonicalBlocks.ts`:

`markdown` · `reasoning` · `code` · `table` · `image` · `chart` · `workflow` · `ocr` · `prediction` · `report` · `interaction` · `tool_output` · `error` · `fallback`

API tool types `calculator` / `math` / `latex` / `formula` normalize to `markdown` blocks (see `formulaToMarkdown.ts`).

## Component map

```
app/components/chat/
  ChatMessage.vue          → message list
  ChatAssistant.vue        → assistant bubble + actions
  ChatMessageRenderer.vue  → block loop (registry only)
  ChatInput.vue            → user input + attachments

app/components/renderers/
  MarkdownRenderer.vue
  CodeBlockRenderer.vue
  TableRenderer.vue
  ChartTaskRenderer.vue + EChartsPanel.vue
  WorkflowRenderer.vue
  OCRRenderer.vue
  PredictionRenderer.vue
  ReportTaskRenderer.vue
  ImageRenderer.vue
  InteractionRenderer.vue
  ErrorRenderer.vue

app/composables/renderers/
  rendererRegistry.ts        → data-driven registry config
  useRenderer.ts           → registry + parse API
  use*Renderer.ts          → per-type logic
```

## Streaming modes

| Tool `mode` | Behavior |
|-------------|----------|
| `sync` | Full `data` rendered when response arrives |
| `stream` | `streamChunks[]` merged live into block content |
| `async` | `taskId` + pending UI; poll or local defer until complete |

## What to refactor (current gaps)

- `Message.blocks` not always populated on every legacy path — prefer envelope → blocks.
- Async polling off by default — enable via `NUXT_PUBLIC_ASYNC_TASK_POLL_ENABLED`.
- Interaction ask-back: wire backend continuation contract end-to-end.
- Expand `normalizeToolData` in `app/types/toolSchemas/` as new tools are added.
- Remove remaining hardcoded labels in renderers (use i18n + API `title` / `toolName`).

## File reference

| Concern | Path |
|---------|------|
| Envelope types | `app/types/unified.ts` |
| Block types | `app/types/chat.ts`, `app/types/renderer.ts` |
| Envelope → blocks | `app/utils/tool/unifiedToolResponse.ts` |
| Contract matrix | `app/utils/tool/toolResponseContract.ts` |
| Raw / marker parse | `app/utils/message/normalizeRawTextBlocks.ts` |
| API adapter | `app/services/chat-api/chatApiAdapter.ts` |
| Streaming | `app/composables/chat/useChatStreaming.ts` |
| Async poll | `app/composables/chat/useAsyncToolTaskPoll.ts` |
| LM proxy | `server/api/lmstudio/[...path].ts` |
