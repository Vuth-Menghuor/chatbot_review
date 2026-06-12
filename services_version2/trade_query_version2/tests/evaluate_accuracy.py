"""Granular Accuracy Evaluator for GDCE Trade ChatBot."""

import os
import sys
import json
import io
import logging
import datetime
import urllib.request
import urllib.parse
from pathlib import Path

# Add repository root to path so we can import services_version2
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

# Load .env manually to ensure API keys are populated
def load_env():
    env_path = repo_root / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")

load_env()

# Import the Trade Query module components
from services_version2.trade_query_version2.core.validation import extract_parameters
from services_version2.trade_query_version2.dal.dal_request_builder import DALRequestBuilder
from services_version2.trade_query_version2.dal.url_builder import DALUrlBuilder
from services_version2.trade_query_version2.core.transformers import transform_params_for_dal

# Log capture handler
class LogCapture:
    """Interceptors to capture python logging output from the trade query service."""
    def __init__(self, logger_name="services_version2.trade_query_version2"):
        self.logger_name = logger_name
        self.log_stream = io.StringIO()
        self.handler = logging.StreamHandler(self.log_stream)
        self.handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
        self.old_level = None

    def __enter__(self):
        logger = logging.getLogger(self.logger_name)
        self.old_level = logger.level
        logger.setLevel(logging.DEBUG)
        logger.addHandler(self.handler)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger = logging.getLogger(self.logger_name)
        logger.removeHandler(self.handler)
        if self.old_level is not None:
            logger.setLevel(self.old_level)

    def get_logs(self) -> str:
        return self.log_stream.getvalue()

def check_live_servers():
    """Verify if the local orchestrator and trade service are running on ports 8001 and 8004."""
    try:
        # Check Orchestrator
        with urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=1.0) as r1:
            # Check Trade Query Service
            with urllib.request.urlopen("http://127.0.0.1:8004/health", timeout=1.0) as r2:
                return r1.status == 200 and r2.status == 200
    except Exception:
        pass
    return False

