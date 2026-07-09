# Workflow Renderer — Agent Prompt

**Block type:** `workflow`  
**Component:** `app/components/renderers/WorkflowRenderer.vue`  
**Composable:** `app/composables/renderers/useWorkflowRenderer.ts`

---

## Copy-paste prompt

````
Refactor the Workflow renderer in Chat-Bot-GDCE (`WorkflowRenderer.vue`, `useWorkflowRenderer.ts`). Visualize multi-step agent pipelines from API data only.

## Context
- Maps `type: "workflow"` tools (Intent / Workflow Planner, etc.).
- Steps can be strings or rich objects with status.

## Data contract

```json
{
  "toolName": "Intent / Workflow Planner",
  "type": "workflow",
  "mode": "sync",
  "status": "success",
  "data": {
    "intent": "Generate HS report",
    "title": "HS Report Pipeline",
    "workflowSteps": [
      "Extract data",
      "Predict HS codes",
      "Generate report"
    ]
  }
}
```

### Rich steps
```json
"workflowSteps": [
  { "label": "Extract data", "status": "complete", "details": "3 pages parsed" },
  { "label": "Predict HS codes", "status": "active" },
  { "label": "Generate report", "status": "pending" }
]
```

### Types (`app/types/renderer.ts`)
```ts
interface WorkflowStep {
  label: string;
  status: 'complete' | 'active' | 'pending' | 'error';
  details?: string;
  timestamp?: string;
}
interface WorkflowData {
  title?: string;
  steps: WorkflowStep[];
}
```

### Normalization (`unifiedToolResponse.ts`)
- String steps → first `active`, rest `pending`
- Title from `data.title ?? data.intent ?? tool.toolName`

## UX
- Vertical stepper with icons (complete ✓, active pulse, pending ○, error ✗)
- Staggered step reveal when `animate: true`
- Optional expand for `details`
- Title header with tool name chip

## Streaming (optional)
- `mode: "stream"` can update step statuses incrementally
- `isStreamingVisible('workflow')` → highlight active step

## Rules
- No hardcoded step labels (HS report, etc.).
- i18n status labels.
- Tailwind + lucide icons; Vuetify only if needed for tooltips.

## Files
- `WorkflowRenderer.vue`, `useWorkflowRenderer.ts`
- `unifiedToolResponse.ts` → `workflowToBlocks()`, `normalizeWorkflowSteps()`

## Acceptance
- [ ] String array steps render with correct default statuses.
- [ ] Rich steps show status icons and details.
- [ ] Title from intent/title/toolName priority works.
- [ ] Animation stagger respects `animate` prop.
````
