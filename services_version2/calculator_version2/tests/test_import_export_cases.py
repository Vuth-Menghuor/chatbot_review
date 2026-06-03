#!/usr/bin/env python3
"""
Calculator Test Suite - Import / Export Cases
===============================================
Run while the Calculator service (port 8002) is running:

    python test_import_export_cases.py

Tests every calculation path with REAL HS codes from the local database.
"""

import json
import sys
from datetime import datetime

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CALCULATOR_URL = "http://127.0.0.1:8002"
TIMEOUT = 30.0

client = httpx.Client(timeout=TIMEOUT)


def check_service() -> bool:
    try:
        r = client.get(f"{CALCULATOR_URL}/health")
        return r.status_code == 200
    except Exception as e:
        print(f"Calculator not reachable at {CALCULATOR_URL}: {e}")
        return False


def run_case(name: str, payload: dict) -> dict:
    """Send one calculation request and return the JSON response."""
    url = f"{CALCULATOR_URL}/v1/calculate_import_taxes"
    try:
        r = client.post(url, json=payload)
        if r.status_code != 200:
            return {"_error": True, "status": r.status_code, "detail": r.text}
        return r.json()
    except Exception as e:
        return {"_error": True, "exception": str(e)}


def print_result(name: str, result: dict):
    """Pretty-print a calculation result."""
    print(f"\n{'='*60}")
    print(f"CASE: {name}")
    print(f"{'='*60}")

    if result.get("_error"):
        print(f"  [FAIL] ERROR: {result}")
        return

    total = result.get("total", 0)
    currency = result.get("currency", "KHR")
    breakdown = result.get("breakdown", {})
    line_items = result.get("line_items", [])
    assumptions = result.get("assumptions", [])

    print(f"  Total: {total:,.0f} {currency}")
    print(f"  Breakdown: {json.dumps(breakdown, indent=4)}")
    print(f"  Line Items:")
    for item in line_items:
        print(
            f"    - {item.get('name', '?'):<42} "
            f"base={item.get('base', 0):>14,.0f}  "
            f"rate={item.get('rate', 0):>6.2f}%  "
            f"amount={item.get('amount', 0):>12,.0f} {currency}"
        )
    print(f"  Assumptions (first 6):")
    for a in assumptions[:6]:
        print(f"    - {a}")
    if len(assumptions) > 6:
        print(f"    ... ({len(assumptions) - 6} more)")


# ---------------------------------------------------------------------------
# REAL HS CODES FROM THE DATABASE (verified 2026-05-13)
# ---------------------------------------------------------------------------
# 2208.90.10  CD=35% ST=35% VAT=10%  (spirits / liquor)
# 2402.20.10  CD=7%  ST=20% VAT=10%  (cigarettes)
# 2402.20.90  CD=7%  ST=20% VAT=10%  (cigarettes)
# 3923.10.10  CD=15% ST=10% VAT=10%  (plastic containers)
# 8471.30.20  CD=7%  ST=0%  VAT=10%  (laptops)
# 8517.62.10  CD=0%  ST=0%  VAT=10%  (communication equipment)
# 0304.89.10  CD=15% ST=0%  VAT=10% ET=10% (fish fillets)
# 4001.21.10  CD=7%  ST=0%  VAT=10%  (natural rubber)
# 4001.22.10  CD=7%  ST=0%  VAT=10%  (smoked rubber sheets)
# 4001.29.10  CD=7%  ST=0%  VAT=10%  (other rubber)
# 1602.32.10  CD=35% ST=0%  VAT=10%  (prepared meat)
# 1905.90.10  CD=15% ST=0%  VAT=10%  (bread / biscuits)
# 4202.92.10  CD=7%  ST=0%  VAT=10%  (containers / bags)
# 6203.42.10  CD=15% ST=0%  VAT=10%  (men's trousers)
# 6403.91.10  CD=15% ST=0%  VAT=10%  (footwear)
# 8528.72.10  CD=15% ST=0%  VAT=10%  (reception apparatus)
# ---------------------------------------------------------------------------

