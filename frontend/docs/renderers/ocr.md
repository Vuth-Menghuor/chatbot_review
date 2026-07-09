# OCR Renderer — Agent Prompt

**Block type:** `ocr`  
**Component:** `app/components/renderers/OCRRenderer.vue`  
**Composable:** `app/composables/renderers/useOCRRenderer.ts`  
**Related:** `app/utils/file/pdfOcr.ts` (client PDF extraction)

---

## Copy-paste prompt

````
Refactor the OCR renderer in Chat-Bot-GDCE (`OCRRenderer.vue`, `useOCRRenderer.ts`). Display extracted document text from API — wire PDF upload path without hardcoding invoice examples.

## Context
- `type: "ocr"` sync tool from backend OCR service.
- Client-side `pdfOcr.ts` can pre-extract; backend should still return same block shape.

## Data contract

```json
{
  "toolName": "OCR",
  "type": "ocr",
  "mode": "sync",
  "status": "success",
  "data": {
    "text": "Invoice 1234: 100 units of wheat",
    "language": "en",
    "confidence": 0.92,
    "pages": 2,
    "fields": {
      "invoiceNumber": "1234",
      "quantity": "100"
    }
  }
}
```

### TypeScript (`OCRData`)
```ts
interface OCRData {
  text: string;
  language?: string;
  confidence?: number;
  pages?: number;
  fields?: Record<string, string>;
}
```

### MessageBlock
```ts
{
  type: 'ocr';
  content: OCRData & ToolResponseEnvelope fields;
}
```

## UX
- Monospace / document-style text panel
- Typewriter reveal of `text` when `animate: true` (`visibleChars` in composable)
- Confidence badge (e.g. 92% accuracy)
- Key-value grid for `fields` (staggered field reveal)
- Copy full text button
- Optional page thumbnails if `meta.pages` / images provided later

## PDF integration (separate task in useChatStreaming)
- On PDF attachment + OCR intent, run `pdfOcr.ts` OR wait for API `ocr` tool
- Do not hardcode in OCRRenderer — only render `block.content`

## Rules
- Skip block if `!data.text`
- i18n: "Copy", "Confidence", "Pages", field labels from API keys (humanize key names generically)

## Files
- `OCRRenderer.vue`, `useOCRRenderer.ts`
- `unifiedToolResponse.ts` → `ocrToBlocks()`
- `app/utils/file/pdfOcr.ts` (wire in streaming, not renderer)

## Acceptance
- [ ] OCR tool JSON renders text + confidence + fields.
- [ ] Copy to clipboard works.
- [ ] Typewriter animation optional via `animate`.
- [ ] Empty text → no block (adapter) / empty state (renderer).
````
