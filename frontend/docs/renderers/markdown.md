# Markdown Renderer — Agent Prompt

**Block types:** `markdown`, `fallback`  
**Component:** `app/components/renderers/MarkdownRenderer.vue`  
**Composable:** `app/composables/renderers/useMarkdownRenderer.ts`

---

## Copy-paste prompt

````
Refactor/implement the Markdown renderer in Chat-Bot-GDCE (`app/components/renderers/MarkdownRenderer.vue`, `useMarkdownRenderer.ts`). Do not hardcode content.

## Context
- Nuxt 4 + Vuetify 4 + Tailwind 4 chatbot.
- Blocks arrive via `UnifiedToolResponse` → `type: "chat"` with `streamChunks` → `MessageBlock.type: "markdown"`.
- Registry: `rendererMap.markdown` and `rendererMap.fallback` in `useRenderer.ts`.

## Data contract

### From unified API (`type: "chat"`, `mode: "stream"`)
```json
{
  "toolName": "RAG",
  "type": "chat",
  "mode": "stream",
  "status": "success",
  "streamChunks": [
    { "chunk": "## Hello\n\n", "done": false },
    { "chunk": "World.", "done": true }
  ]
}
```

### MessageBlock shape
```ts
{
  id: string;
  type: 'markdown';
  content: string;  // accumulated markdown
  isComplete?: boolean;
  meta?: { tool?: ToolResponseEnvelope };
}
```

### Marker format (legacy)
```markdown
Plain markdown or text without fences.
```

## Features to preserve/enhance
- markdown-it rendering + DOMPurify sanitization
- Shiki syntax highlighting inside fenced code (delegate to code blocks via `normalizeRawTextBlocks` split)
- Mermaid diagrams in ```mermaid fences
- Table extraction to dedicated table blocks (if inline tables detected)
- Typewriter effect during streaming (`useTypewriter`, `useChatMessageRenderFlow`)
- Dark mode compatible prose classes

## Streaming
- When `isComplete: false`, append chunks live during SSE.
- `isStreamingVisible('markdown')` should return true in render flow config.

## Rules
- No hardcoded demo text in component.
- All strings via i18n if user-facing (copy button, etc.).
- Props: `block: MessageBlock`, `animate?: boolean`, `animId?: string`.
- Invalid/empty content → render nothing, not an error.

## Files to touch
- `MarkdownRenderer.vue`
- `useMarkdownRenderer.ts`
- `unifiedToolResponse.ts` → `chatToBlocks()` (if stream merge broken)
- `useChatMessageRenderFlow.ts` (streaming visibility)

## Acceptance
- [ ] Streamed chat tool updates markdown live.
- [ ] Mermaid + Shiki still work.
- [ ] Fallback type renders same component safely.
- [ ] No tool-specific branches in ChatMessageRenderer.
````

## Example unified tool

```json
{
  "toolName": "Assistant",
  "type": "chat",
  "mode": "sync",
  "status": "success",
  "data": "# Report\n\nWheat (**HS 1001**) classified with **95%** confidence."
}
```
