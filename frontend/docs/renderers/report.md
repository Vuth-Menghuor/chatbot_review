# Report Renderer — Agent Prompt

**Block type:** `report`  
**Component:** `app/components/renderers/ReportTaskRenderer.vue`  
**Composable:** `app/composables/renderers/useReportRenderer.ts`

---

## Copy-paste prompt

````
Refactor the Report task renderer in Chat-Bot-GDCE (`ReportTaskRenderer.vue`, `useReportRenderer.ts`). Handle async report generation lifecycle from API task states.

## Context
- `type: "report"`, `mode: "async"` with `taskId`.
- Poll via `useAsyncToolTaskPoll` when `NUXT_PUBLIC_ASYNC_TASK_POLL_ENABLED=true`.

## Data contract

### Async pending
```json
{
  "toolName": "Report Generation",
  "type": "report",
  "mode": "async",
  "status": "pending",
  "taskId": "task-789"
}
```

### Completed
```json
{
  "toolName": "Report Generation",
  "type": "report",
  "mode": "async",
  "status": "success",
  "taskId": "task-789",
  "data": {
    "title": "HS Classification Report",
    "reportUrl": "https://cdn.example.com/reports/task-789.pdf",
    "fileSize": "2.4 MB",
    "format": "PDF"
  }
}
```

### TypeScript (`ReportTask`)
```ts
interface ReportTask {
  title?: string;
  status?: 'pending' | 'processing' | 'completed' | 'error';
  taskId?: string;
  reportUrl?: string;
  fileSize?: string;
  format?: string;
  error?: string;
}
```

## UX states
| status | UI |
|--------|-----|
| `pending` | Spinner + "Generating report..." |
| `processing` | Progress indicator |
| `completed` | Download/open button, file size, format badge |
| `error` | Error message + retry |

## Behavior
- `openReport()` → `window.open(reportUrl)` when completed
- Map `toolStatus` from envelope via `mapUnifiedToolStatusToTaskWidgetStatus`
- Poll merge updates same block id in message

## Rules
- No hardcoded report URLs or titles.
- i18n all status strings.
- Emit retry/regenerate on error if `retryable`.

## Files
- `ReportTaskRenderer.vue`, `useReportRenderer.ts`
- `unifiedToolResponse.ts` → `reportToBlocks()`
- `useAsyncToolTaskPoll.ts`, `mergePollTaskBlocks.ts`

## Acceptance
- [ ] Pending shows loading UI with taskId (debug optional).
- [ ] Completed shows download with fileSize/format.
- [ ] Poll updates block without full message replace.
- [ ] Error state with message from `data.error` or tool `error`.
````
