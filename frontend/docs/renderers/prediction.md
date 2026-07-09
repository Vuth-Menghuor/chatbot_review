# Prediction Renderer — Agent Prompt

**Block type:** `prediction`  
**Component:** `app/components/renderers/PredictionRenderer.vue`  
**Composable:** `app/composables/renderers/usePredictionRenderer.ts`  
**Helper:** `SourceLink.vue`

---

## Copy-paste prompt

````
Refactor the Prediction renderer in Chat-Bot-GDCE (`PredictionRenderer.vue`, `usePredictionRenderer.ts`). Support HS classification AND generic prediction payloads without hardcoding wheat/1001 examples.

## Context
- Primary use: HS code prediction with confidence, duties, alternatives.
- Also supports generic numeric predictions (`predictedVolume`, `year`) via flexible `data` shape.
- Merges `structured.formattedOutput` from same envelope (`mergeStructuredIntoPrediction`).

## Data contract

### HS prediction
```json
{
  "toolName": "HS Prediction",
  "type": "prediction",
  "mode": "sync",
  "status": "success",
  "data": {
    "hsCode": "1001",
    "productName": "Wheat",
    "category": "Agriculture",
    "confidence": 0.95,
    "reason": "Grain cereal classification",
    "evidence": ["Product description matches Chapter 10"],
    "sourceName": "GDCE Tariff DB",
    "sourceUrl": "https://example.com/hs/1001",
    "importDuty": "5%",
    "alternatives": [
      { "hsCode": "1002", "productName": "Rye", "confidence": 0.3 }
    ]
  }
}
```

### Generic prediction
```json
{
  "toolName": "Future Prediction",
  "type": "prediction",
  "mode": "sync",
  "status": "success",
  "data": {
    "predictedVolume": 1500,
    "year": 2026,
    "confidence": 0.88,
    "label": "Export volume"
  }
}
```

### TypeScript (`Prediction`)
See `app/types/renderer.ts` — extend normalizer for generic key-value display when `hsCode` absent.

## UX
- Confidence ring or bar with count-up animation (`predictionCountUpMs`)
- High confidence styling when > 0.9
- Alternatives as expandable list
- Tax/duty chips if present
- `SourceLink` for `sourceUrl`
- Generic mode: show `label`, primary value, `year`, confidence

## Adapter
- `predictionToBlocks` requires `hsCode` today — **extend** to support generic predictions (render card from arbitrary `data` keys via schema, not hardcode field names).

## Rules
- Structured formatter in same response merges into prediction (no duplicate card).
- i18n all labels ("Confidence", "Alternatives", etc.).
- No wheat/HS-specific strings in component — use `data.productName`, `data.label`.

## Files
- `PredictionRenderer.vue`, `usePredictionRenderer.ts`
- `unifiedToolResponse.ts` → `predictionToBlocks()`, `mergeStructuredIntoPrediction()`
- `SourceLink.vue`

## Acceptance
- [ ] HS prediction example renders fully.
- [ ] Generic volume/year prediction renders without hsCode.
- [ ] Structured merge works (no duplicate structured block).
- [ ] Confidence animation respects `animate` prop.
````
