"""
Retest Failures Script
Automatically finds the latest DAL URL accuracy CSV report, 
extracts any questions that did not PASS, and re-runs them.
"""

import sys
import json
import csv
import urllib.request
import urllib.parse
from pathlib import Path

# Add repository root to path so we can import internal DAL modules
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

from services_version2.trade.dal.dal_request_builder import DALRequestBuilder
from services_version2.trade.dal.url_builder import DALUrlBuilder

def check_live_server(url="http://127.0.0.1:8004/health") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as r:
            return r.status == 200
    except Exception:
        return False

def check_url_assertions(expected: dict, query_params: dict) -> list[str]:
    mismatches = []
    
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

    if "trade_direction" in expected:
        exp_dir = str(expected["trade_direction"]).strip().upper()
        target_filter = f"FLOW:eq:{exp_dir}"
        if target_filter not in filters:
            mismatches.append(f"Expected trade direction filter '{target_filter}', got filters: {filters}")

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

    if "start_period" in expected:
        exp_val = str(expected["start_period"]).strip()
        act_list = query_params.get("start-period", [])
        act_val = act_list[0].strip() if act_list else None
        if act_val != exp_val:
            mismatches.append(f"Expected start-period '{exp_val}', got '{act_val}'")

    if "end_period" in expected:
        exp_val = str(expected["end_period"]).strip()
        act_list = query_params.get("end-period", [])
        act_val = act_list[0].strip() if act_list else None
        if act_val != exp_val:
            mismatches.append(f"Expected end-period '{exp_val}', got '{act_val}'")

    if "frequency" in expected:
        exp_val = str(expected["frequency"]).strip().upper()
        act_list = query_params.get("frequency", [])
        act_val = act_list[0].strip().upper() if act_list else None
        if act_val != exp_val:
            mismatches.append(f"Expected frequency '{exp_val}', got '{act_val}'")

    # year -> period (UPDATED TO ALLOW GRANULAR DATES)
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

    if "limit" in expected:
        exp_val = str(expected["limit"]).strip()
        act_list = query_params.get("limit", [])
        act_val = act_list[0].strip() if act_list else None
        if act_val != exp_val:
            mismatches.append(f"Expected limit '{exp_val}', got '{act_val}'")

    if expected.get("hs_present") is True:
        found = False
        for f in filters:
            if any(f.startswith(prefix) for prefix in ["HS_CHAPTER", "HS_HEADING", "HS_CODE"]):
                found = True
                break
        if not found:
            mismatches.append("Expected HS code or chapter filter, but none found in filters")

    if expected.get("time_range_present") is True:
        has_time = any(k in query_params for k in ["period", "start-period", "end-period"])
        if not has_time:
            mismatches.append("Expected time range parameter (period/start-period/end-period), but none found")

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

    if "month" in expected:
        exp_val = str(expected["month"]).strip()
        act_vals = [query_params.get(k, [None])[0] for k in ["period", "start-period", "end-period"]]
        act_vals = [str(v).strip() for v in act_vals if v]
        if not any(exp_val in v for v in act_vals):
            mismatches.append(f"Expected month '{exp_val}' in time parameters, got actual: {act_vals}")

    if "quarter" in expected:
        exp_val = str(expected["quarter"]).strip()
        act_vals = [query_params.get(k, [None])[0] for k in ["period", "start-period", "end-period"]]
        act_vals = [str(v).strip() for v in act_vals if v]
        if not any(exp_val in v for v in act_vals):
            mismatches.append(f"Expected quarter '{exp_val}' in time parameters, got actual: {act_vals}")

    if "semester" in expected:
        exp_val = str(expected["semester"]).strip()
        act_vals = [query_params.get(k, [None])[0] for k in ["period", "start-period", "end-period"]]
        act_vals = [str(v).strip() for v in act_vals if v]
        if not any(exp_val in v for v in act_vals):
            mismatches.append(f"Expected semester '{exp_val}' in time parameters, got actual: {act_vals}")

    if "sort_order" in expected:
        exp_val = str(expected["sort_order"]).strip().lower()
        act_list = query_params.get("sort", [])
        act_val = act_list[0].strip().lower() if act_list else ""
        if not act_val.endswith(f":{exp_val}"):
            mismatches.append(f"Expected sort order '{exp_val}' (e.g. ending in ':{exp_val}'), got sort param: '{act_val}'")

    return mismatches

