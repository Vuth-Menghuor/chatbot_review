# Renderer Registry

How block types resolve to Vue components — the single extension point for new UI.

## Current registry

Source: `app/config/rendererRegistry.ts` (consumed by `app/composables/renderers/useRenderer.ts`)


| Block type    | Component          | Composable            |
| ------------- | ------------------ | --------------------- |
| `markdown`    | MarkdownRenderer   | useMarkdownRenderer   |
| `fallback`    | MarkdownRenderer   | useMarkdownRenderer   |
| `reasoning`   | TypingIndicator    | —                     |
| `table`       | TableRenderer      | useTableRenderer      |
| `chart`       | ChartTaskRenderer  | useChartRenderer      |
| `workflow`    | WorkflowRenderer   | useWorkflowRenderer   |
| `image`       | ImageRenderer      | useImageRenderer      |
| `ocr`         | OCRRenderer        | useOCRRenderer        |
| `prediction`  | PredictionRenderer | usePredictionRenderer |
| `report`      | ReportTaskRenderer | useReportRenderer     |
| `interaction` | InteractionRenderer | normalizeToolData    |
| `code`        | CodeBlockRenderer  | useCodeBlockRenderer  |
| `tool_output` | CodeBlockRenderer  | useCodeBlockRenderer  |
| `error`       | ErrorRenderer      | useErrorRenderer      |


## Resolution flow

```ts
// ChatMessageRenderer.vue (conceptual)
const { resolveRenderer } = useRenderer();
const component = resolveRenderer(block.type); // canonicalizeBlockType inside
```

```ts
export function resolveRenderer(type: string): Component {
  const canonical = canonicalizeBlockType(type);
  return rendererMap[canonical] ?? rendererMap.fallback;
}
```

## Type aliases

`app/utils/message/canonicalBlocks.ts` maps legacy names:


| Alias                 | Canonical     |
| --------------------- | ------------- |
| `text`, `md`          | `markdown`    |
| `thinking`, `reason`  | `reasoning`   |
| `json`, `snippet`     | `code`        |
| `chart_task`, `graph` | `chart`       |
| `report_task`         | `report`      |
| `structured`, `tool`  | `tool_output` |
| `steps`, `guide`      | `workflow`    |
| `latex`, `formula`, `equation`, `mathjax` | `markdown` |
| `calculator`, `calc`  | `markdown`    |


## Adding a new renderer

1. Add canonical type to `CANONICAL_BLOCK_TYPES` (if new).
2. Add Vue component under `app/components/renderers/`.
3. Add composable under `app/composables/renderers/` (if logic is non-trivial).
4. Register in `rendererMap` + `blockTypeLabels`.
5. Add `toolToBlocks` case in `unifiedToolResponse.ts`.
6. Add row to `TOOL_RESPONSE_MATRIX` in `toolResponseContract.ts`.
7. Add schema in `app/types/toolSchemas/` (recommended).
8. Add doc + agent prompt in `docs/renderers/`.
9. Add mock fixture in `app/mocks/unifiedResponses/`.

## Registry config (target shape)

Refactor toward a single config object:

```ts
interface RendererDefinition {
  component: Component;
  label: string;
  normalizeContent?: (raw: unknown) => unknown;
  supportsStream?: boolean;
  supportsAsync?: boolean;
  streamVisible?: boolean;
  defaultAnimate?: boolean;
}
```

## Invariants

- `rendererMap` keys must match `blockTypeLabels` keys (enforced at module load in dev).
- Components receive `block: MessageBlock` and optional `animate`, `animId` props.
- Never import omponents dirrenderer cectly in `ChatMessageRenderer` — always via registry.

## Tool envelope on content

Async/sync tools merge metadata into `block.content`:

```ts
{
  toolName: string;
  type: string;
  mode: 'sync' | 'stream' | 'async';
  toolStatus: ToolStatus;
  status: 'pending' | 'processing' | 'completed' | 'error';
  taskId?: string;
  // ... payload fields
}
```

See `toolEnvelopeContentFields()` in `toolResponseContract.ts`.