import pytest
import urllib.request
import json
import uuid

URL = "http://127.0.0.1:8001/chat"


def send_query(question: str, session_id: str):
    payload = {
        "question": question,
        "session_id": session_id
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        URL,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode('utf-8'))


def get_answer(res: dict) -> str:
    return (res.get("answer") or res.get("response") or "")


# 1. FTA DV SCENARIOS
@pytest.mark.parametrize("query, is_khmer", [
    ("hi how much tax if i import a car hs 8703.22.00 cif is $10500, from china, ACFTA rate, dv=0", False),
    ("សួស្តី ខ្ញុំចង់ដឹងពន្ធនាំចូលរថយន្ត hs 8703.22.00 cif $10500 ពីប្រទេសចិន តាមអត្រា ACFTA dv=0 គិតប៉ុន្មាន?", True),
    ("can u calculate tax for 8703.22.00 china cif10500usd acfta dv 0", False),
    ("ជួយគណនាពន្ធឲ្យ 8703.22.00 ពីចិន cif10500usd acfta dv 0", True),
    ("hs code 8703.22.00, cif 10500 usd, china, acfta, dv=0 — total import tax pls", False),
    ("hs code 8703.22.00, cif 10500 usd, ចិន, acfta, dv=0 — សូមគណនាពន្ធនាំចូលសរុប", True),
])
def test_scenario_fta_dv(query, is_khmer):
    session_id = f"test_fta_dv_{uuid.uuid4()}"
    res = send_query(query, session_id)
    ans = get_answer(res)
    assert len(ans) > 0
    assert res.get("intent", "").lower() == "calculation"
    if is_khmer:
        # Check that response contains Khmer characters (verifying translation boundary)
        assert any('\u1780' <= char <= '\u17ff' for char in ans)
    else:
        assert any(x in ans.lower() for x in ["tax", "duty", "total", "pay", "usd"])


# 2. NORMAL SCENARIOS
@pytest.mark.parametrize("query, is_khmer", [
    ("need tax calc for hs code 8703.24.00, cif $40,000, importing from china", False),
    ("ត្រូវការគណនាពន្ធសម្រាប់ hs code 8703.24.00, cif $40,000 នាំចូលពីប្រទេសចិន", True),
    ("whats the import tax on 8703.32.00 cif 9180 usd coming from china no fta", False),
    ("ពន្ធនាំចូលសម្រាប់ 8703.32.00 cif 9180 usd ពីចិន គ្មាន fta គិតប៉ុន្មាន?", True),
    ("importing coffee beans from malaysia hs 0901.11.00 cif is only 86.98usd, how much tax would that be", False),
    ("នាំចូលគ្រាប់កាហ្វេពីម៉ាឡេស៊ី hs 0901.11.00 cif គ្រាន់តែ 86.98usd ពន្ធគិតប៉ុន្មាន?", True),
    ("steel parts hs 7308.90.00 from thailand cif 2884.91 usd — tax amount?", False),
    ("គ្រឿងបន្លាស់ដែក hs 7308.90.00 ពីថៃ cif 2884.91 usd — ចំនួនពន្ធប៉ុន្មាន?", True),
])
def test_scenario_normal(query, is_khmer):
    session_id = f"test_normal_{uuid.uuid4()}"
    res = send_query(query, session_id)
    ans = get_answer(res)
    assert len(ans) > 0
    assert res.get("intent", "").lower() == "calculation"
    if is_khmer:
        assert any('\u1780' <= char <= '\u17ff' for char in ans)
    else:
        assert any(x in ans.lower() for x in ["tax", "duty", "total", "pay", "usd"])


# 3. FTA DV DQ SCENARIOS
@pytest.mark.parametrize("query, is_khmer", [
    ("import tax pls — hs 8703.24.00, cif=40000usd, china, acfta, dv=0, dq 40%", False),
    ("សូមគណនាពន្ធនាំចូល — hs 8703.24.00, cif=40000usd, ចិន, acfta, dv=0, dq 40%", True),
    ("8703.33.00 from china cif 9300$ dv0 dq40% under acfta how much total tax", False),
    ("8703.33.00 ពីចិន cif 9300$ dv0 dq40% ក្រោម acfta សរុបពន្ធប៉ុន្មាន?", True),
    ("china import, hs 8703.22.00, cif $13869, acfta applies, dv=0, dq=50%, what's my total import tax", False),
    ("នាំចូលពីចិន hs 8703.22.00, cif $13869, អនុវត្តតាម acfta, dv=0, dq=50% សរុបពន្ធនាំចូលប៉ុន្មាន?", True),
    ("got a car shipment hs8703.24.00 cif40000usd from China. dv=0 dq=40%. tax?", False),
    ("មានទំនិញរថយន្តមកដល់ hs8703.24.00 cif40000usd ពីចិន dv=0 dq=40% ពន្ធប៉ុន្មាន?", True),
    ("hs 8703.33.00 cif 9300 usd china acfta dv=0 dq=40 need tax breakdown asap", False),
    ("hs 8703.33.00 cif 9300 usd ពីចិន acfta dv=0 dq=40 ត្រូវការលម្អិតពន្ធជាបន្ទាន់", True),
])
def test_scenario_fta_dv_dq(query, is_khmer):
    session_id = f"test_fta_dv_dq_{uuid.uuid4()}"
    res = send_query(query, session_id)
    ans = get_answer(res)
    assert len(ans) > 0
    assert res.get("intent", "").lower() == "calculation"
    if is_khmer:
        assert any('\u1780' <= char <= '\u17ff' for char in ans)
    else:
        assert any(x in ans.lower() for x in ["tax", "duty", "total", "pay", "usd"])


# 4. PETROLEUM SCENARIOS
@pytest.mark.parametrize("query, is_khmer", [
    ("calculating tax for petroleum import hs 2710.12.26 from vietnam, cif 393684.59 usd, dv=700, net mass 505423kg / 675789L — what's the duty+vat+atp breakdown", False),
    ("គណនាពន្ធនាំចូលប្រេងឥន្ធនៈ hs 2710.12.26 ពីវៀតណាម cif 393684.59 usd, dv=700, ទម្ងន់សុទ្ធ 505423kg / 675789L — សូមបំបែក duty+vat+atp ជាមួយគ្នា", True),
    ("vietnam petroleum shipment hs code 2710.12.26 cif393684.59 dv 700 mass505423kg vol675789l need full tax calc", False),
    ("ការដឹកជញ្ជូនប្រេងឥន្ធនៈពីវៀតណាម hs code 2710.12.26 cif393684.59 dv 700 mass505423kg vol675789l ត្រូវការគណនាពន្ធពេញលេញ", True),
])
def test_scenario_petroleum(query, is_khmer):
    session_id = f"test_petroleum_{uuid.uuid4()}"
    res = send_query(query, session_id)
    ans = get_answer(res)
    assert len(ans) > 0
    assert res.get("intent", "").lower() == "calculation"
    if is_khmer:
        assert any('\u1780' <= char <= '\u17ff' for char in ans)
    else:
        assert any(x in ans.lower() for x in ["tax", "duty", "total", "vat", "atp"])
