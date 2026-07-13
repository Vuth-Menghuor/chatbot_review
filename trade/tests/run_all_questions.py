#!/usr/bin/env python3
"""
GDCE Trade ChatBot Question Test Runner (Robust Version)

Improvements:
- Retry on failures (including HTTP 502)
- Exponential backoff
- Reduced backend overload
- Safer response handling
- More stable long-run execution
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

INTENT_MAPPING = {
    "summary": "summary",
    "ranking": "ranking",
    "trend": "trend",
    "comparison": "comparison",
    "breakdown": "breakdown",
    "growth": "growth",
    "tradebalance": "trade_balance"
}

BASE_URL = "http://127.0.0.1:8004"
MAX_RETRIES = 3
BASE_DELAY = 1.2   # increased from 0.3 to prevent HTTP 429
BACKOFF_FACTOR = 2


def call_api(url, body, timeout=30):
    """
    Call API with retry + exponential backoff
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))

        except urllib.error.HTTPError as e:
            # Retry only on server errors (502, 503, 504)
            if e.code in [502, 503, 504]:
                print(f"[Warning] HTTP {e.code} (attempt {attempt}/{MAX_RETRIES})")
            else:
                return {"status": "error", "error": f"HTTP {e.code}"}

        except Exception as e:
            print(f"[Warning] Error (attempt {attempt}/{MAX_RETRIES}): {e}")

        # Backoff before retry
        if attempt < MAX_RETRIES:
            sleep_time = BASE_DELAY * (BACKOFF_FACTOR ** (attempt - 1))
            time.sleep(sleep_time)

    return {
        "status": "error",
        "error": "Max retries exceeded"
    }


def run_all_questions():
    tests_dir = Path(__file__).resolve().parent
    bank_path = tests_dir / "visualization_bank.json"

    if not bank_path.exists():
        print(f"Error: visualization_bank.json not found at {bank_path}")
        return

    with open(bank_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    print(f"Loaded {len(cases)} test cases")
    print(f"Target: {BASE_URL}/query\n")

    grouped_responses = {v: [] for v in INTENT_MAPPING.values()}
    grouped_responses["unknown"] = []

    url = f"{BASE_URL}/query"

    for i, case in enumerate(cases, 1):
        qid = case.get("id", "")
        question = case.get("question", "")

        prefix = qid.split("-")[0] if "-" in qid else qid
        intent = INTENT_MAPPING.get(prefix, "unknown")

        print(f"[{i}/{len(cases)}] {intent}: {question}")

        body = json.dumps({"question": question}).encode("utf-8")

        response = call_api(url, body)

        grouped_responses[intent].append(response)

        # pacing to avoid backend overload
        time.sleep(BASE_DELAY)

    # Save outputs
    output_dir = tests_dir / "outputs"
    output_dir.mkdir(exist_ok=True)

    print("\nSaving results...\n")

    for intent, responses in grouped_responses.items():
        file_path = output_dir / f"{intent}_output.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(responses, f, indent=2, ensure_ascii=False)

        success_count = sum(1 for r in responses if r.get("status") != "error")
        print(f"{intent}: {success_count}/{len(responses)} successful -> {file_path.name}")

    print("\nDone [OK]")


if __name__ == "__main__":
    run_all_questions()