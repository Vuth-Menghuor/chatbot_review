"""Phase 3 Test Suite: DAL request construction URL accuracy verification.

Queries the live Trade Query Service's fast /extract-params endpoint to get
parameters, uses the local DALRequestBuilder to simulate the URL construction
(bypassing heavy DB and NLG waits), and validates the parsed query string.
Generates JSON, Log, and CSV reports.
"""

import sys
import json
import csv
import datetime
import urllib.request
import urllib.parse
from pathlib import Path

# Add repository root to path so we can import internal DAL modules
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from services_version2.trade.dal.dal_request_builder import DALRequestBuilder
from services_version2.trade.dal.url_builder import DALUrlBuilder

def check_live_server(url="http://127.0.0.1:8004/health") -> bool:
    """Check if the live Trade Query Service is running."""
    try:
        with urllib.request.urlopen(url, timeout=1.0) as r:
            return r.status == 200
    except Exception:
        return False

def check_url_assertions(expected: dict, query_params: dict) -> list[str]:
    """Custom assertion logic mapping question_bank expectations to query params."""
    mismatches = []
    
    # Helper to retrieve split/cleaned comma-separated parameter values
    def get_param_values(key: str) -> set[str]:
        val_list = query_params.get(key, [])
        if not val_list:
            return set()
        res = set()
        for v in val_list:
            for item in v.split(','):
                item = item.strip().upper()
                if item:
                    res.add(item)
        return res

    filters = query_params.get("filter", [])

    # 1. trade_direction -> FLOW:eq:EX or FLOW:eq:IM
    if "trade_direction" in expected:
        exp_dir = str(expected["trade_direction"]).strip().upper()
        target_filter = f"FLOW:eq:{exp_dir}"
        if target_filter not in filters:
            mismatches.append(f"Expected trade direction filter '{target_filter}', got filters: {filters}")

    # 2. country -> PARTNER_COUNTRY:eq:XX
    if "country" in expected:
        exp_country = str(expected["country"]).strip().upper()
        target_filter = f"PARTNER_COUNTRY:eq:{exp_country}"
        found = False
        for f in filters:
            if f == target_filter or f == f"PARTNER_COUNTRY:in:{exp_country}":
                found = True
                break
        if not found:
            mismatches.append(f"Expected partner country filter '{target_filter}', got filters: {filters}")

    # 3. partner_countries -> PARTNER_COUNTRY:in:XX,YY
    if "partner_countries" in expected:
        exp_list = [str(c).strip().upper() for c in expected["partner_countries"] if c]
        actual_countries = set()
        for f in filters:
            if f.startswith("PARTNER_COUNTRY:in:"):
                actual_countries.update(c.strip().upper() for c in f.split("PARTNER_COUNTRY:in:")[1].split(",") if c.strip())
            elif f.startswith("PARTNER_COUNTRY:eq:"):
                actual_countries.add(f.split("PARTNER_COUNTRY:eq:")[1].strip().upper())
        
        expected_set = set(exp_list)
        if not expected_set.issubset(actual_countries):
            mismatches.append(f"Expected partner countries subset {exp_list}, got actual: {list(actual_countries)}")

    # 4. mode_of_transport -> MODE_OF_TRANSPORT:eq:1 (sea) or 4 (air)
    if "mode_of_transport" in expected:
        exp_mot = expected["mode_of_transport"]
        exp_list = [exp_mot] if isinstance(exp_mot, str) else list(exp_mot)
        exp_list = [str(m).strip().lower() for m in exp_list if m]
        
        code_map = {"air": "4", "sea": "1"}
        exp_codes = {code_map[m] for m in exp_list if m in code_map}
        
        actual_codes = set()
        for f in filters:
            if f.startswith("MODE_OF_TRANSPORT:eq:"):
                actual_codes.add(f.split("MODE_OF_TRANSPORT:eq:")[1].strip())
            elif f.startswith("MODE_OF_TRANSPORT:in:"):
                actual_codes.update(c.strip() for c in f.split("MODE_OF_TRANSPORT:in:")[1].split(",") if c.strip())
        
        if not exp_codes.issubset(actual_codes):
            mismatches.append(f"Expected transport mode codes {list(exp_codes)} for {exp_list}, got actual: {list(actual_codes)}")

    # 5. start_period -> start-period
    if "start_period" in expected:
        exp_val = str(expected["start_period"]).strip()
        act_list = query_params.get("start-period", [])
        act_val = act_list[0].strip() if act_list else None
        if act_val != exp_val:
            mismatches.append(f"Expected start-period '{exp_val}', got '{act_val}'")

    # 6. end_period -> end-period
    if "end_period" in expected:
        exp_val = str(expected["end_period"]).strip()
        act_list = query_params.get("end-period", [])
        act_val = act_list[0].strip() if act_list else None
        if act_val != exp_val:
            mismatches.append(f"Expected end-period '{exp_val}', got '{act_val}'")

    # 7. frequency -> frequency
    if "frequency" in expected:
        exp_val = str(expected["frequency"]).strip().upper()
        act_list = query_params.get("frequency", [])
        act_val = act_list[0].strip().upper() if act_list else None
        if act_val != exp_val:
            mismatches.append(f"Expected frequency '{exp_val}', got '{act_val}'")

    # 8. year -> period (UPDATED TO ALLOW GRANULAR DATES)
    if "year" in expected:
        exp_val = str(expected["year"]).strip()
        act_period = query_params.get("period", [None])[0]
        act_start = query_params.get("start-period", [None])[0]
        
        has_match = False
        if act_period and str(act_period).strip().startswith(exp_val):
            has_match = True
        if act_start and str(act_start).strip().startswith(exp_val):
            has_match = True
            
        if not has_match:
            mismatches.append(f"Expected year '{exp_val}' to be in period/start-period, got period='{act_period}', start-period='{act_start}'")

    # 9. limit -> limit
    if "limit" in expected:
        exp_val = str(expected["limit"]).strip()
        act_list = query_params.get("limit", [])
        act_val = act_list[0].strip() if act_list else None
        if act_val != exp_val:
            mismatches.append(f"Expected limit '{exp_val}', got '{act_val}'")

    # 10. hs_present -> checks if HS Chapter or HS Heading or HS Code filter is present
    if expected.get("hs_present") is True:
        found = False
        for f in filters:
            if any(f.startswith(prefix) for prefix in ["HS_CHAPTER", "HS_HEADING", "HS_CODE"]):
                found = True
                break
        if not found:
            mismatches.append("Expected HS code or chapter filter, but none found in filters")

    # 11. time_range_present -> checks if period, start-period, or end-period is present
    if expected.get("time_range_present") is True:
        has_time = any(k in query_params for k in ["period", "start-period", "end-period"])
        if not has_time:
            mismatches.append("Expected time range parameter (period/start-period/end-period), but none found")

    # 12. group_by_contains_any
    if "group_by_contains_any" in expected:
        expected_options = [str(o).strip().lower() for o in expected["group_by_contains_any"]]
        dim_map = {
            "mode_of_transport": "MODE_OF_TRANSPORT",
            "hs_code": "HS_CHAPTER",
            "partner_country": "PARTNER_COUNTRY",
            "flow": "FLOW",
        }
        exp_dims = set()
        for opt in expected_options:
            if opt in dim_map:
                exp_dims.add(dim_map[opt])
            else:
                exp_dims.add(opt.upper())
                
        actual_dims = get_param_values("dimensions")
        if not (exp_dims & actual_dims):
            mismatches.append(f"Expected group by dimensions (contains any of {list(exp_dims)}), got actual: {list(actual_dims)}")

    # 13. month
    if "month" in expected:
        exp_val = str(expected["month"]).strip()
        act_vals = [query_params.get(k, [None])[0] for k in ["period", "start-period", "end-period"]]
        act_vals = [str(v).strip() for v in act_vals if v]
        if not any(exp_val in v for v in act_vals):
            mismatches.append(f"Expected month '{exp_val}' in time parameters, got actual: {act_vals}")

    # 14. quarter
    if "quarter" in expected:
        exp_val = str(expected["quarter"]).strip()
        act_vals = [query_params.get(k, [None])[0] for k in ["period", "start-period", "end-period"]]
        act_vals = [str(v).strip() for v in act_vals if v]
        if not any(exp_val in v for v in act_vals):
            mismatches.append(f"Expected quarter '{exp_val}' in time parameters, got actual: {act_vals}")

    # 15. semester
    if "semester" in expected:
        exp_val = str(expected["semester"]).strip()
        act_vals = [query_params.get(k, [None])[0] for k in ["period", "start-period", "end-period"]]
        act_vals = [str(v).strip() for v in act_vals if v]
        if not any(exp_val in v for v in act_vals):
            mismatches.append(f"Expected semester '{exp_val}' in time parameters, got actual: {act_vals}")

    # 16. sort_order
    if "sort_order" in expected:
        exp_val = str(expected["sort_order"]).strip().lower()
        act_list = query_params.get("sort", [])
        act_val = act_list[0].strip().lower() if act_list else ""
        if not act_val.endswith(f":{exp_val}"):
            mismatches.append(f"Expected sort order '{exp_val}' (e.g. ending in ':{exp_val}'), got sort param: '{act_val}'")

    return mismatches

