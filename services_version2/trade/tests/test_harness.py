"""
Extraction Test Harness for trade_query
========================================

Calls POST {base_url}/extract-params for every question in question_bank.json,
compares the actual extracted params against the hand-written "expected" fields,
and writes out:

  - results_full.json   -> every question with expected, actual (raw), status, mismatches
  - results.csv          -> same thing flattened for spreadsheet review
  - summary printed to stdout -> pass rate per subintent (this is your "weakest subintent" answer)

Usage:
    python test_harness.py --base-url http://localhost:8005
    python test_harness.py --base-url http://localhost:8005 --bank question_bank.json

Notes:
  - Only fields present in a question's "expected" dict are checked. Anything
    not listed there is ignored (it's not "wrong", we just didn't assert on it).
  - Special expected keys (not literal param names):
      "country"             -> matches actual.origin_country OR actual.destination_country
                                OR actual.partner_country (single-country convenience check)
      "partner_countries"   -> set-compared against actual.partner_countries (order-independent)
      "group_by_contains_any" -> passes if actual.group_by contains >=1 of the listed codes
      "hs_present": true    -> passes if actual.hs_code OR actual.hs_chapter is non-null
      "time_range_present": true -> passes if any of year/years/start_period/end_period/period is non-null
  - Status:
      FAIL    -> intent itself is wrong (most severe, check this first)
      PARTIAL -> intent correct, but >=1 other expected field is wrong/missing
      PASS    -> intent correct and all expected fields match
      ERROR   -> the HTTP call itself failed (network/service down/5xx) -- not a scoring result
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import httpx

SPECIAL_KEYS = {"country", "partner_countries", "group_by_contains_any", "hs_present", "time_range_present"}


def _as_set(values: Any) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, (list, tuple, set)):
        return {str(v).strip().upper() for v in values if v is not None}
    return {str(values).strip().upper()}


def check_field(key: str, expected_value: Any, actual: dict[str, Any]) -> tuple[bool, Any]:
    """Returns (passed, actual_value_shown_in_report)."""

    if key == "country":
        candidates = [actual.get("origin_country"), actual.get("destination_country"), actual.get("partner_country")]
        candidates_set = {str(c).strip().upper() for c in candidates if c}
        passed = str(expected_value).strip().upper() in candidates_set
        return passed, candidates

    if key == "partner_countries":
        actual_set = _as_set(actual.get("partner_countries"))
        expected_set = _as_set(expected_value)
        passed = expected_set.issubset(actual_set) and len(actual_set) > 0
        return passed, sorted(actual_set)

    if key == "group_by_contains_any":
        actual_group_by = actual.get("group_by") or []
        actual_group_by_upper = {str(g).strip().upper() for g in actual_group_by}
        expected_options = {str(g).strip().upper() for g in expected_value}
        passed = len(actual_group_by_upper & expected_options) > 0
        return passed, actual_group_by

    if key == "hs_present":
        present = bool(actual.get("hs_code") or actual.get("hs_chapter"))
        return present == bool(expected_value), {"hs_code": actual.get("hs_code"), "hs_chapter": actual.get("hs_chapter")}

    if key == "time_range_present":
        present = any(
            actual.get(k) is not None
            for k in ("year", "years", "start_period", "end_period", "period")
        )
        return present == bool(expected_value), {
            "year": actual.get("year"), "years": actual.get("years"),
            "start_period": actual.get("start_period"), "end_period": actual.get("end_period"),
        }

    # Plain field: direct equality, case-insensitive for strings
    actual_value = actual.get(key)
    if isinstance(expected_value, str) and isinstance(actual_value, str):
        passed = expected_value.strip().upper() == actual_value.strip().upper()
    else:
        passed = expected_value == actual_value
    return passed, actual_value


def evaluate(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Returns (status, mismatches) where mismatches is a list of
    {field, expected, actual} dicts for any field that failed."""

    mismatches: list[dict[str, Any]] = []

    expected_intent = expected.get("intent")
    actual_intent = actual.get("intent")
    if expected_intent and str(expected_intent).strip().lower() != str(actual_intent or "").strip().lower():
        mismatches.append({"field": "intent", "expected": expected_intent, "actual": actual_intent})
        return "FAIL", mismatches

    for key, expected_value in expected.items():
        if key == "intent":
            continue
        passed, actual_shown = check_field(key, expected_value, actual)
        if not passed:
            mismatches.append({"field": key, "expected": expected_value, "actual": actual_shown})

    return ("PASS" if not mismatches else "PARTIAL"), mismatches


