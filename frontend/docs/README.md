# GDCE Chatbot — Documentation

Documentation for the **Chat-Bot-GDCE** rich multi-tool chatbot UI (Nuxt 4 + Vuetify 4 + Tailwind 4 + LM Studio).

## Quick links

| Doc | Description |
|-----|-------------|
| [Architecture overview](./01-architecture-overview.md) | End-to-end pipeline, file map, design rules |
| [Unified API contract](./02-unified-api-contract.md) | `UnifiedToolResponse` envelope, tool types, examples |
| [Master refactor prompt](./03-master-refactor-prompt.md) | Full agent prompt to refactor the whole system |
| [Renderer registry](./04-renderer-registry.md) | How blocks map to components (no hardcoding) |
| [LM Studio & backend setup](./05-lm-studio-backend.md) | Env vars, transports, mocks, async polling |
| [Interactive ask-back UI](./06-interactive-ask-back.md) | Schema-driven forms that ask the user back |
| [API Layer health & Bruno](./07-api-layer-health-and-bruno.md) | Health endpoints, readiness behavior, Bruno requests |

## Per-renderer prompts

Copy any file below into Cursor Agent when working on that renderer only.

| Renderer | Block type(s) | Prompt file |
|----------|---------------|-------------|
| Markdown | `markdown`, `fallback` | [renderers/markdown.md](./renderers/markdown.md) |
| Reasoning | `reasoning` | [renderers/reasoning.md](./renderers/reasoning.md) |
| Code | `code` | [renderers/code.md](./renderers/code.md) |
| Tool output | `tool_output`, `structured` | [renderers/tool-output.md](./renderers/tool-output.md) |
| Table | `table` | [renderers/table.md](./renderers/table.md) |
| Chart | `chart` | [renderers/chart.md](./renderers/chart.md) |
| Workflow | `workflow` | [renderers/workflow.md](./renderers/workflow.md) |
| OCR | `ocr` | [renderers/ocr.md](./renderers/ocr.md) |
| Prediction | `prediction` | [renderers/prediction.md](./renderers/prediction.md) |
| Report | `report` | [renderers/report.md](./renderers/report.md) |
| Image | `image` | [renderers/image.md](./renderers/image.md) |
| Calculator | `summary`, `key_value`, `table`, `details`, `references`, `markdown` fallback | [renderers/calculator.md](./renderers/calculator.md) |
| Math (→ markdown) | `math`, `latex`, `formula` | [renderers/math.md](./renderers/math.md) |
| Error | `error` | [renderers/error.md](./renderers/error.md) |
| Interaction (planned) | `interaction` | [renderers/interaction.md](./renderers/interaction.md) |

## Recommended workflow

1. Read **01** and **02** to understand the contract.
2. Run **03** (master prompt) for a full data-driven refactor.
3. Use individual **renderers/*.md** prompts for focused work on one block type.
4. Use **05** when wiring LM Studio or a real backend.
5. Use **06** when adding ask-back / confirmation UI.

## Key source files (repo)

```
app/types/unified.ts
app/utils/tool/unifiedToolResponse.ts
app/utils/tool/toolResponseContract.ts
app/composables/renderers/useRenderer.ts
app/composables/chat/useChatStreaming.ts
app/components/renderers/*
app/services/chat-api/chatApiAdapter.ts
server/api/lmstudio/[...path].ts
```
