"""Unit tests for normalization utilities."""

from app.utils.normalization import normalize_list, normalize_string


class TestNormalizeList:
    def test_basic(self):
        assert normalize_list("FREQ,PARTNER_COUNTRY,FLOW") == [
            "FLOW",
            "FREQ",
            "PARTNER_COUNTRY",
        ]

    def test_lowercased_input(self):
        assert normalize_list("freq,partner_country") == ["FREQ", "PARTNER_COUNTRY"]

    def test_deduplication(self):
        assert normalize_list("FLOW,FLOW,FREQ") == ["FLOW", "FREQ"]

    def test_whitespace_handling(self):
        assert normalize_list("  FLOW , FREQ  ") == ["FLOW", "FREQ"]

    def test_empty_string(self):
        assert normalize_list("") == []

    def test_none(self):
        assert normalize_list(None) == []

    def test_single_item(self):
        assert normalize_list("FLOW") == ["FLOW"]


class TestNormalizeString:
    def test_basic(self):
        assert normalize_string("hello") == "HELLO"

    def test_whitespace(self):
        assert normalize_string("  hello  ") == "HELLO"

    def test_none(self):
        assert normalize_string(None) is None

    def test_empty(self):
        assert normalize_string("") is None

    def test_whitespace_only(self):
        assert normalize_string("   ") is None
