# Math Tool — Agent Prompt

**API tool type:** `math` | `latex` | `formula` | `equation`  
**Rendered as:** `markdown` block (ChatGPT-style formula fences)  
**Component:** `app/components/renderers/MarkdownRenderer.vue`  
**Converter:** `app/utils/tool/formulaToMarkdown.ts` → `mathDataToMarkdown()`

---

## Copy-paste prompt

````
Implement and maintain the Math tool path in Chat-Bot-GDCE. There is no dedicated `MathRenderer` or MathJax — math payloads convert to markdown with inline or fenced code (ChatGPT-style). Do not use LaTeX delimiters.

## Context
- Unified API `type: "math"` → `mathToBlocks()` in `unifiedToolResponse.ts`
- Output is always `type: "markdown"` rendered by `MarkdownRenderer`
- `canonicalBlocks.ts` maps `math`, `latex`, `formula`, `equation`, `mathjax` → `markdown`
- Legacy `---math` / `---latex` fences → same markdown via `normalizeRawTextBlocks`
- For LLM-authored answers, prefer `type: "chat"` with markdown (see `lmStudioTeachingPrompt.ts`)

## Formula display rules (IMPORTANT)

NEVER use LaTeX: no `$$...$$`, `$...$`, `\(...\)`, `\[...\]`, `\frac{}`, `\text{}`.

Use ChatGPT-style markdown:
- Short formulas → inline `` `E = mc^2` ``
- Multi-line or long formulas → fenced ` ```text ` block
- Spreadsheet-style → ` ```excel ` block with leading `=`

## Data contract

### Unified API input
```json
{
  "toolName": "Math Formatter",
  "type": "math",
  "mode": "sync",
  "status": "success",
  "data": {
    "latex": "E = mc^2",
    "expression": "E = mc^2"
  }
}
```

### Converted markdown output
Short:
```markdown
`E = mc^2`
```

Long / multiline:
```markdown
```text
Total Price = Net Price × (1 + VAT Rate / 100)
```
```

### Field mapping (`mathDataToMarkdown`)
| API field | Markdown output |
| --------- | --------------- |
| string `data` | inline code if ≤72 chars, else ` ```text ` fence |
| `latex` / `expression` / `formula` / `content` | same as string path |
| strips leading/trailing `$$` if present | plain text only |

### Marker format (legacy)
```
---math
E = mc^2
---
```
or
```
---latex
a / b = c
---
```

## Adapter (implemented)

1. `'math'` in `UnifiedToolType`
2. `case 'math':` → `mathToBlocks()` in `unifiedToolResponse.ts`
3. Row in `TOOL_RESPONSE_MATRIX`: `math: sync → markdown (inline/fenced formulas)`

## Rules
- No `MathRenderer`, no `useMathJax`, no hardcoded equations.
- Empty data → skip block in adapter.
- Shiki highlights fenced `text` / `excel` blocks in markdown.

## Files
- `app/utils/tool/formulaToMarkdown.ts` — `mathDataToMarkdown`, `legacyToolContentToMarkdown`
- `unifiedToolResponse.ts` — `mathToBlocks`
- `canonicalBlocks.ts` — math aliases → `markdown`
- `MarkdownRenderer.vue` — final render
- `lmStudioTeachingPrompt.ts` — LLM guidance

## Acceptance
- [ ] Unified API math tool renders as markdown (inline or fence).
- [ ] Legacy `---math` / `---latex` fences still work.
- [ ] No LaTeX typesetting path remains in the UI.
- [ ] No math-specific branches in `ChatMessageRenderer`.
````
