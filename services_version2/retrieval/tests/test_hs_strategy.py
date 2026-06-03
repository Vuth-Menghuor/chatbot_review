"""Tests for HS strategy behavior."""

from services_version2.retrieval.core.hs_code_strategy import select_hs_documents


def _doc(hs_code: str, score: float):
    return {
        "id": hs_code,
        "score": score,
        "content": f"HS {hs_code}",
        "metadata": {"hs_code": hs_code, "description": "sample"},
    }


def test_best_mode_returns_single_result():
    docs = [_doc("8471.30.20", 0.72), _doc("8471.30.90", 0.71), _doc("8517.12.00", 0.80)]
    result = select_hs_documents("laptop", docs, mode="best")
    assert len(result.documents) == 1
    assert result.heading_4_digit == "8471"


def test_compare_mode_requires_codes():
    docs = [_doc("3917.23.00", 0.9)]
    result = select_hs_documents("pvc pipe", docs, mode="compare", compare_codes=[])
    assert result.missing_parameters == ["compare_codes"]


def test_select_mode_requires_selected_code():
    docs = [_doc("3917.23.00", 0.9)]
    result = select_hs_documents("pvc pipe", docs, mode="select", selected_code=None)
    assert result.missing_parameters == ["selected_code"]
