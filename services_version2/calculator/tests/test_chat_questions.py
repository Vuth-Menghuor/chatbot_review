#!/usr/bin/env python3
"""
Chat Question Automated Tester
================================
Sends each chat question to the orchestrator (/query endpoint) and checks
that the response matches expectations. Flags any failures.

Run while both services are running:
    python test_chat_questions.py
"""

import json
import re
import sys
from datetime import datetime

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)

ORCHESTRATOR_URL = "http://127.0.0.1:8001"
TIMEOUT = 60.0
client = httpx.Client(timeout=TIMEOUT)

OK = "[PASS]"
FAIL = "[FAIL]"


def check_service() -> bool:
    try:
        r = client.get(f"{ORCHESTRATOR_URL}/health")
        return r.status_code == 200
    except Exception as e:
        print(f"Orchestrator not reachable at {ORCHESTRATOR_URL}: {e}")
        return False


def send_question(question: str) -> dict:
    """POST question to orchestrator /query endpoint."""
    try:
        r = client.post(
            f"{ORCHESTRATOR_URL}/query",
            json={"question": question, "session_id": f"test-{datetime.now().timestamp()}"},
        )
        if r.status_code != 200:
            return {"_error": True, "status": r.status_code, "detail": r.text}
        return r.json()
    except Exception as e:
        return {"_error": True, "exception": str(e)}


def _contains(text: str, *phrases: str) -> tuple[bool, str]:
    lowered = text.lower()
    for p in phrases:
        if p.lower() not in lowered:
            return False, f"missing phrase: '{p}'"
    return True, ""


