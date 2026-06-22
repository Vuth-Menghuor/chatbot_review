#!/usr/bin/env python
"""Test GDCE Calculator Service v2"""

import requests
import json
from datetime import datetime

API_URL = "http://127.0.0.1:8002"

print("=" * 50)
print("GDCE Calculator Service v2 - Test")
print("=" * 50)
print()

# Test 1: Health Check
print("[TEST 1] Health Check")
try:
    response = requests.get(f"{API_URL}/health", timeout=5)
    response.raise_for_status()
    health = response.json()
    print("[OK] Status:", health.get("status"))
    print("     Timestamp:", health.get("timestamp"))
    print()
except Exception as e:
    print("[FAILED]", str(e))
    exit(1)

# Test 2: Root Endpoint
print("[TEST 2] Service Info")
try:
    response = requests.get(f"{API_URL}/", timeout=5)
    response.raise_for_status()
    info = response.json()
    print("[OK] Service:", info.get("service"))
    print("     Version:", info.get("version"))
    print("     Status:", info.get("status"))
    print()
except Exception as e:
    print("[FAILED]", str(e))
    exit(1)

# Test 3: Calculate Import Taxes
print("[TEST 3] Calculate Import Taxes")
payload = {
    "calculation_date": "2026-04-01",
    "regime": "import",
    "goods": {
        "hs_code": "0102.29.11",
        "description": "Live cattle",
        "origin_country": "CN"
    },
    "valuation": {
        "customs_value": 800,
        "currency": "USD"
    }
}

try:
    response = requests.post(
        f"{API_URL}/calculate_import_taxes",
        json=payload,
        timeout=10
    )
    response.raise_for_status()
    result = response.json()
    
    print("[OK] Calculation Result:")
    print(f"     ID: {result.get('calculation_id')}")
    print(f"     Total: {result.get('total')} {result.get('currency')}")
    print(f"     Exchange Rate: 1 USD = {result.get('exchange_rate_usd_to_khr')} KHR")
    print()
    
    print("[*] Tax Breakdown:")
    if result.get("breakdown"):
        for key, value in result["breakdown"].items():
            print(f"     {key}: {value} {result.get('currency')}")
    print()
    
    print("[*] Full Response:")
    print(json.dumps(result, indent=2))
    print()
    
    print("[SUCCESS] Test passed!")
    
except Exception as e:
    print("[FAILED]", str(e))
    if hasattr(e, 'response') and e.response is not None:
        print("Response:", e.response.text)
    exit(1)