def run_retest():
    # 1. Detect live server
    base_url = "http://127.0.0.1:8004"
    if not check_live_server(f"{base_url}/health"):
        print(f"Error: Live Trade Query Service is not running on {base_url}.")
        sys.exit(1)

    # 2. Find the latest CSV report to grab failed IDs
    reports_dir = Path(__file__).parent / "reports"
    csv_files = list(reports_dir.glob("dal_url_accuracy_*.csv"))
    
    if not csv_files:
        print("Error: No CSV reports found in tests/reports/")
        sys.exit(1)
        
    latest_csv = max(csv_files, key=lambda p: p.stat().st_mtime)
    print(f"Reading target IDs from latest report: {latest_csv.name}")

    failed_ids = set()
    with open(latest_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Grab anything that isn't a PASS
            if row["status"] in ["FAIL", "ERROR", "PARTIAL"]:
                failed_ids.add(row["id"])

    if not failed_ids:
        print("\n✅ WOW! Your last run was perfectly clean (100%). There are no failed cases to re-test.")
        sys.exit(0)

    # 3. Load question bank and filter to only failed IDs
    bank_path = Path(__file__).resolve().parent / "question_bank.json"
    with open(bank_path, "r", encoding="utf-8") as f:
        bank = json.load(f)
    
    target_questions = [q for q in bank["questions"] if q["id"] in failed_ids]

    print("=" * 80)
    print(f"GDCE Trade ChatBot: Retesting {len(target_questions)} Failed Cases")
    print("=" * 80)

    results = []
    import time
    import datetime
    for i, item in enumerate(target_questions, 1):
        qid = item["id"]
        subintent = item["subintent"]
        question_text = item["question"]
        expected = item["expected"]
        notes = item.get("notes", "")

        print(f"\n[{i}/{len(target_questions)}] Retesting {qid}: '{question_text}'")

        # Delay to avoid rate limiting
        time.sleep(1.5)

        url = f"{base_url}/extract-params"
        body = json.dumps({"question": question_text}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"}
        )

        actual_intent = None
        dal_source_url = None
        mismatches = []
        status = "PASS"

        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                
                extracted_params = res_data.get("params", {})
                actual_intent = extracted_params.get("intent")

                if not extracted_params:
                    status = "FAIL"
                    mismatches.append("Endpoint returned empty parameters")
                    print("  ❌ [FAIL] Endpoint returned empty parameters")
                else:
                    # Build DAL URL
                    req_builder = DALRequestBuilder()
                    dal_req = req_builder.build_request(actual_intent, extracted_params)
                    
                    url_builder = DALUrlBuilder(base_url="http://127.0.0.1:8000", dataset="trade_volume")
                    dal_source_url = url_builder.build(dal_req)
                    
                    parsed = urllib.parse.urlparse(dal_source_url)
                    query_params = urllib.parse.parse_qs(parsed.query)

                    # Intent check
                    expected_intent = expected.get("intent")
                    if expected_intent and str(expected_intent).strip().lower() != str(actual_intent or "").strip().lower():
                        status = "FAIL"
                        mismatches.append(f"Intent mismatch: Expected '{expected_intent}', got '{actual_intent}'")
                        print(f"  ❌ [FAIL] Intent mismatch: Expected '{expected_intent}', got '{actual_intent}'")
                    else:
                        mismatches = check_url_assertions(expected, query_params)
                        if mismatches:
                            status = "PARTIAL"
                            print("  ⚠️ [PARTIAL/FAIL] Mismatches found:")
                            for m in mismatches:
                                print(f"     - {m}")
                            print(f"     URL: {dal_source_url}")
                        else:
                            status = "PASS"
                            print("  ✅ [PASS] Successfully resolved and validated parameters!")

        except urllib.error.HTTPError as e:
            status = "ERROR"
            error_body = e.read().decode()
            mismatches.append(f"HTTP {e.code}: {error_body}")
            print(f"  ❌ [ERROR] HTTP {e.code}: {error_body}")
        except Exception as e:
            status = "ERROR"
            mismatches.append(str(e))
            print(f"  ❌ [ERROR] Request failed: {e}")

        results.append({
            "id": qid,
            "subintent": subintent,
            "category": item.get("category", ""),
            "question": question_text,
            "status": status,
            "dal_source_url": dal_source_url,
            "expected_plan": json.dumps(expected),
            "mismatches": "; ".join(mismatches),
            "notes": notes
        })

    # Save to a new CSV file
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
    retest_csv = reports_dir / f"retest_results_{timestamp}.csv"
    with open(retest_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "subintent", "category", "question", "status", "dal_source_url", "expected_plan", "mismatches", "notes"])
        for r in results:
            writer.writerow([
                r["id"],
                r["subintent"],
                r["category"],
                r["question"],
                r["status"],
                r["dal_source_url"] or "",
                r["expected_plan"],
                r["mismatches"],
                r["notes"]
            ])

    print("\n" + "=" * 80)
    print(f"Retest complete! Results saved to: {retest_csv.name}")

if __name__ == "__main__":
    run_retest()