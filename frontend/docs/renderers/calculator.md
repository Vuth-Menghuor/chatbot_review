# Calculator Tool — Agent Prompt

**API tool type:** `calculator`  
**Rendered as:** `markdown` block (ChatGPT-style formula fences)  
**Component:** `app/components/renderers/MarkdownRenderer.vue`  
**Converter:** `app/utils/tool/formulaToMarkdown.ts` → `calculatorDataToMarkdown()`

---

## Copy-paste prompt

````
Implement and maintain the Calculator tool path in Chat-Bot-GDCE. There is no dedicated `CalculatorRenderer` — calculator payloads convert to markdown with highlighted formula code blocks (ChatGPT-style). Do not use LaTeX or MathJax.

## Context
- Unified API `type: "calculator"` → `calculatorToBlocks()` in `unifiedToolResponse.ts`
- Output is always `type: "markdown"` rendered by `MarkdownRenderer`
- `canonicalBlocks.ts` maps `calculator` / `calc` → `markdown`
- Legacy `---calculator` fences in raw text → same markdown via `normalizeRawTextBlocks` + `legacyToolContentToMarkdown`
- For LLM-authored answers, prefer `type: "chat"` with markdown (see `lmStudioTeachingPrompt.ts`) — calculator tool is for structured API payloads

## Formula display rules (IMPORTANT)

NEVER use LaTeX delimiters (`$$...$$`, `$...$`, `\(...\)`, `\[...\]`, `\frac{}`, `\text{}`). The UI does not typeset LaTeX.

Use ChatGPT-style markdown instead:
- Spreadsheet / numeric expressions → fenced ` ```excel ` block
- General formulas → fenced ` ```text ` block or inline `` `backticks` ``
- Step values → inline `` `backticks` `` on each formula line
- Plain Unicode math symbols are fine: `×`, `÷`, `%`, `=`

BAD:
```
CIF \times duty\_rate
$$50 = 1000 \times 0.05$$
```

GOOD:
```text
CIF × duty_rate
```
```excel
=1000 * 0.05
```
- **Duty:** `1000 × 0.05 = 50 USD`

## Data contract

### Unified API input
```json
{
  "toolName": "Duty Calculator",
  "type": "calculator",
  "mode": "sync",
  "status": "success",
  "data": {
    "title": "Import duty calculation",
    "expression": "=1000 * 0.05",
    "result": 50,
    "currency": "USD",
    "formula": "CIF × duty_rate",
    "steps": [
      { "label": "CIF value", "value": "1000 USD" },
      { "label": "Duty rate", "value": "5%" },
      { "label": "Duty", "value": "50 USD", "note": "1000 × 0.05" }
    ],
    "note": "Rates apply to HS Chapter 10 goods."
  }
}
```

### Converted markdown output (what the user sees)
```markdown
### Import duty calculation

**Expression**
```excel
=1000 * 0.05
```

**Formula**
```text
CIF × duty_rate
```

**Result:** 50 USD

**Steps**
- **CIF value:** `1000 USD`
- **Duty rate:** `5%`
- **Duty:** `50 USD` — 1000 × 0.05

**Note**

Rates apply to HS Chapter 10 goods.
```

### Field mapping (`calculatorDataToMarkdown`)
| API field | Markdown output |
| --------- | --------------- |
| `title` / `name` | `###` heading |
| `description` | plain paragraph |
| `expression` | `**Expression**` + ` ```excel ` fence |
| `formula` | `**Formula**` + ` ```text ` fence (skipped if same as expression) |
| `result` + `currency` / `unit` | `**Result:**` line |
| `steps` (string[]) | bullet with inline code |
| `steps` (objects) | `- **label:** \`value\`` with optional ` — note` |
| `note` | `**Note**` + paragraph |

### Steps aliases
- Steps can be strings or objects: `{ label, value, note }` (also `title`, `expression`)
- Empty / missing sections are omitted from output

### Marker format (legacy)
```
---calculator
{"expression":"=2+2","result":4,"steps":["2+2=4"]}
---
```
Parsed JSON is passed through `calculatorDataToMarkdown()` → `markdown` block.

## Adapter (implemented)

1. `'calculator'` in `UnifiedToolType` (`app/types/unified.ts`)
2. `case 'calculator':` → `calculatorToBlocks()` in `unifiedToolResponse.ts`
3. Row in `TOOL_RESPONSE_MATRIX`: `calculator: sync → markdown (formula code blocks)`
4. `hasCalculatorPayload()` gates empty tool responses

## Rules
- No hardcoded expressions or results in components.
- No `CalculatorRenderer`, no MathJax, no tabbed UI.
- `expression` values should include leading `=` when they are spreadsheet formulas.
- Empty data → skip block in adapter.
- Shiki highlights `excel` and `text` fences inside `MarkdownRenderer`.

## Files
- `app/utils/tool/formulaToMarkdown.ts` — `calculatorDataToMarkdown`, `legacyToolContentToMarkdown`
- `unifiedToolResponse.ts` — `calculatorToBlocks`, `hasCalculatorPayload`
- `canonicalBlocks.ts` — `calculator` / `calc` → `markdown`
- `normalizeRawTextBlocks.ts` — `---calculator` fence handling
- `MarkdownRenderer.vue` — renders final markdown
- `lmStudioTeachingPrompt.ts` — LLM guidance for ChatGPT-style formulas

## Acceptance
- [ ] Unified API calculator tool renders as markdown with excel/text fences.
- [ ] Steps show inline-highlighted formulas (backticks), not LaTeX.
- [ ] Marker fence `---calculator` still converts to markdown.
- [ ] No calculator-specific branches in `ChatMessageRenderer`.
- [ ] Raw LaTeX in formula fields is not introduced by the converter (plain text only).
````
