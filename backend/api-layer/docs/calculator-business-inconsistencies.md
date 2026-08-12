# Calculator Upstream Business Inconsistencies

The API layer treats calculator payloads as external upstream responses. It must not correct calculator terminology, formulas, totals, rankings, or conclusions.

## Regression Fixture

Fixture:

```text
backend/api-layer/tests/fixtures/service_responses/calculator_business_inconsistency.json
```

Observed upstream-style inconsistency:

- `answer` says the majority tax component is `Special Tax (SPP)`.
- `calculator_result.tax_breakdown[0].tax_component` is `Special Tariff (SOP)`.

## API-Layer Behavior

- Preserve the upstream `answer` unchanged in `response.content`.
- Preserve structured fields unchanged in `message.content` blocks.
- Do not rewrite `SPP` to `SOP`, or `SOP` to `SPP`.
- Do not recalculate totals or determine the largest tax component.
- Emit a development-only warning log for service-team investigation.

## Services-Team Follow-Up

The calculator service should define the official terminology and business conclusion. Once the upstream service updates the response, the API layer will pass through the updated values.
