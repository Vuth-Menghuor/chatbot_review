# Extraction Test Bank — How To Use

## Files
- `question_bank.json` — 105 questions (15 per subintent: summary, ranking, trend, comparison,
  breakdown, growth, trade_balance), each with hand-written expected extraction fields.
- `test_harness.py` — runs every question against your live service's `/extract-params`
  endpoint, compares actual vs expected, and saves results.

## Run it

```bash
# 1. Make sure your trade_query service is running, e.g.:
python -m services_version2.trade.main
# (default port 8005, per config.py)

# 2. In another terminal, run the harness against it:
python test_harness.py --base-url http://localhost:8005
```

This produces a `results/` folder with:
- `results_full.json` — every question with expected, actual, status, and exact mismatches
- `results.csv` — same data, open in Excel/Sheets for easier triage

And prints a summary table to your terminal, sorted **weakest subintent first**:

```
SUBINTENT        TOTAL   PASS  PARTIAL   FAIL  ERROR    PASS%
------------------------------------------------------------------------------
trend               15      6        5      4      0    40.0%
comparison          15      9        4      2      0    60.0%
...
```

## How to read results

- **FAIL** = intent itself was misclassified. Fix this first — everything downstream
  (DAL filters, viz, NLG) is wrong if intent is wrong.
- **PARTIAL** = intent was right, but a parameter is wrong/missing (e.g. year extracted
  but country missed). This is a parameter-extraction bug, not an intent bug.
- **PASS** = matched everything we checked for that question.
- **ERROR** = the HTTP call itself failed (service down, network issue, 5xx) —
  not a scoring result, fix connectivity and re-run.

Open `results.csv`, filter `status != PASS`, and read the `mismatches_json` column —
it tells you the exact field, what was expected, and what actually came back, so you
don't have to re-derive it by eye.

## Important caveats baked into this test bank

1. **Only fields listed in a question's `expected` dict are checked.** If a question's
   expected only has `{"intent": "summary", "year": 2023}`, we don't care what
   `metrics` or `limit` came back — that's intentional, not a gap.

2. **`hs_present: true` checks depend on a live DAL call.** Product-name resolution
   (e.g. "rice" → HS code) happens via `core/product_resolver.py`, which fetches
   metadata from your DAL service at runtime. If DAL is unreachable, these specific
   questions will show PARTIAL/FAIL even if the LLM extraction itself was fine.
   Check `actual.hs_code`/`actual.hs_chapter` in the CSV before assuming it's an
   LLM bug — it might be a DAL connectivity issue instead.

3. **8 questions are deliberately adversarial** (marked `category: adversarial` with
   a `notes` field explaining the ambiguity) — they're designed to trip the
   intent-confusion pairs called out in your `SYSTEM_INSTRUCTION` prompt
   (trend vs growth, comparison vs trade_balance, ranking vs comparison, etc).
   If these fail, it tells you exactly which prompt rule the LLM isn't following.

4. **Current year is assumed to be 2026** for relative date questions ("last year" →
   2025, "this year" → 2026). If you run this after that's no longer true, update
   those `expected.year` values in `question_bank.json`.

## Next steps after running

1. Sort by the printed summary table — start with the lowest PASS% subintent.
2. In `results.csv`, filter that subintent + `status == FAIL` first (intent
   misclassification — highest leverage fix, usually means a `SYSTEM_INSTRUCTION`
   prompt tweak in `core/llm_extractor.py`).
3. Then filter `status == PARTIAL` for that subintent — these are parameter-level
   bugs, often in `core/enrichment.py` (synonym/value resolution) or the regex
   fallbacks in `llm_extractor.py`.
4. Fix, re-run the **whole bank** (not just the one question) to make sure you
   didn't regress another subintent, and watch the weakest-subintent ranking move.
5. Once `/extract-params` is solid (say 90%+ PASS across the board), build the
   same kind of question bank + harness for Stage 4 (DAL request/filters built)
   and Stage 6 (NLG message vs facts) — same method, different endpoint/comparison.
