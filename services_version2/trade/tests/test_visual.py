import json
import httpx
import logging
import csv
import datetime
import time
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

API_URL = "http://127.0.0.1:8004/query"  # Adjust port to match your local Trade Service
TEST_FILE = "question_bank.json"             # Your local file with the 124 questions

def validate_visualization(intent, viz_data):
    """Asserts that the dynamic visualization JSON is structurally sound."""
    
    if not viz_data:
        return False, "Visualization object is missing or null. (Might be a NoResultsError from DAL)"

    # 1. Check required keys
    required_keys = {"type", "title", "labels", "datasets"}
    if not required_keys.issubset(viz_data.keys()):
        return False, f"Missing keys. Found: {list(viz_data.keys())}"
        
    chart_type = viz_data["type"]
    labels = viz_data["labels"]
    datasets = viz_data["datasets"]
    
    # 2. Validate Chart Type matches Registry
    valid_types = ["bar", "line", "pie"]
    if chart_type not in valid_types:
        return False, f"Invalid chart type: '{chart_type}'"

    # 3. Validate Data Alignment
    if not isinstance(labels, list):
        return False, "Labels must be an array."
        
    if not isinstance(datasets, list) or len(datasets) == 0:
        return False, "Datasets must be a non-empty array."
        
    for ds in datasets:
        if "label" not in ds or "data" not in ds:
            return False, "Dataset is missing 'label' or 'data'."
        
        if len(ds["data"]) != len(labels):
            return False, f"Data length ({len(ds['data'])}) does not match labels length ({len(labels)})."
            
    # 4. Intent-specific logic checks
    if intent == "trend" and chart_type != "line":
        return False, f"Trend queries must output a line chart, got {chart_type}."
        
    if intent == "ranking" and chart_type != "bar":
        return False, f"Ranking queries must output a bar chart, got {chart_type}."

    return True, "Passed"

def run_tests():
    # Load your local question bank
    try:
        with open(TEST_FILE, "r") as f:
            data = json.load(f)
            questions = data.get("questions", [])
    except Exception as e:
        logging.error(f"Could not load {TEST_FILE}: {e}")
        return

    passed = 0
    failed = 0
    results = []

    with httpx.Client(timeout=30.0) as client:
        for q_obj in questions:
            q_id = q_obj.get("id", "unknown")
            question_text = q_obj.get("question")
            expected_intent = q_obj.get("expected", {}).get("intent", "summary")
            status = "FAIL"
            title = ""
            chart_type = ""
            msg = ""
            
            # Delay to avoid rate limiting (HTTP 429) from DAL server
            time.sleep(1.5)
            
            try:
                # Hit your local query endpoint
                response = client.post(API_URL, json={"question": question_text})
                
                if response.status_code != 200:
                    logging.warning(f"[{q_id}] API Error {response.status_code} (Skipping viz check)")
                    failed += 1
                    status = "ERROR"
                    msg = f"API HTTP Error {response.status_code}"
                    results.append({
                        "id": q_id,
                        "question": question_text,
                        "expected_intent": expected_intent,
                        "status": status,
                        "title": title,
                        "chart_type": chart_type,
                        "message": msg
                    })
                    continue
                    
                resp_json = response.json()
                viz_data = resp_json.get("visualization")
                
                if viz_data:
                    title = viz_data.get("title", "")
                    chart_type = viz_data.get("type", "")
                
                # Run the structural assertions
                is_valid, msg = validate_visualization(expected_intent, viz_data)
                
                if is_valid:
                    passed += 1
                    status = "PASS"
                    logging.info(f"[{q_id}] PASS - {title}")
                else:
                    failed += 1
                    status = "FAIL"
                    logging.error(f"[{q_id}] FAIL - {msg}")
                    
            except Exception as e:
                logging.error(f"[{q_id}] Exception during request: {e}")
                failed += 1
                status = "ERROR"
                msg = str(e)
                
            results.append({
                "id": q_id,
                "question": question_text,
                "expected_intent": expected_intent,
                "status": status,
                "title": title,
                "chart_type": chart_type,
                "message": msg
            })

    logging.info("\n--- Visualization Validation Summary ---")
    logging.info(f"Total: {passed + failed}")
    logging.info(f"Passed: {passed}")
    logging.info(f"Failed: {failed}")

    # Save to a new CSV file inside reports/ folder
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
    report_csv = reports_dir / f"visual_test_results_{timestamp}.csv"
    
    try:
        with open(report_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "question", "expected_intent", "status", "title", "chart_type", "message"])
            for r in results:
                writer.writerow([
                    r["id"],
                    r["question"],
                    r["expected_intent"],
                    r["status"],
                    r["title"],
                    r["chart_type"],
                    r["message"]
                ])
        logging.info(f"Saved visualization test results to: {report_csv}")
    except Exception as e:
        logging.error(f"Failed to write CSV report: {e}")

if __name__ == "__main__":
    run_tests()