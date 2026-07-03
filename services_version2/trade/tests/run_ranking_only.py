#!/usr/bin/env python3
"""
GDCE Trade ChatBot Ranking Intent Test Runner
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
BASE_DELAY = 0.3
BACKOFF_FACTOR = 2


def call_api(url, body, timeout=30):
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
            if e.code in [502, 503, 504]:
                print(f"⚠️ HTTP {e.code} (attempt {attempt}/{MAX_RETRIES})")
            else:
                return {"status": "error", "error": f"HTTP {e.code}"}
        except Exception as e:
            print(f"⚠️ Error (attempt {attempt}/{MAX_RETRIES}): {e}")

        if attempt < MAX_RETRIES:
            sleep_time = BASE_DELAY * (BACKOFF_FACTOR ** (attempt - 1))
            time.sleep(sleep_time)

    return {"status": "error", "error": "Max retries exceeded"}


def run_ranking_questions():
    tests_dir = Path(__file__).resolve().parent
    bank_path = tests_dir / "visualization_bank.json"

    if not bank_path.exists():
        print(f"Error: visualization_bank.json not found")
        return

    with open(bank_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    target_cases = []
    for case in cases:
        qid = case.get("id", "")
        prefix = qid.split("-")[0] if "-" in qid else qid
        intent = INTENT_MAPPING.get(prefix, "unknown")
        if intent == "ranking":
            target_cases.append(case)

    print(f"Loaded {len(target_cases)} ranking test cases")
    url = f"{BASE_URL}/query"
    responses = []

    for i, case in enumerate(target_cases, 1):
        question = case.get("question", "")
        print(f"[{i}/{len(target_cases)}] ranking: {question}")
        body = json.dumps({"question": question}).encode("utf-8")
        response = call_api(url, body)
        responses.append(response)
        time.sleep(BASE_DELAY)

    output_dir = tests_dir / "outputs"
    output_dir.mkdir(exist_ok=True)
    file_path = output_dir / "ranking_output.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(responses, f, indent=2, ensure_ascii=False)

    success_count = sum(1 for r in responses if r.get("status") != "error")
    print(f"\nRanking: {success_count}/{len(responses)} successful → {file_path.name}")
    print("\nDone ✔")


if __name__ == "__main__":
    run_ranking_questions()
