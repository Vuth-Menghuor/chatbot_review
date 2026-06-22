#!/usr/bin/env python3
"""
Interactive Chat for Trade Query Service v3

Connects to the trade_query_v3 service (default port 8005) and provides
an interactive REPL for testing natural-language trade queries.

Usage:
    python service_scripts/trade_query_v3_chat.py
    python service_scripts/trade_query_v3_chat.py --url http://127.0.0.1:8005

Prerequisite:
    Start the service first:
        python -m uvicorn services_version2.trade_query_v3.app:app --host 127.0.0.1 --port 8005 --reload
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urljoin

import httpx


def banner():
    print("=" * 70)
    print("   GDCE Trade Query Service v3 — Interactive Chat")
    print("=" * 70)
    print("Type your question and press Enter.")
    print("Commands:")
    print("  /params <question>  — Show extracted parameters only (no DAL call)")
    print("  /quit  or  /exit    — Leave the chat")
    print("  /help               — Show this help")
    print("")


def print_response(data: dict) -> None:
    """Pretty-print a /query response."""
    status = data.get("status", "unknown")
    count = data.get("count", 0)
    summary = data.get("summary", {})
    metadata = data.get("metadata", {})
    records = data.get("records", [])
    query_params = data.get("query_params", {})

    print("")
    print("─" * 70)
    print(f"Status : {status}")
    print(f"Count  : {count}")

    if query_params:
        print(f"Params : {json.dumps(query_params, indent=2)}")

    if summary:
        print(f"Summary: {json.dumps(summary, indent=2)}")

    if metadata:
        dal_url = metadata.get("dal_source_url")
        if dal_url:
            print(f"Source : {dal_url}")

    if records:
        print(f"\nRecords ({len(records)}):")
        for i, rec in enumerate(records[:10], start=1):
            line = " | ".join(f"{k}={v}" for k, v in rec.items())
            print(f"  {i}. {line}")
        if len(records) > 10:
            print(f"  ... and {len(records) - 10} more")

    print("─" * 70)
    print("")


def query_service(base_url: str, question: str) -> dict:
    url = urljoin(base_url, "/query")
    resp = httpx.post(url, json={"question": question}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def extract_params_service(base_url: str, question: str) -> dict:
    url = urljoin(base_url, "/extract-params")
    resp = httpx.post(url, json={"question": question}, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive chat for Trade Query v3")
    parser.add_argument("--url", default="http://127.0.0.1:8005", help="Trade Query v3 base URL")
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    # Quick health check
    try:
        r = httpx.get(urljoin(base_url, "/health"), timeout=5.0)
        if r.status_code != 200:
            print(f"[WARNING] Health check returned {r.status_code}. Service may not be ready.")
        else:
            print(f"[OK] Connected to {base_url} — {r.json()}")
    except Exception as exc:
        print(f"[ERROR] Cannot reach {base_url}: {exc}")
        print("Make sure the service is running:")
        print("  python -m uvicorn services_version2.trade_query_v3.app:app --host 127.0.0.1 --port 8005 --reload")
        sys.exit(1)

    banner()

    while True:
        try:
            user_input = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            print("Goodbye!")
            break

        if user_input.lower() == "/help":
            banner()
            continue

        if user_input.lower().startswith("/params "):
            question = user_input[8:].strip()
            if not question:
                print("Usage: /params <question>")
                continue
            try:
                result = extract_params_service(base_url, question)
                print(f"\nExtracted parameters: {json.dumps(result.get('params'), indent=2)}")
            except Exception as exc:
                print(f"[ERROR] {exc}")
            continue

        # Normal query flow
        try:
            result = query_service(base_url, user_input)
            print_response(result)
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json()
            except Exception:
                detail = exc.response.text
            print(f"[HTTP {exc.response.status_code}] {detail}")
        except Exception as exc:
            print(f"[ERROR] {exc}")


if __name__ == "__main__":
    main()
