# Table Renderer — Agent Prompt

**Block type:** `table`  
**Component:** `app/components/renderers/TableRenderer.vue`  
**Composable:** `app/composables/renderers/useTableRenderer.ts`

---

## Copy-paste prompt

````
Implement/refactor the Table renderer in Chat-Bot-GDCE (`TableRenderer.vue`, `useTableRenderer.ts`). Data-driven columns and rows — no hardcoded HS tables.

## Context
- Tables can come from unified API, markdown extraction, or marker fences.
- Helper: `TableMathInline.vue` for math in cells.

## Data contract

### Unified API (`type: "table"`)
```json
{
  "toolName": "Data Table",
  "type": "table",
  "mode": "sync",
  "status": "success",
  "data": {
    "columns": [
      { "key": "hsCode", "title": "HS Code" },
      { "key": "product", "title": "Product" },
      { "key": "confidence", "title": "Confidence" }
    ],
    "rows": [
      { "hsCode": "1001", "product": "Wheat", "confidence": "95%" },
      { "hsCode": "1002", "product": "Rye", "confidence": "72%" }
    ]
  }
}
```

### TypeScript (`app/types/renderer.ts`)
```ts
interface TableData {
  columns: { key: string; title: string }[];
  rows: Record<string, unknown>[];
}
```

### Marker format
```
---table
{"columns":[...],"rows":[...]}
---
```

## Adapter task
Add `case 'table':` in `unifiedToolResponse.ts` if missing.

## UX
- Horizontal scroll on mobile (`overflow-x-auto`)
- Staggered row reveal when `animate: true`
- Sortable headers (optional, config-driven)
- Empty state when `rows.length === 0`
- Math in cells → `TableMathInline` + `MathRenderer`

## Rules
- Derive columns from first row keys if `columns` omitted (normalize function).
- i18n empty state message.
- Vuetify `v-table` or native table with Tailwind — match existing style.

## Files
- `TableRenderer.vue`, `useTableRenderer.ts`
- `unifiedToolResponse.ts`
- `useMarkdownRenderer.ts` (table token extraction)

## Acceptance
- [ ] API table tool renders correctly.
- [ ] Responsive scroll on narrow screens.
- [ ] Stagger animation respects `animate` prop.
- [ ] No hardcoded column names.
````