def _rate_near(text: str, label: str, expected: float, tol: float = 0.5) -> tuple[bool, str]:
    """Look for a rate value near a label or anywhere in the text.
    Matches both 'Rate: 7.00' and '7.00%' formats."""
    # Search near the label first (with optional %)
    pattern = re.compile(
        rf"{re.escape(label)}.*?([\d.,]+)\s*%?",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(text):
        try:
            val = float(m.group(1).replace(",", ""))
            if abs(val - expected) <= tol:
                return True, f"{val:.2f}%"
        except ValueError:
            pass
    # Fallback: search any number + % in text
    for m in re.finditer(r"([\d.,]+)\s*%", text):
        try:
            val = float(m.group(1).replace(",", ""))
            if abs(val - expected) <= tol:
                return True, f"{val:.2f}%"
        except ValueError:
            pass
    # Fallback 2: search table rows like "|  7.00 |"
    for m in re.finditer(r"\|\s*([\d.,]+)\s*\|", text):
        try:
            val = float(m.group(1).replace(",", ""))
            if abs(val - expected) <= tol:
                return True, f"{val:.2f}%"
        except ValueError:
            pass
    return False, f"expected {expected:.2f}% near '{label}'"


def run_test(name: str, question: str, checks: list) -> tuple[bool, list[str]]:
    """Run one test case. Returns (passed, list_of_issue_strings)."""
    result = send_question(question)
    issues = []

    if result.get("_error"):
        issues.append(f"HTTP error: {result}")
        return False, issues

    status = result.get("status", "unknown")
    intent = result.get("intent", "unknown")
    answer = result.get("answer", "")
    latency = result.get("latency_ms", 0)

    if status != "completed":
        issues.append(f"status={status} (expected completed)")

    if intent != "calculation":
        issues.append(f"intent={intent} (expected calculation)")

    if not answer or len(answer) < 50:
        issues.append("answer too short or empty")
        return False, issues

    for check_fn in checks:
        ok, msg = check_fn(answer)
        if not ok:
            issues.append(msg)

    if issues:
        print(f"  {FAIL} {name} ({latency:.0f}ms) — {len(issues)} issue(s)")
        for i in issues:
            print(f"       - {i}")
    else:
        print(f"  {OK} {name} ({latency:.0f}ms)")

    return len(issues) == 0, issues


# ---------------------------------------------------------------------------
# TEST DEFINITIONS
# ---------------------------------------------------------------------------
TESTS = [
    # --- 1. NORMAL IMPORT — COP + SOP + VOP ---
    (
        "Normal Import — Spirits (COP+SOP+VOP)",
        "calculate import tax for 200 liters of whisky from the UK, HS code 2208.90.10, CIF value $5000",
        [
            lambda t: _contains(t, "COP", "SOP", "VOP"),
            lambda t: _rate_near(t, "COP", 35.0),
            lambda t: _rate_near(t, "SOP", 35.0),
            lambda t: _rate_near(t, "VOP", 10.0),
            lambda t: _contains(t, "total", "KHR"),
        ],
    ),
    (
        "Normal Import — Cigarettes (COP+SOP+VOP)",
        "what is the import tax for 10,000 cigarettes from Indonesia, HS 2402.20.10, CIF $8000",
        [
            lambda t: _contains(t, "COP", "SOP", "VOP"),
            lambda t: _rate_near(t, "COP", 7.0),
            lambda t: _rate_near(t, "SOP", 20.0),
            lambda t: _rate_near(t, "VOP", 10.0),
        ],
    ),
    (
        "Normal Import — Plastic (COP+SOP+VOP)",
        "i want to import 5000 plastic food containers from China, HS 3923.10.10, CIF value $15000. calculate tax",
        [
            lambda t: _contains(t, "COP", "SOP", "VOP"),
            lambda t: _rate_near(t, "COP", 15.0),
            lambda t: _rate_near(t, "SOP", 10.0),
            lambda t: _rate_near(t, "VOP", 10.0),
        ],
    ),

    # --- 2. NORMAL IMPORT — ZERO SOP ---
    (
        "Normal Import — Zero SOP (laptops)",
        "importing 100 laptops from the USA, HS code 8471.30.20, CIF value $50000. what is the total tax",
        [
            lambda t: _contains(t, "COP", "SOP", "VOP"),
            lambda t: _rate_near(t, "COP", 7.0),
            lambda t: _rate_near(t, "SOP", 0.0),
            lambda t: _rate_near(t, "VOP", 10.0),
            lambda t: _contains(t, "SOP", "0 KHR") if "SOP" in t else (False, "SOP amount not shown as 0"),
        ],
    ),
    (
        "Normal Import — Zero SOP (phones)",
        "calculate customs tax for 200 mobile phones from China, HS 8517.62.10, CIF $25000",
        [
            lambda t: _contains(t, "COP", "SOP", "VOP"),
            lambda t: _rate_near(t, "COP", 0.0),
            lambda t: _rate_near(t, "SOP", 0.0),
            lambda t: _rate_near(t, "VOP", 10.0),
        ],
    ),

    # --- 3. FTA/DV CASE ---
    (
        "FTA/DV — Laptops from ASEAN",
        "importing 50 laptops from Vietnam, HS 8471.30.20, CIF $20000. we have ACFTA certificate. calculate tax",
        [
            lambda t: _contains(t, "COP", "VOP"),
            lambda t: _contains(t, "FTA", "preferential"),
            lambda t: _rate_near(t, "VOP", 10.0),
        ],
    ),
    (
        "FTA/DV — Rubber from ASEAN",
        "importing natural rubber sheets from Vietnam, HS 4001.21.10, CIF $8000. ACFTA applies",
        [
            lambda t: _contains(t, "COP", "VOP"),
            lambda t: _contains(t, "FTA"),
        ],
    ),

    # --- 4. FTA/DV/DQ CASE ---
    (
        "FTA/DV/DQ — Spirits with DQ 0.85",
        "my company has a DQ agreement. importing whisky from Vietnam under ACFTA, HS 2208.90.10, CIF $5000, DQ factor 0.85",
        [
            lambda t: _contains(t, "COP", "SOP", "VOP"),
            lambda t: _contains(t, "DQ", "ACFTA"),
            lambda t: _contains(t, "0.85"),
        ],
    ),
    (
        "FTA/DV/DQ — Plastic with DQ 0.90",
        "calculate import tax for plastic containers from Thailand with ACFTA and DQ factor 0.90, HS 3923.10.10, CIF $10000",
        [
            lambda t: _contains(t, "COP", "SOP", "VOP"),
            lambda t: _contains(t, "DQ", "ACFTA"),
        ],
    ),

    # --- 5. RUBBER EXPORT ---
    (
        "Rubber Export — Natural rubber",
        "exporting 15 tons of natural rubber to China, HS 4001.21.10, declared value $1200 per ton",
        [
            lambda t: _contains(t, "export", "ETR"),
        ],
    ),
    (
        "Rubber Export — Smoked sheets",
        "what is the export tax for 8 tons of smoked rubber sheets to Vietnam, HS 4001.22.10, DV $1200 per ton",
        [
            lambda t: _contains(t, "export", "ETR"),
        ],
    ),

    # --- 6. EXEMPTIONS ---
    (
        "Exemption — QIP",
        "our company is QIP. importing construction equipment from Japan, HS 4202.92.10, CIF $50000",
        [
            lambda t: _contains(t, "exemption", "QIP"),
            lambda t: ("0 KHR" in t or "0.00" in t or "exempt" in t.lower())
            and (True, "")
            or (False, "tax not shown as exempt/zero"),
        ],
    ),
    (
        "Exemption — SEZ",
        "we operate in the SEZ. importing garment materials from China, HS 6203.42.10, CIF $30000",
        [
            lambda t: _contains(t, "exemption", "SEZ"),
            lambda t: ("0 KHR" in t or "0.00" in t or "exempt" in t.lower())
            and (True, "")
            or (False, "tax not shown as exempt/zero"),
        ],
    ),
    (
        "Exemption — Diplomatic",
        "embassy importing office laptops from USA, HS 8471.30.20, CIF $5000. diplomatic shipment",
        [
            lambda t: _contains(t, "exemption", "diplomatic"),
            lambda t: ("0 KHR" in t or "0.00" in t or "exempt" in t.lower())
            and (True, "")
            or (False, "tax not shown as exempt/zero"),
        ],
    ),
    (
        "Exemption — NGO",
        "UNICEF importing medical supplies for flood relief, HS 3004.90.10, CIF $30000",
        [
            lambda t: _contains(t, "exemption", "NGO", "humanitarian"),
            lambda t: ("0 KHR" in t or "0.00" in t or "exempt" in t.lower())
            and (True, "")
            or (False, "tax not shown as exempt/zero"),
        ],
    ),
    (
        "Exemption — Educational",
        "university importing lab equipment from Germany, HS 8517.62.10, CIF $8500",
        [
            lambda t: _contains(t, "exemption", "educational"),
            lambda t: ("0 KHR" in t or "0.00" in t or "exempt" in t.lower())
            and (True, "")
            or (False, "tax not shown as exempt/zero"),
        ],
    ),
    (
        "Exemption — Medical",
        "public hospital importing donated MRI machines, HS 3004.90.10, CIF $250000",
        [
            lambda t: _contains(t, "exemption", "medical"),
            lambda t: ("0 KHR" in t or "0.00" in t or "exempt" in t.lower())
            and (True, "")
            or (False, "tax not shown as exempt/zero"),
        ],
    ),
    (
        "Exemption — Passenger",
        "i am bringing personal electronics worth $1200 from USA in my luggage. do i pay duty",
        [
            lambda t: _contains(t, "exemption", "passenger"),
            lambda t: ("0 KHR" in t or "0.00" in t or "exempt" in t.lower())
            and (True, "")
            or (False, "tax not shown as exempt/zero"),
        ],
    ),

    # --- 7. EDGE CASES ---
    (
        "Edge — Mass-based DV per ton",
        "importing 10 tons of frozen fish fillets from Vietnam, HS 0304.89.10, declared value $800 per ton",
        [
            lambda t: _contains(t, "COP", "VOP"),
            lambda t: _contains(t, "per ton", "DV"),
        ],
    ),
    (
        "Edge — Input in KHR",
        "calculate import tax for rice from Cambodia, HS 1006.10.10, CIF value 50000000 KHR",
        [
            lambda t: _contains(t, "COP", "VOP"),
            lambda t: ("exchange rate" not in t.lower() or "USD" not in t)
            and (True, "")
            or (False, "unnecessary USD/exchange-rate step shown"),
        ],
    ),
    (
        "Edge — FTA without cert type",
        "importing laptops from Vietnam, HS 8471.30.20, CIF $10000. we have FTA",
        [
            lambda t: _contains(t, "COP", "VOP"),
            lambda t: _contains(t, "FTA"),
        ],
    ),

    # --- 8. PETROLEUM (expected to fail if HS not seeded) ---
    (
        "Petroleum — Diesel fuel (expected: may fail if HS not seeded)",
        "importing 50000 liters of diesel from Singapore, HS 2710.19.10, declared value $550 per ton, net mass 42 tons",
        [
            lambda t: _contains(t, "CPP", "SPP", "VPP"),
            lambda t: _contains(t, "Phase", "DPP"),
        ],
    ),
]


def main():
    if not check_service():
        print(f"\nPlease start the orchestrator first:")
        print(f"    uvicorn services_version2.orchestrator_version2.main:app --reload --port 8001")
        sys.exit(1)

    print(f"Orchestrator OK at {ORCHESTRATOR_URL}")
    print(f"Running {len(TESTS)} chat tests...\n")

    passed = 0
    failed = 0
    flagged = []

    for name, question, checks in TESTS:
        print(f"\n{'-'*60}")
        print(f"Question: {question}")
        ok, issues = run_test(name, question, checks)
        if ok:
            passed += 1
        else:
            failed += 1
            flagged.append((name, question, issues))

    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed} passed, {failed} failed out of {len(TESTS)} tests")
    print(f"{'='*60}")

    if flagged:
        print(f"\n{'='*60}")
        print("FLAGGED TESTS (need attention):")
        print(f"{'='*60}")
        for name, question, issues in flagged:
            print(f"\n  • {name}")
            print(f"    Q: {question}")
            for i in issues:
                print(f"    Issue: {i}")

    client.close()


if __name__ == "__main__":
    main()
