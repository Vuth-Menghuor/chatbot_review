# Error Renderer — Agent Prompt

**Block type:** `error`  
**Component:** `app/components/renderers/ErrorRenderer.vue`  
**Composable:** `app/composables/renderers/useErrorRenderer.ts`

---

## Copy-paste prompt

````
Refactor the Error renderer in Chat-Bot-GDCE (`ErrorRenderer.vue`, `useErrorRenderer.ts`, `useFriendlyErrorDisplay`). Handle tool-level and envelope-level errors with retry UX.

## Context
- Tool `status: "error"` → `errorBlock()` in `unifiedToolResponse.ts`
- Top-level `envelope.error` → additional error block appended
- Network/timeout errors from chat streaming may also produce error blocks

## Data contract

### Tool error
```json
{
  "toolName": "Chart Generation",
  "type": "chart",
  "mode": "async",
  "status": "error",
  "taskId": "task-790",
  "error": {
    "code": "CHART_TIMEOUT",
    "message": "Chart generation timed out",
    "detail": "ECharts option was invalid",
    "retryable": true
  }
}
```

### Envelope error
```json
{
  "requestId": "uuid-12345",
  "mode": "sync",
  "status": "error",
  "tools": [],
  "error": {
    "message": "Upstream service unavailable",
    "retryable": true
  }
}
```

### MessageBlock content
```ts
{
  title?: string;
  message: string;
  detail?: string;
  code?: string;
  retryable?: boolean;
  toolName?: string;
}
```

## UX
- Friendly icons by kind: `network`, `timeout`, `rate_limit`, `server`, `generic` (`ErrorDisplayKind`)
- Show `title` (tool name) + `message` + collapsible `detail`
- Retry button when `retryable: true` → emit regenerate / retry async task
- Distinct red/amber styling, dark mode safe
- Do not expose raw stack traces to user unless `detail` provided by API

## Rules
- `useFriendlyErrorDisplay` maps codes/messages to kinds — extend mapping table, not hardcode in template.
- i18n all friendly messages.
- Multiple errors in one response → multiple error blocks OK.

## Files
- `ErrorRenderer.vue`, `useErrorRenderer.ts`
- `unifiedToolResponse.ts` → `errorBlock()`, envelope error append
- `useChatStreaming.ts` (catch → error block)

## Acceptance
- [ ] Tool error renders with retry when retryable.
- [ ] Envelope error renders when tools empty.
- [ ] ErrorDisplayKind picks correct icon/message.
- [ ] detail collapsible for long text.
````
