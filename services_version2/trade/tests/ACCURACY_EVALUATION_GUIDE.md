# GDCE Trade ChatBot Accuracy Evaluation Guide

This guide explains how to run, inspect, and maintain the accuracy evaluation suite in:

- `services_version2/trade_query_version2/tests/generate_test_cases.py`
- `services_version2/trade_query_version2/tests/evaluate_accuracy.py`

## What the suite does

The suite validates two layers:

1. Offline pipeline correctness
- Parameter extraction output from the parser
- DAL URL/query construction shape (filters, dimensions, periods, limits, frequency, sorting)

2. Optional online E2E answer validation
- When local services are available, E2E-marked cases are sent through the Orchestrator endpoint
- The final answer text is validated against expected key substrings

Current generated test corpus size: **155 cases** (from `accuracy_test_cases.json`).

## 1) Run the evaluation

From the project root (`GDCE-ChatBot`), run:

```powershell
python services_version2/trade_query_version2/tests/evaluate_accuracy.py
```

The evaluator automatically chooses mode:

### Mode A: Offline local validation
If services are not running on local health endpoints, the evaluator runs only parser/DAL checks.

Health probes used:
- `http://127.0.0.1:8001/health` (Orchestrator)
- `http://127.0.0.1:8004/health` (Trade Query)

### Mode B: Online E2E validation
If both probes are healthy, the evaluator additionally runs E2E answer checks for cases marked with `"e2e": true`.

Typical local startup flow:

```powershell
# Terminal 1
.\service_scripts\start_all_v2.ps1

# Terminal 2
python services_version2/trade_query_version2/tests/evaluate_accuracy.py
```

## 2) Outputs and where to find them

Each run writes artifacts into:

- `services_version2/trade_query_version2/tests/reports/`

Two files are created per run timestamp:

1. Summary JSON
- Filename: `accuracy_YYYY_MM_DD_HHMMSS.json`
- Contains overall and per-attribute accuracy metrics, and per-intent accuracy blocks

Example structure:

```json
{
  "timestamp": "2026_06_02_143000",
  "overall_accuracy": 92.5,
  "total_cases": 155,
  "total_passed": 143,
  "attribute_accuracies": {
    "intent": { "correct": 150, "total": 155, "accuracy": 96.8 },
    "country": { "correct": 148, "total": 150, "accuracy": 98.7 }
  },
  "intent_accuracies": {
    "summary": {
      "total": 23,
      "intent_accuracy": 95.7,
      "parameter_accuracy": 91.3,
      "url_accuracy": 95.7,
      "e2e_accuracy": 100.0
    }
  }
}
```

2. Detailed diagnostics log
- Filename: `run_details_YYYY_MM_DD_HHMMSS.log`
- Includes per-case pass/fail, mismatch diffs, captured internal service logs, and E2E answer diagnostics

For each case you can inspect:
- Extracted vs expected parameters
- Generated DAL URL mismatches
- E2E status and missing expected answer substrings (if E2E case)
- Captured logging output from `services_version2.trade_query_version2`

## 3) Regenerate or update test cases

### Edit cases
Modify test definitions in:

- `services_version2/trade_query_version2/tests/generate_test_cases.py`

Cases are defined in intent-specific lists and support optional flags such as ambiguity and E2E checks.

### Rebuild JSON corpus
After edits, regenerate:

```powershell
python services_version2/trade_query_version2/tests/generate_test_cases.py
```

This rewrites:

- `services_version2/trade_query_version2/tests/accuracy_test_cases.json`

## 4) Common workflow

1. Update case definitions in `generate_test_cases.py`
2. Regenerate `accuracy_test_cases.json`
3. Run `evaluate_accuracy.py`
4. Inspect summary JSON for score trend
5. Inspect detailed log for exact failure causes and parser/DAL diffs

## 5) Notes for prompt/logic iteration

- Use summary JSON for high-level comparison between revisions
- Use detailed log to target fixes in extraction prompts, normalization, and URL builder logic
- Keep E2E expectations in `expected_answer_contains` tight enough to catch regressions, but not overly brittle to harmless wording changes