def run_dal_url_evaluation():
    # Detect live server
    base_url = "http://127.0.0.1:8004"
    if not check_live_server(f"{base_url}/health"):
        print(f"Error: Live Trade Query Service is not running on {base_url}.")
        print("Please start the server first (e.g., using python app.py or uvicorn).")
        sys.exit(1)

    # Load question bank
    bank_path = Path(__file__).resolve().parent / "question_bank.json"
    if not bank_path.exists():
        print(f"Error: Question bank not found at {bank_path}")
        sys.exit(1)

    with open(bank_path, "r", encoding="utf-8") as f:
        bank = json.load(f)
    questions = bank["questions"]

    print("=" * 80)
    print("GDCE Trade ChatBot: DAL URL Request Construction Accuracy Suite (FAST MODE)")
    print(f"Total Question Bank Cases Loaded: {len(questions)}")
    print("=" * 80)

    results = []
    stats = {} # subintent -> {total, pass, partial, fail, error}

    import time
    for i, item in enumerate(questions, 1):
        qid = item["id"]
        subintent = item["subintent"]
        question_text = item["question"]
        expected = item["expected"]

        # Initialize subintent stats
        if subintent not in stats:
            stats[subintent] = {"total": 0, "PASS": 0, "PARTIAL": 0, "FAIL": 0, "ERROR": 0}
        stats[subintent]["total"] += 1

        print(f"[{i}/{len(questions)}] {qid}: '{question_text}'", flush=True)

        # 1.5 seconds is safe for the LLM extraction without hitting Gemini limits
        time.sleep(1.5)

        # HIT FAST ENDPOINT (/extract-params) instead of /query
        url = f"{base_url}/extract-params"
        body = json.dumps({"question": question_text}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"}
        )

        actual_intent = None
        dal_source_url = None
        query_params = {}
        mismatches = []
        status = "PASS"

        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                
                extracted_params = res_data.get("params", {})
                actual_intent = extracted_params.get("intent")

                if not extracted_params:
                    mismatches.append("Endpoint returned empty parameters")
                    status = "FAIL"
                else:
                    # BUILD DAL URL LOCALLY (Bypasses heavy DB wait and NLG wait)
                    req_builder = DALRequestBuilder()
                    dal_req = req_builder.build_request(actual_intent, extracted_params)
                    
                    url_builder = DALUrlBuilder(base_url="http://127.0.0.1:8000", dataset="trade_volume")
                    dal_source_url = url_builder.build(dal_req)
                    
                    parsed = urllib.parse.urlparse(dal_source_url)
                    query_params = urllib.parse.parse_qs(parsed.query)

                    # Intent check
                    expected_intent = expected.get("intent")
                    if expected_intent and str(expected_intent).strip().lower() != str(actual_intent or "").strip().lower():
                        mismatches.append(f"Intent mismatch: Expected '{expected_intent}', got '{actual_intent}'")
                        status = "FAIL"
                    else:
                        mismatches = check_url_assertions(expected, query_params)
                        status = "PASS" if not mismatches else "PARTIAL"

        except Exception as e:
            status = "ERROR"
            mismatches = [f"HTTP request failed or Validation Error: {e}"]

        stats[subintent][status] += 1
        results.append({
            "id": qid,
            "subintent": subintent,
            "category": item.get("category", ""),
            "question": question_text,
            "notes": item.get("notes", ""),
            "expected": expected,
            "actual_intent": actual_intent,
            "dal_source_url": dal_source_url,
            "query_params": query_params,
            "status": status,
            "mismatches": mismatches
        })

    # Aggregated metrics
    total_cases = len(questions)
    passed_cases = sum(1 for r in results if r["status"] == "PASS")
    overall_accuracy = (passed_cases / total_cases) * 100 if total_cases > 0 else 0

    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    # 1. Save JSON Report
    report_json_path = reports_dir / f"dal_url_accuracy_{timestamp}.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "overall_accuracy": round(overall_accuracy, 1),
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "subintent_stats": stats
        }, f, indent=2)

    # 2. Save detailed Log Report
    report_log_path = reports_dir / f"dal_url_accuracy_{timestamp}.log"
    with open(report_log_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"GDCE TRADE CHATBOT: DAL URL ACCURACY RUN REPORT - {timestamp}\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Overall Accuracy: {round(overall_accuracy, 1)}% ({passed_cases}/{total_cases} passed)\n\n")
        
        f.write("Subintent Breakdown:\n")
        for sub, counts in stats.items():
            pass_rate = (counts["PASS"] / counts["total"] * 100) if counts["total"] > 0 else 0.0
            f.write(f"  - {sub:<15}: {pass_rate:>5.1f}% (PASS: {counts['PASS']}, PARTIAL: {counts['PARTIAL']}, FAIL: {counts['FAIL']}, ERROR: {counts['ERROR']})\n")
        f.write("\n" + "=" * 80 + "\n\n")
        
        f.write("DETAILED MISMATCHES & ERRORS\n")
        f.write("=" * 80 + "\n\n")
        for r in results:
            if r["status"] != "PASS":
                f.write(f"Case #{r['id']}: [{r['status']}] - Question: \"{r['question']}\"\n")
                f.write(f"  Expected Plan: {json.dumps(r['expected'])}\n")
                if r["dal_source_url"]:
                    f.write(f"  Generated URL: {r['dal_source_url']}\n")
                if r["mismatches"]:
                    f.write(f"  Mismatches:\n")
                    for m in r["mismatches"]:
                        f.write(f"    - {m}\n")
                f.write("-" * 80 + "\n\n")

    # 3. Save CSV Report with actual parsed params
    report_csv_path = reports_dir / f"dal_url_accuracy_{timestamp}.csv"
    with open(report_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "subintent", "category", "question", "status", "dal_source_url", "expected_plan", "actual_params", "mismatches", "notes"])
        for r in results:
            writer.writerow([
                r["id"],
                r["subintent"],
                r["category"],
                r["question"],
                r["status"],
                r["dal_source_url"] or "",
                json.dumps(r["expected"]),
                json.dumps(r["query_params"]),
                "; ".join(r["mismatches"]),
                r["notes"]
            ])

    # Console output
    print("\n" + "=" * 78)
    print(f"DAL URL EVALUATION SUMMARY: Overall Accuracy: {round(overall_accuracy, 1)}% ({passed_cases}/{total_cases} passed)")
    print("=" * 78)
    print(f"{'Subintent':<15}{'Total':>7}{'PASS':>7}{'PARTIAL':>9}{'FAIL':>7}{'ERROR':>7}{'PASS%':>9}")
    print("-" * 78)
    for sub, counts in sorted(stats.items(), key=lambda x: x[0]):
        pass_rate = (counts["PASS"] / counts["total"] * 100) if counts["total"] > 0 else 0.0
        print(f"{sub:<15}{counts['total']:>7}{counts['PASS']:>7}{counts['PARTIAL']:>9}{counts['FAIL']:>7}{counts['ERROR']:>7}{pass_rate:>8.1f}%")
    print("-" * 78)
    print(f"Detailed logs saved to: {report_log_path}")
    print(f"CSV report saved to: {report_csv_path}")
    print("=" * 78 + "\n")

if __name__ == "__main__":
    run_dal_url_evaluation()