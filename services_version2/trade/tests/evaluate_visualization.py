"""Phase 5 Test Suite: Normalization & Visualization Check.

Queries the live Trade Query Service's /query endpoint for all scenarios.
Reads expected UI contracts from visualization_bank.json and inspects the 
`table` and `visualization` objects. Generates a detailed CSV report and
console metrics.
"""

import sys
import json
import csv
import datetime
import urllib.request
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

def run_visualization_tests():
    base_url = "http://127.0.0.1:8004"
    
    bank_path = Path(__file__).resolve().parent / "visualization_bank.json"
    if not bank_path.exists():
        print(f"{Fore.RED}Error: visualization_bank.json not found at {bank_path}{Style.RESET_ALL}")
        print("Please create it with your test configurations.")
        sys.exit(1)
        
    with open(bank_path, "r", encoding="utf-8") as f:
        viz_cases = json.load(f)
        
    print("=" * 80)
    print("GDCE Trade ChatBot: Phase 5 - Full Visualization & Table UI Contract Suite")
    print(f"Testing {len(viz_cases)} UI scenarios from visualization_bank.json...")
    print("=" * 80)

    passed_total = 0
    results_data = []
    stats = {} # Tracker for subintent metrics
    
    import time
    
    for i, case in enumerate(viz_cases, 1):
        qid = case["id"]
        question = case["question"]
        
        # Extract subintent from the ID (e.g., 'summary-01' -> 'summary')
        subintent = qid.split("-")[0]
        if subintent not in stats:
            stats[subintent] = {"total": 0, "PASS": 0, "FAIL": 0, "ERROR": 0}
        stats[subintent]["total"] += 1
        
        print(f"\n[{i}/{len(viz_cases)}] {qid}: '{question}'")
        
        time.sleep(4.5) # Respect rate limits
        
        url = f"{base_url}/query"
        body = json.dumps({"question": question}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})

        errors = []
        actual_type = None
        status = "PASS"
        
        try:
            with urllib.request.urlopen(req, timeout=25.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
                viz = data.get("visualization", {})
                table = data.get("table", {})
                
                if not viz or not table:
                    errors.append(f"No visualization or table returned. (Status: {data.get('status')})")
                    status = "FAIL"
                else:
                    # 1. Check Chart Type
                    actual_type = viz.get("type")
                    expected_type = case.get("expected_type")
                    if expected_type and actual_type != expected_type:
                        if not (expected_type == "pie" and actual_type == "doughnut"):
                            errors.append(f"Expected chart type '{expected_type}', got '{actual_type}'")
                    
                    # 2. Check Multiple Series Split
                    datasets = viz.get("datasets", [])
                    expected_count = case.get("expected_datasets_count")
                    if expected_count is not None:
                        if len(datasets) != expected_count:
                            errors.append(f"Expected {expected_count} datasets, got {len(datasets)}")
                    
                    # 3. Check Labels
                    expected_labels = case.get("expected_labels")
                    if expected_labels:
                        actual_labels = [str(l).upper() for l in viz.get("labels", [])]
                        for exp_lbl in expected_labels:
                            if not any(str(exp_lbl).upper() in l for l in actual_labels):
                                errors.append(f"Expected label '{exp_lbl}' not found in actual labels: {actual_labels}")
                    
                    # 3.5 Check Title
                    expected_title = case.get("expected_title")
                    if expected_title:
                        actual_title = viz.get("title", "")
                        if expected_title.lower() not in actual_title.lower():
                            errors.append(f"Expected title containing '{expected_title}', got '{actual_title}'")
                    
                    # 4. Check Table Columns
                    expected_columns = case.get("expected_columns")
                    if expected_columns:
                        actual_columns = table.get("columns", [])
                        if not all(col in actual_columns for col in expected_columns):
                            errors.append(f"Expected columns {expected_columns} not fully present in actual {actual_columns}")
                    
                    # 5. Check Data Mapping safety (no empty datasets)
                    for ds_idx, ds in enumerate(datasets):
                        if not ds.get("data"):
                            errors.append(f"Dataset {ds_idx} ('{ds.get('label')}') has empty data array!")
                            
                if errors:
                    status = "FAIL"
                    stats[subintent]["FAIL"] += 1
                    print(f"  {Fore.RED}[FAIL] UI Contract Mismatches:{Style.RESET_ALL}")
                    for err in errors:
                        print(f"    - {err}")
                else:
                    passed_total += 1
                    stats[subintent]["PASS"] += 1
                    print(f"  {Fore.GREEN}[PASS] Valid {str(actual_type).upper()} chart configuration.{Style.RESET_ALL}")
                    
        except Exception as e:
            status = "ERROR"
            stats[subintent]["ERROR"] += 1
            errors.append(f"Request failed: {e}")
            print(f"  {Fore.RED}[ERROR] Request failed: {e}{Style.RESET_ALL}")

        # Store for CSV
        results_data.append({
            "id": qid,
            "subintent": subintent,
            "question": question,
            "status": status,
            "expected_type": case.get("expected_type", ""),
            "actual_type": actual_type or "",
            "mismatches": errors
        })

    # --- SAVE CSV REPORT ---
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    report_csv_path = reports_dir / f"visualization_accuracy_{timestamp}.csv"
    with open(report_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "subintent", "question", "status", "expected_type", "actual_type", "mismatches"])
        for r in results_data:
            writer.writerow([
                r["id"], r["subintent"], r["question"], r["status"], 
                r["expected_type"], r["actual_type"], "; ".join(r["mismatches"])
            ])

    # --- PRINT SUMMARY TABLE ---
    overall_accuracy = (passed_total / len(viz_cases)) * 100 if viz_cases else 0
    print("\n" + "=" * 78)
    print(f"VISUALIZATION UI EVALUATION SUMMARY: {round(overall_accuracy, 1)}% ({passed_total}/{len(viz_cases)} passed)")
    print("=" * 78)
    print(f"{'Subintent':<15}{'Total':>7}{'PASS':>7}{'FAIL':>7}{'ERROR':>7}{'PASS%':>9}")
    print("-" * 78)
    for sub, counts in sorted(stats.items(), key=lambda x: x[0]):
        pass_rate = (counts["PASS"] / counts["total"] * 100) if counts["total"] > 0 else 0.0
        print(f"{sub:<15}{counts['total']:>7}{counts['PASS']:>7}{counts['FAIL']:>7}{counts['ERROR']:>7}{pass_rate:>8.1f}%")
    print("-" * 78)
    print(f"CSV report saved to: {report_csv_path}")
    print("=" * 78 + "\n")

if __name__ == "__main__":
    run_visualization_tests()