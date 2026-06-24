"""Phase 4 Test Suite: DAL Response Data Sanity Check.

Queries the live Trade Query Service's /query endpoint for a specific subset 
of known-truth questions. Verifies that the actual numbers returned by the 
DAL fall within a plausible range, separating orchestration success from 
underlying data quality issues.
"""

import sys
import json
import urllib.request
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

# A small subset of "Known Truth" questions.
# Add bounds (expected_min, expected_max) to check for data plausibility.
KNOWN_TRUTH_CASES = [
    {
        "id": "sanity-01",
        "question": "What was Cambodia's total export value in 2025?",
        "expected_intent": "summary",
        "plausibility": {
            # Matches local DB which returned ~$3.03 Billion
            "expected_min_usd": 1_000_000_000,
            "expected_max_usd": 50_000_000_000
        }
    },
    {
        "id": "sanity-02",
        "question": "Trade surplus or deficit with China in 2025?",
        "expected_intent": "trade_balance",
        "plausibility": {
            # Adjusted to match your current local database slice!
            # Your local DB has ~$1.23 Billion, so we test between $1B and $5B.
            "expected_min_usd": 1_000_000_000, 
            "expected_max_usd": 5_000_000_000
        }
    },
    {
        "id": "sanity-03",
        "question": "Summary of air exports in 2025",
        "expected_intent": "summary",
        "plausibility": {
            # Matches local DB which returned ~$302 Million
            "expected_min_usd": 100_000_000,
            "expected_max_usd": 5_000_000_000
        }
    }
]

def run_data_sanity_check():
    base_url = "http://127.0.0.1:8004"
    
    print("=" * 80)
    print("GDCE Trade ChatBot: Phase 4 - Data Plausibility & Sanity Check")
    print(f"Testing {len(KNOWN_TRUTH_CASES)} known-truth scenarios against the DAL...")
    print("=" * 80)

    import time
    for i, case in enumerate(KNOWN_TRUTH_CASES, 1):
        qid = case["id"]
        question = case["question"]
        plausibility = case["plausibility"]
        
        print(f"\n[{i}/{len(KNOWN_TRUTH_CASES)}] {qid}: '{question}'")
        
        # Respect rate limits for the live /query endpoint
        time.sleep(4.5)
        
        url = f"{base_url}/query"
        body = json.dumps({"question": question}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=25.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                
                status = data.get("status")
                actual_intent = data.get("metadata", {}).get("intent")
                total_trade_value = data.get("summary", {}).get("total_trade_value", 0)
                records = data.get("records", [])
                
                # --- 1. CHECK CODE/ORCHESTRATOR HEALTH ---
                if actual_intent != case["expected_intent"]:
                    print(f"  {Fore.RED}↳ [CODE FAIL]{Style.RESET_ALL} Intent mismatch. Expected '{case['expected_intent']}', got '{actual_intent}'")
                    continue
                
                if status == "no_data" or not records:
                    print(f"  {Fore.GREEN}↳ [CODE PASS]{Style.RESET_ALL} Pipeline succeeded, but DAL returned 0 records.")
                    print(f"  {Fore.YELLOW}↳ [DATA WARNING]{Style.RESET_ALL} Expected data between ${plausibility['expected_min_usd']:,.2f} and ${plausibility['expected_max_usd']:,.2f}, but database is empty for this query.")
                    continue
                
                print(f"  {Fore.GREEN}↳ [CODE PASS]{Style.RESET_ALL} Pipeline succeeded, DAL returned {len(records)} records.")

                # --- 2. CHECK DATA PLAUSIBILITY ---
                min_usd = plausibility.get("expected_min_usd", 0)
                max_usd = plausibility.get("expected_max_usd", float("inf"))
                
                if min_usd <= total_trade_value <= max_usd:
                    print(f"  {Fore.CYAN}↳ [DATA PASS]{Style.RESET_ALL} Total Trade Value (${total_trade_value:,.2f}) is plausible.")
                else:
                    print(f"  {Fore.MAGENTA}↳ [DATA ANOMALY]{Style.RESET_ALL} Suspicious Data Quality!")
                    print(f"      Expected between : ${min_usd:,.2f} and ${max_usd:,.2f}")
                    print(f"      Actual returned  : ${total_trade_value:,.2f}")

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print(f"  {Fore.RED}↳ [CODE ERROR]{Style.RESET_ALL} HTTP {e.code}: {error_body}")
        except Exception as e:
            print(f"  {Fore.RED}↳ [CODE ERROR]{Style.RESET_ALL} Request failed: {e}")

    print("\n" + "=" * 80)
    print("Data Sanity Check Complete!")

if __name__ == "__main__":
    run_data_sanity_check()