def check_e2e_answer(question, expected_substrings):
    """Query live orchestrator to verify the text answer generated for the question."""
    url = "http://127.0.0.1:8001/query"
    body = json.dumps({"question": question, "session_id": "test-accuracy-run"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            answer = res_data.get("answer", "")
            mismatches = []
            for sub in expected_substrings:
                if sub.lower() not in answer.lower():
                    mismatches.append(sub)
            return answer, mismatches, None
    except Exception as e:
        return "", [], str(e)

def check_parameters(expected, actual):
    """Compare expected parameters against actual extracted parameters."""
    mismatches = {}
    for key, exp_val in expected.items():
        act_val = actual.get(key)
        
        # Normalize list check
        if isinstance(exp_val, list) and isinstance(act_val, list):
            if sorted(exp_val) != sorted(act_val):
                mismatches[key] = f"Expected list {exp_val}, got {act_val}"
        elif isinstance(exp_val, list):
            mismatches[key] = f"Expected list {exp_val}, got {act_val}"
        else:
            if str(exp_val).lower() != str(act_val).lower():
                mismatches[key] = f"Expected '{exp_val}', got '{act_val}'"
    return mismatches

def check_url_params(expected, parsed_query):
    """Compare expected URL parameters against parsed actual URL parameters."""
    mismatches = {}
    for key, exp_val in expected.items():
        url_key = key
        if key == "start_period":
            url_key = "start-period"
        elif key == "end_period":
            url_key = "end-period"
            
        act_val_list = parsed_query.get(url_key, [])
        
        if key == "filter":
            # Multiple repeatable filters
            exp_set = set(exp_val)
            act_set = set(act_val_list)
            if not exp_set.issubset(act_set):
                missing = exp_set - act_set
                mismatches[key] = f"Missing filters: {missing}. Got: {act_set}"
        elif key in ("dimensions", "measures"):
            act_str = act_val_list[0] if act_val_list else ""
            act_set = set(item.strip() for item in act_str.split(",") if item.strip())
            
            if isinstance(exp_val, list):
                exp_set = set(exp_val)
            else:
                exp_set = set(item.strip() for item in exp_val.split(",") if item.strip())
                
            if exp_set != act_set:
                mismatches[key] = f"Expected dimensions/measures {exp_set}, got {act_set}"
        else:
            act_val = act_val_list[0] if act_val_list else None
            if str(exp_val).lower() != str(act_val).lower():
                mismatches[key] = f"Expected URL value '{exp_val}', got '{act_val}'"
    return mismatches

def run_evaluation():
    test_cases_path = Path(__file__).parent / "accuracy_test_cases.json"
    if not test_cases_path.exists():
        print(f"Error: {test_cases_path} does not exist. Run generate_test_cases.py first.")
        sys.exit(1)
        
    with open(test_cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    print("=" * 70)
    print(f"GDCE Trade ChatBot Accuracy Evaluation Suite")
    print(f"Total Test Cases Loaded: {len(cases)}")
    print("=" * 70)
    
    live_online = check_live_servers()
    if live_online:
        print("[ONLINE] Live servers detected (Orchestrator + Trade Query Service). Running E2E checks.")
    else:
        print("[OFFLINE] Live servers not detected. Running Parameter & URL validation locally. E2E checks skipped.")
    
    print("-" * 70)
    
    # Initialize metric trackers
    intent_stats = {} # intent -> {"total": 0, "intent_ok": 0, "params_ok": 0, "url_ok": 0, "e2e_ok": 0, "e2e_count": 0}
    attributes = {
        "intent": {"total": 0, "correct": 0},
        "country": {"total": 0, "correct": 0},
        "year": {"total": 0, "correct": 0},
        "hs_code": {"total": 0, "correct": 0},
        "transport": {"total": 0, "correct": 0},
        "dal_url": {"total": 0, "correct": 0}
    }
    
    detailed_report = []
    
    request_builder = DALRequestBuilder()
    url_builder = DALUrlBuilder(base_url="http://localhost:8000", dataset="trade_volume")
    
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
    
    for case in cases:
        case_id = case["id"]
        question = case["question"]
        target_intent = case["intent"]
        expected_params = case["expected_params"]
        expected_url = case["expected_url_params"]
        is_ambig = case.get("ambiguous", False)
        is_e2e = case.get("e2e", False)
        
        # Initialize stats for this intent
        if target_intent not in intent_stats:
            intent_stats[target_intent] = {
                "total": 0, "intent_ok": 0, "params_ok": 0, "url_ok": 0, "e2e_ok": 0, "e2e_count": 0
            }
            
        intent_stats[target_intent]["total"] += 1
        
        # Execute query and capture logs
        actual_params = {}
        param_mismatches = {}
        url_mismatches = {}
        e2e_mismatches = []
        e2e_error = None
        actual_answer = ""
        
        # Introduce rate-limiting delay between LLM calls to avoid 503/429 errors
        # (Only if api key is set)
        api_key = os.getenv("X_GOOG_API_KEY") or os.getenv("GEMINI_API_KEY")
        if api_key:
            import time
            time.sleep(1.5)

        with LogCapture() as logs:
            try:
                # 1. Parameter Extraction
                actual_params = extract_parameters(question)
                
                # 2. DAL Request Construction
                dal_params = transform_params_for_dal(actual_params)
                
                # Get the strategy and merge defaults to align URL construction with BaseHandler
                from services_version2.trade_query_version2.handlers.strategies import STRATEGIES
                from services_version2.trade_query_version2.handlers.base import BaseHandler
                intent = actual_params.get("intent", "summary")
                strategy = STRATEGIES.get(intent, STRATEGIES["summary"])
                
                handler_instance = BaseHandler()
                merged_params = handler_instance._merge_strategy_defaults(dal_params, strategy)
                
                dal_request = request_builder.build_request(intent, merged_params)
                
                # 3. URL Construction
                generated_url = url_builder.build(dal_request)
                parsed_url = urllib.parse.urlparse(generated_url)
                parsed_query = urllib.parse.parse_qs(parsed_url.query)
            except Exception as e:
                # Failed execution
                param_mismatches["pipeline_execution"] = str(e)
                generated_url = ""
                parsed_query = {}
                
        # Intercepted service logs
        captured_logs = logs.get_logs()
        
        # Perform Checks
        intent_match = False
        if "pipeline_execution" not in param_mismatches:
            # Intent
            intent_match = actual_params.get("intent") == expected_params.get("intent")
            if intent_match:
                intent_stats[target_intent]["intent_ok"] += 1
                attributes["intent"]["correct"] += 1
            attributes["intent"]["total"] += 1
            
            # Param Checks
            param_mismatches = check_parameters(expected_params, actual_params)
            
            # Attribute-level accuracy mapping
            # Country Check
            country_keys = ["origin_country", "destination_country", "partner_country"]
            country_ok = all(k not in param_mismatches for k in country_keys if k in expected_params)
            if any(k in expected_params for k in country_keys):
                attributes["country"]["total"] += 1
                if country_ok:
                    attributes["country"]["correct"] += 1
            
            # Year Check
            year_keys = ["year", "years", "start_period", "end_period", "quarter", "month", "frequency"]
            year_ok = all(k not in param_mismatches for k in year_keys if k in expected_params)
            if any(k in expected_params for k in year_keys):
                attributes["year"]["total"] += 1
                if year_ok:
                    attributes["year"]["correct"] += 1
                    
            # HS Code Check
            hs_keys = ["hs_code", "hs_chapter", "hs_heading"]
            hs_ok = all(k not in param_mismatches for k in hs_keys if k in expected_params)
            if any(k in expected_params for k in hs_keys):
                attributes["hs_code"]["total"] += 1
                if hs_ok:
                    attributes["hs_code"]["correct"] += 1
                    
            # Transport Check
            transport_ok = "mode_of_transport" not in param_mismatches
            if "mode_of_transport" in expected_params:
                attributes["transport"]["total"] += 1
                if transport_ok:
                    attributes["transport"]["correct"] += 1
            
            # URL checks
            url_mismatches = check_url_params(expected_url, parsed_query)
            
            url_ok = len(url_mismatches) == 0
            if url_ok:
                intent_stats[target_intent]["url_ok"] += 1
                attributes["dal_url"]["correct"] += 1
            attributes["dal_url"]["total"] += 1
            
            params_ok = len(param_mismatches) == 0
            if params_ok:
                intent_stats[target_intent]["params_ok"] += 1
        else:
            attributes["intent"]["total"] += 1
            attributes["dal_url"]["total"] += 1
            
        # E2E Answer Verification
        e2e_status = "N/A"
        if is_e2e:
            intent_stats[target_intent]["e2e_count"] += 1
            if live_online:
                expected_subs = case.get("expected_answer_contains", [])
                actual_answer, e2e_mismatches, e2e_error = check_e2e_answer(question, expected_subs)
                if not e2e_mismatches and not e2e_error:
                    intent_stats[target_intent]["e2e_ok"] += 1
                    e2e_status = "PASS"
                else:
                    e2e_status = "FAIL"
            else:
                e2e_status = "SKIPPED"
                
        # Record details
        case_passed = intent_match and len(param_mismatches) == 0 and len(url_mismatches) == 0
        if is_e2e and live_online and e2e_status != "PASS":
            case_passed = False
            
        detailed_report.append({
            "id": case_id,
            "question": question,
            "intent": target_intent,
            "passed": case_passed,
            "intent_match": intent_match,
            "expected_params": expected_params,
            "actual_params": actual_params,
            "param_mismatches": param_mismatches,
            "expected_url_params": expected_url,
            "generated_url": generated_url,
            "url_mismatches": url_mismatches,
            "ambiguous": is_ambig,
            "expected_behavior": case.get("expected_behavior"),
            "e2e": is_e2e,
            "e2e_status": e2e_status,
            "e2e_answer": actual_answer,
            "e2e_missing_substrings": e2e_mismatches,
            "e2e_error": e2e_error,
            "logs": captured_logs
        })
        
    # Calculate aggregated statistics
    total_cases = len(cases)
    total_passed = sum(1 for c in detailed_report if c["passed"])
    overall_accuracy = (total_passed / total_cases) * 100 if total_cases > 0 else 0
    
    # Granular scores
    granular_scores = {}
    for attr, data in attributes.items():
        score = (data["correct"] / data["total"]) * 100 if data["total"] > 0 else 100.0
        granular_scores[attr] = {
            "correct": data["correct"],
            "total": data["total"],
            "accuracy": round(score, 1)
        }
        
    intent_accuracies = {}
    for intent, stats in intent_stats.items():
        total = stats["total"]
        intent_acc = (stats["intent_ok"] / total) * 100
        params_acc = (stats["params_ok"] / total) * 100
        url_acc = (stats["url_ok"] / total) * 100
        
        e2e_acc = 100.0
        if stats["e2e_count"] > 0 and live_online:
            e2e_acc = (stats["e2e_ok"] / stats["e2e_count"]) * 100
            
        intent_accuracies[intent] = {
            "total": total,
            "intent_accuracy": round(intent_acc, 1),
            "parameter_accuracy": round(params_acc, 1),
            "url_accuracy": round(url_acc, 1),
            "e2e_accuracy": round(e2e_acc, 1) if stats["e2e_count"] > 0 else "N/A"
        }
        
    # Create Reports Directory
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)
    
    # Save JSON report
    summary_json = {
        "timestamp": timestamp,
        "overall_accuracy": round(overall_accuracy, 1),
        "total_cases": total_cases,
        "total_passed": total_passed,
        "attribute_accuracies": granular_scores,
        "intent_accuracies": intent_accuracies
    }
    
    json_report_path = reports_dir / f"accuracy_{timestamp}.json"
    with open(json_report_path, "w", encoding="utf-8") as f:
        json.dump(summary_json, f, indent=2)
        
    # Save Detailed log
    log_report_path = reports_dir / f"run_details_{timestamp}.log"
    with open(log_report_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"GDCE TRADE CHATBOT ACCURACY TEST RUN REPORT - {timestamp}\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Summary Metrics:\n")
        f.write(f"  - Overall Pipeline Accuracy: {summary_json['overall_accuracy']}%\n")
        f.write(f"  - Total Cases Checked      : {total_cases}\n")
        f.write(f"  - Total Cases Passed       : {total_passed}\n\n")
        
        f.write("Attribute Accuracy Scores:\n")
        for attr, s in granular_scores.items():
            f.write(f"  - {attr.capitalize():<10} : {s['accuracy']}% ({s['correct']}/{s['total']})\n")
        f.write("\n")
        
        f.write("Intent Level Accuracy Breakdown:\n")
        for intent, s in intent_accuracies.items():
            f.write(f"  - {intent:<15} (Count: {s['total']}):\n")
            f.write(f"      * Intent Classification Accuracy : {s['intent_accuracy']}%\n")
            f.write(f"      * Parameter Extraction Accuracy  : {s['parameter_accuracy']}%\n")
            f.write(f"      * DAL URL Generation Accuracy    : {s['url_accuracy']}%\n")
            f.write(f"      * E2E Answer Match Accuracy     : {s['e2e_accuracy']}%\n")
        f.write("\n" + "="*80 + "\n\n")
        
        f.write("DETAILED TEST CASE LOGS AND DIAGNOSTICS\n")
        f.write("=" * 80 + "\n\n")
        
        for r in detailed_report:
            status_str = "PASS" if r["passed"] else "FAIL"
            f.write(f"Case #{r['id']}: [{status_str}] - Question: \"{r['question']}\"\n")
            f.write(f"  * Detected Intent : {r['actual_params'].get('intent')} (Expected: {r['intent']})\n")
            
            if r["param_mismatches"]:
                f.write(f"  * Parameter Extraction Mismatches:\n")
                for k, v in r["param_mismatches"].items():
                    f.write(f"      - {k}: {v}\n")
            else:
                f.write(f"  * Parameter Extraction: PASS\n")
                
            if r["url_mismatches"]:
                f.write(f"  * DAL URL Mismatches:\n")
                for k, v in r["url_mismatches"].items():
                    f.write(f"      - {k}: {v}\n")
            else:
                f.write(f"  * DAL URL Generation: PASS\n")
                
            if r["e2e"]:
                f.write(f"  * E2E Status: {r['e2e_status']}\n")
                if r["e2e_answer"]:
                    f.write(f"  * E2E Generated Answer:\n\"\"\"\n{r['e2e_answer'].strip()}\n\"\"\"\n")
                if r["e2e_missing_substrings"]:
                    f.write(f"  * E2E Missing Key Content Substrings: {r['e2e_missing_substrings']}\n")
                if r["e2e_error"]:
                    f.write(f"  * E2E Connection Error: {r['e2e_error']}\n")
                    
            if r["logs"]:
                f.write(f"  * Captured Service Execution Logs:\n")
                for log_line in r["logs"].strip().split("\n"):
                    f.write(f"      {log_line}\n")
            f.write("-" * 80 + "\n\n")
            
    # Print Console Summary Table
    print("\n" + "=" * 70)
    print(f"EVALUATION SUMMARY: Overall Accuracy: {summary_json['overall_accuracy']}% ({total_passed}/{total_cases} passed)")
    print("=" * 70)
    print(f"{'Attribute':<15} | {'Accuracy %':<12} | {'Fraction Passed':<18}")
    print("-" * 70)
    for attr, s in granular_scores.items():
        print(f"{attr.capitalize():<15} | {s['accuracy']:<12}% | {s['correct']}/{s['total']}")
    print("-" * 70)
    print(f"\n{'Intent':<15} | {'Intent Acc %':<12} | {'Params Acc %':<12} | {'URL Acc %':<12}")
    print("-" * 70)
    for intent, s in intent_accuracies.items():
        print(f"{intent:<15} | {s['intent_accuracy']:<12}% | {s['parameter_accuracy']:<12}% | {s['url_accuracy']}%")
    print("-" * 70)
    
    # Print the 5 worst failures
    failures = [c for c in detailed_report if not c["passed"]]
    if failures:
        print(f"\nDiagnostic Failures (Showing first 5):")
        print("-" * 70)
        for i, f_case in enumerate(failures[:5]):
            print(f"#{f_case['id']}: \"{f_case['question']}\"")
            if f_case["param_mismatches"]:
                print(f"  Param Mismatches: {f_case['param_mismatches']}")
            if f_case["url_mismatches"]:
                print(f"  URL Mismatches:   {f_case['url_mismatches']}")
            if f_case["e2e_missing_substrings"]:
                print(f"  E2E Missing Terms: {f_case['e2e_missing_substrings']}")
            print()
            
    print(f"Summary saved to: {json_report_path}")
    print(f"Detailed logs and diagnostics saved to: {log_report_path}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    run_evaluation()