def run(base_url: str, bank_path: Path, out_dir: Path) -> None:
    bank = json.loads(bank_path.read_text())
    questions = bank["questions"]

    results: list[dict[str, Any]] = []
    summary: dict[str, dict[str, int]] = {}

    with httpx.Client(timeout=30.0) as client:
        for i, item in enumerate(questions, 1):
            qid = item["id"]
            subintent = item["subintent"]
            question_text = item["question"]
            expected = item["expected"]

            summary.setdefault(subintent, {"PASS": 0, "PARTIAL": 0, "FAIL": 0, "ERROR": 0, "total": 0})
            summary[subintent]["total"] += 1

            print(f"[{i}/{len(questions)}] {qid}: {question_text!r}", flush=True)

            try:
                resp = client.post(f"{base_url.rstrip('/')}/extract-params", json={"question": question_text})
                resp.raise_for_status()
                body = resp.json()
                actual = body.get("params", {})
                status, mismatches = evaluate(expected, actual)
            except Exception as exc:
                actual = {}
                status = "ERROR"
                mismatches = [{"field": "_request", "expected": "200 OK", "actual": str(exc)}]

            summary[subintent][status] += 1

            results.append({
                "id": qid,
                "subintent": subintent,
                "category": item.get("category"),
                "question": question_text,
                "notes": item.get("notes"),
                "expected": expected,
                "actual": actual,
                "status": status,
                "mismatches": mismatches,
            })

    out_dir.mkdir(parents=True, exist_ok=True)

    full_path = out_dir / "results_full.json"
    full_path.write_text(json.dumps(results, indent=2))

    csv_path = out_dir / "results.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "subintent", "category", "question", "status", "expected_json", "actual_json", "mismatches_json", "notes"])
        for r in results:
            writer.writerow([
                r["id"], r["subintent"], r["category"], r["question"], r["status"],
                json.dumps(r["expected"]), json.dumps(r["actual"]), json.dumps(r["mismatches"]),
                r.get("notes") or "",
            ])

    # Save mismatches and errors separately for easy review
    mismatch_path = out_dir / "mismatches.json"
    mismatches = [r for r in results if r["status"] != "PASS"]
    mismatch_path.write_text(json.dumps(mismatches, indent=2))

    txt_path = out_dir / "mismatches.txt"
    with txt_path.open("w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("MISMATCH REPORT (FAILURES, PARTIALS, & ERRORS)\n")
        f.write("=" * 80 + "\n\n")
        if not mismatches:
            f.write("All test cases passed successfully!\n")
        for r in mismatches:
            f.write(f"[{r['status']}] {r['id']}: {r['question']}\n")
            if r.get("notes"):
                f.write(f"  Notes: {r['notes']}\n")
            f.write(f"  Expected: {json.dumps(r['expected'])}\n")
            f.write(f"  Actual:   {json.dumps(r['actual'])}\n")
            f.write("  Mismatches:\n")
            for m in r["mismatches"]:
                f.write(f"    - Field '{m['field']}': Expected: {m['expected']} | Actual: {m['actual']}\n")
            f.write("-" * 80 + "\n\n")

    # Print summary table, sorted weakest-first
    print("\n" + "=" * 78)
    print(f"{'SUBINTENT':<15}{'TOTAL':>7}{'PASS':>7}{'PARTIAL':>9}{'FAIL':>7}{'ERROR':>7}{'PASS%':>9}")
    print("-" * 78)

    rows = []
    for subintent, counts in summary.items():
        total = counts["total"]
        pass_pct = (counts["PASS"] / total * 100) if total else 0.0
        rows.append((subintent, counts, pass_pct))

    rows.sort(key=lambda r: r[2])  # weakest subintent first

    for subintent, counts, pass_pct in rows:
        print(f"{subintent:<15}{counts['total']:>7}{counts['PASS']:>7}{counts['PARTIAL']:>9}{counts['FAIL']:>7}{counts['ERROR']:>7}{pass_pct:>8.1f}%")

    overall_total = sum(c["total"] for c in summary.values())
    overall_pass = sum(c["PASS"] for c in summary.values())
    print("-" * 78)
    print(f"{'OVERALL':<15}{overall_total:>7}{overall_pass:>7}{'':>9}{'':>7}{'':>7}{(overall_pass/overall_total*100 if overall_total else 0):>8.1f}%")
    print("=" * 78)
    print(f"\nWeakest subintent: {rows[0][0]} ({rows[0][2]:.1f}% pass rate)")
    print(f"\nFull results: {full_path}")
    print(f"CSV for spreadsheet review: {csv_path}")
    print(f"Mismatches JSON: {mismatch_path}")
    print(f"Mismatches Text Log: {txt_path}")
    print("\nTip: open mismatches.txt for a quick, readable view of what failed.")


def main():
    parser = argparse.ArgumentParser(description="Run extraction test bank against /extract-params")
    parser.add_argument("--base-url", default="http://localhost:8005", help="Base URL of the trade_query service")
    parser.add_argument("--bank", default="question_bank.json", help="Path to question_bank.json")
    parser.add_argument("--out", default="results", help="Output directory for results")
    args = parser.parse_args()

    bank_path = Path(args.bank)
    if not bank_path.exists():
        print(f"Question bank not found: {bank_path}", file=sys.stderr)
        sys.exit(1)

    run(args.base_url, bank_path, Path(args.out))


if __name__ == "__main__":
    main()
