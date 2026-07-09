# Code Block Renderer — Agent Prompt

**Block type:** `code`  
**Component:** `app/components/renderers/CodeBlockRenderer.vue`  
**Composable:** `app/composables/renderers/useCodeRenderer.ts`

---

## Copy-paste prompt

````
Refactor the Code block renderer in Chat-Bot-GDCE (`CodeBlockRenderer.vue`, `useCodeBlockRenderer`). Data-driven only — no hardcoded snippets.

## Context
- Renders syntax-highlighted code via Shiki.
- Also used for `tool_output` with `meta.language`.
- Split from markdown by `normalizeRawTextBlocks` and `chatToBlocks`.

## Data contract

### Unified API (`type: "code"`)
```json
{
  "toolName": "Code Generator",
  "type": "code",
  "mode": "sync",
  "status": "success",
  "data": {
    "language": "python",
    "code": "def classify(item):\n    return '1001'"
  }
}
```

### MessageBlock
```ts
{
  type: 'code';
  content: string | {
    code?: string;
    content?: string;
    text?: string;
    language?: string;
    lang?: string;
  };
  meta?: { language?: string };
}
```

### Marker format
````
---code
{"language":"typescript","code":"const x = 1;"}
---
````

## Features
- Language detection + aliases (`LANG_ALIASES` in useCodeRenderer)
- Copy to clipboard button
- Line numbers (if existing)
- Icon per language (lucide)
- Dark/light Shiki themes matching app theme

## Adapter task
Add `case 'code':` in `unifiedToolResponse.ts` `toolToBlocks` if missing:
- Map `data.code` / `data.language` → block content
- Set `meta.language`

## Rules
- Accept `code`, `content`, `text` field aliases in normalizer.
- Empty code → skip block.
- i18n: "Copy", "Copied"

## Files
- `CodeBlockRenderer.vue`
- `useCodeRenderer.ts`
- `unifiedToolResponse.ts`
- `canonicalBlocks.ts` (alias `json` → `code`)

## Acceptance
- [ ] API code tool renders highlighted block.
- [ ] Copy works.
- [ ] Language aliases resolve (py → python).
- [ ] Works in dark mode.
````