CASES = [
    # --- 1. NORMAL IMPORT (COP + SOP + VOP) ---
    (
        "Normal Import - COP + SOP + VOP (spirits)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Whisky in bottles",
                "hs_code": "2208.90.10",
                "origin_country": "GB",
                "quantity": 500,
                "unit": "liters",
            },
            "valuation": {
                "customs_value": 12000,
                "currency": "USD",
            },
            "flags": {},
        },
    ),
    (
        "Normal Import - COP + SOP + VOP (cigarettes)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Cigarettes",
                "hs_code": "2402.20.10",
                "origin_country": "ID",
                "quantity": 10000,
                "unit": "sticks",
            },
            "valuation": {
                "customs_value": 8000,
                "currency": "USD",
            },
            "flags": {},
        },
    ),
    (
        "Normal Import - COP + SOP + VOP (plastic containers)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Plastic food containers",
                "hs_code": "3923.10.10",
                "origin_country": "CN",
                "quantity": 5000,
                "unit": "units",
            },
            "valuation": {
                "customs_value": 15000,
                "currency": "USD",
            },
            "flags": {},
        },
    ),

    # --- 2. NORMAL IMPORT with ZERO SOP (COP + VOP only) ---
    (
        "Normal Import - Zero SOP (laptops)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Laptop computers",
                "hs_code": "8471.30.20",
                "origin_country": "US",
                "quantity": 100,
                "unit": "units",
            },
            "valuation": {
                "customs_value": 50000,
                "currency": "USD",
            },
            "flags": {},
        },
    ),
    (
        "Normal Import - Zero SOP (communication equipment)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Mobile phones",
                "hs_code": "8517.62.10",
                "origin_country": "CN",
                "quantity": 200,
                "unit": "units",
            },
            "valuation": {
                "customs_value": 25000,
                "currency": "USD",
            },
            "flags": {},
        },
    ),

    # --- 3. FTA/DV CASE (preferential rates) ---
    (
        "FTA/DV Case - ACFTA preferential (laptops from ASEAN)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Laptop computers",
                "hs_code": "8471.30.20",
                "origin_country": "VN",
                "quantity": 50,
                "unit": "units",
            },
            "valuation": {
                "customs_value": 20000,
                "currency": "USD",
            },
            "flags": {
                "fta_applicable": True,
                "fta_certificate_type": "ACFTA",
            },
        },
    ),
    (
        "FTA/DV Case - ACFTA preferential (rubber from ASEAN)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Natural rubber sheets",
                "hs_code": "4001.21.10",
                "origin_country": "VN",
                "quantity": 5000,
                "unit": "kg",
            },
            "valuation": {
                "customs_value": 8000,
                "currency": "USD",
            },
            "flags": {
                "fta_applicable": True,
                "fta_certificate_type": "ACFTA",
            },
        },
    ),

    # --- 4. FTA/DV/DQ CASE (preferential + DQ adjustment) ---
    (
        "FTA/DV/DQ Case - with DQ factor 0.85 (spirits)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Whisky in bottles",
                "hs_code": "2208.90.10",
                "origin_country": "VN",
                "quantity": 200,
                "unit": "liters",
            },
            "valuation": {
                "customs_value": 5000,
                "currency": "USD",
                "dq_factor": 0.85,
            },
            "flags": {
                "fta_applicable": True,
                "fta_certificate_type": "ACFTA",
                "dq_applicable": True,
            },
        },
    ),
    (
        "FTA/DV/DQ Case - with DQ factor 0.90 (plastic)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Plastic containers",
                "hs_code": "3923.10.10",
                "origin_country": "TH",
                "quantity": 3000,
                "unit": "units",
            },
            "valuation": {
                "customs_value": 10000,
                "currency": "USD",
                "dq_factor": 0.90,
            },
            "flags": {
                "fta_applicable": True,
                "fta_certificate_type": "ACFTA",
                "dq_applicable": True,
            },
        },
    ),

    # --- 5. RUBBER EXPORT (ETR only) ---
    (
        "Rubber Export - ETR only",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "export",
            "goods": {
                "description": "Natural rubber",
                "hs_code": "4001.21.10",
                "origin_country": "KH",
                "net_mass_kg": 15000,
            },
            "valuation": {
                "customs_value": 18000,
                "currency": "USD",
                "declared_value": 1200,
                "declared_value_basis": "per_ton",
            },
            "flags": {
                "rubber_case": True,
            },
        },
    ),
    (
        "Rubber Export - Smoked sheets",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "export",
            "goods": {
                "description": "Smoked rubber sheets",
                "hs_code": "4001.22.10",
                "origin_country": "KH",
                "net_mass_kg": 8000,
            },
            "valuation": {
                "customs_value": 9600,
                "currency": "USD",
                "declared_value": 1200,
                "declared_value_basis": "per_ton",
            },
            "flags": {
                "rubber_case": True,
            },
        },
    ),

    # --- 6. EXEMPTIONS ---
    (
        "Exemption - QIP",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Construction machinery",
                "hs_code": "4202.92.10",
                "origin_country": "JP",
            },
            "valuation": {
                "customs_value": 50000,
                "currency": "USD",
            },
            "flags": {
                "qip_exemption": True,
            },
        },
    ),
    (
        "Exemption - SEZ",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Raw materials for garment production",
                "hs_code": "6203.42.10",
                "origin_country": "CN",
            },
            "valuation": {
                "customs_value": 30000,
                "currency": "USD",
            },
            "flags": {
                "sez_applicable": True,
            },
        },
    ),
    (
        "Exemption - Diplomatic",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Office equipment for embassy",
                "hs_code": "8471.30.20",
                "origin_country": "US",
            },
            "valuation": {
                "customs_value": 5000,
                "currency": "USD",
            },
            "flags": {
                "diplomatic_exemption": True,
            },
        },
    ),
    (
        "Exemption - NGO / Humanitarian",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Medical supplies for flood relief",
                "hs_code": "3004.90.10",
                "origin_country": "US",
            },
            "valuation": {
                "customs_value": 30000,
                "currency": "USD",
            },
            "flags": {
                "ngo_humanitarian": True,
            },
        },
    ),
    (
        "Exemption - Educational",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Laboratory microscopes",
                "hs_code": "8517.62.10",
                "origin_country": "DE",
            },
            "valuation": {
                "customs_value": 8500,
                "currency": "USD",
            },
            "flags": {
                "educational_exemption": True,
            },
        },
    ),
    (
        "Exemption - Medical",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Medical diagnostic equipment",
                "hs_code": "3004.90.10",
                "origin_country": "US",
            },
            "valuation": {
                "customs_value": 250000,
                "currency": "USD",
            },
            "flags": {
                "medical_exemption": True,
            },
        },
    ),
    (
        "Exemption - Passenger Allowance",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Personal electronics in luggage",
                "hs_code": "8471.30.20",
                "origin_country": "US",
            },
            "valuation": {
                "customs_value": 1200,
                "currency": "USD",
            },
            "flags": {
                "passenger_allowance": True,
            },
        },
    ),

    # --- 7. EDGE CASES ---
    (
        "Edge - Mass-based DV per ton (fish fillets)",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Frozen fish fillets",
                "hs_code": "0304.89.10",
                "origin_country": "VN",
                "net_mass_kg": 10000,
            },
            "valuation": {
                "customs_value": 8000,
                "currency": "USD",
                "declared_value": 800,
                "declared_value_basis": "per_ton",
            },
            "flags": {},
        },
    ),
    (
        "Edge - Input already in KHR",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Rice",
                "hs_code": "1006.10.10",
                "origin_country": "KH",
            },
            "valuation": {
                "customs_value": 50000000,
                "currency": "KHR",
            },
            "flags": {},
        },
    ),
    (
        "Edge - FTA without certificate type specified",
        {
            "calculation_date": datetime.now().strftime("%Y-%m-%d"),
            "regime": "import",
            "goods": {
                "description": "Laptop computers",
                "hs_code": "8471.30.20",
                "origin_country": "VN",
                "quantity": 20,
                "unit": "units",
            },
            "valuation": {
                "customs_value": 10000,
                "currency": "USD",
            },
            "flags": {
                "fta_applicable": True,
            },
        },
    ),
]


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    if not check_service():
        print(f"\nPlease start the calculator first:")
        print(f"    uvicorn services_version2.calculator_version2.main:app --reload --port 8002")
        sys.exit(1)

    print(f"Calculator OK at {CALCULATOR_URL}")
    print(f"Running {len(CASES)} test cases...\n")

    passed = 0
    failed = 0

    for name, payload in CASES:
        result = run_case(name, payload)
        print_result(name, result)
        if result.get("_error"):
            failed += 1
        else:
            passed += 1

    print(f"\n{'='*60}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(CASES)} cases")
    print(f"{'='*60}")

    client.close()


if __name__ == "__main__":
    main()
