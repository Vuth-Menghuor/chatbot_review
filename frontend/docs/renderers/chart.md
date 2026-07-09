# Chart Renderer — Agent Prompt

**Block type:** `chart`  
**Components:** `ChartTaskRenderer.vue`, `EChartsPanel.vue`  
**Composable:** `app/composables/renderers/useChartRenderer.ts`  
**Utils:** `app/utils/chart/*` (16 chart kinds)

---

## Copy-paste prompt

````
Refactor the Chart renderer in Chat-Bot-GDCE (`ChartTaskRenderer.vue`, `EChartsPanel.vue`, `useChartRenderer.ts`). Support sync, async, and local-defer modes without hardcoded chart data.

## Context
- ECharts 6 via builders in `app/utils/chart/`.
- Async tools use `taskId` + pending/processing/completed states.
- Local demo: `local-chart:*` task ids (env-gated defer in `localAsyncChartTasks.ts`).

## Data contract

### Async pending
```json
{
  "toolName": "Chart Generation",
  "type": "chart",
  "mode": "async",
  "status": "pending",
  "taskId": "task-790"
}
```

### Sync / completed
```json
{
  "toolName": "Chart Generation",
  "type": "chart",
  "mode": "sync",
  "status": "success",
  "data": {
    "title": "Export Volume Forecast",
    "chartType": "bar",
    "output": {
      "xKey": "year",
      "yLabel": "Volume (tons)",
      "data": [
        { "year": 2024, "volume": 1200 },
        { "year": 2025, "volume": 1350 },
        { "year": 2026, "volume": 1500 }
      ],
      "series": [
        { "key": "volume", "name": "Volume", "color": "#6366f1" }
      ]
    }
  }
}
```

### Alternative: raw ECharts option
```json
"data": {
  "echartsOption": { "xAxis": {}, "yAxis": {}, "series": [] }
}
```

### Chart kinds supported
`line`, `bar`, `horizontal-bar`, `area`, `pie`, `donut`, `scatter`, `radar`, `heatmap`, `treemap`, `funnel`, `gauge`, `candlestick`, `sankey`, `graph`, `sunburst`

### MessageBlock content
```ts
{
  title?: string;
  chartType?: ChartKind;
  output?: ChartOutput;
  echartsOption?: Record<string, unknown>;
  status: 'pending' | 'processing' | 'completed' | 'error';
  taskId?: string;
  toolName?: string;
}
```

## UX
- Skeleton/spinner while `status: pending | processing`
- Error state with retry → `regenerate` emit
- Responsive chart resize (`ResizeObserver`)
- Title + tool name chip
- Poll completion via `useAsyncToolTaskPoll` when enabled

## Rules
- `useChartRenderer` builds options from `output` — do not hardcode series in Vue SFC.
- `prepareSyncChartToolForDeferredRender` only when env allows demo defer.
- `isStreamingVisible('chart')` → skeleton during stream.

## Files
- `ChartTaskRenderer.vue`, `EChartsPanel.vue`, `useChartRenderer.ts`
- `unifiedToolResponse.ts` → `chartToBlocks()`
- `app/utils/chart/*`
- `useAsyncToolTaskPoll.ts`, `mergePollTaskBlocks.ts`

## Acceptance
- [ ] Pending async chart shows loading UI.
- [ ] Completed chart renders correct ECharts type from `chartType`.
- [ ] `echartsOption` passthrough works.
- [ ] Poll merge updates block in place.
- [ ] 16 chart kinds route through builders (no one-off in component).
````
