"""Unit tests for filter and sort parsing."""

import pytest

from app.utils.filter_parser import parse_filters, parse_sort


class TestParseFilters:
    """Tests for parse_filters()."""

    def test_parse_single_filter(self):
        result = parse_filters(["PARTNER_COUNTRY:eq:US"])
        assert len(result) == 1
        assert result[0].field == "PARTNER_COUNTRY"
        assert result[0].operator == "eq"
        assert result[0].value == "US"

    def test_parse_multiple_filters(self):
        result = parse_filters(["PARTNER_COUNTRY:eq:US", "FLOW:eq:IMPORT"])
        assert len(result) == 2
        assert result[0].field == "PARTNER_COUNTRY"
        assert result[1].field == "FLOW"
        assert result[1].value == "IMPORT"

    def test_parse_empty_filters(self):
        assert parse_filters(None) == []
        assert parse_filters([]) == []

    def test_field_uppercased(self):
        result = parse_filters(["partner_country:eq:US"])
        assert result[0].field == "PARTNER_COUNTRY"

    def test_operator_lowercased(self):
        result = parse_filters(["FLOW:EQ:IMPORT"])
        assert result[0].operator == "eq"

    def test_all_valid_operators(self):
        for op in ["eq", "ne", "gt", "ge", "lt", "le", "in", "like"]:
            result = parse_filters([f"FIELD:{op}:val"])
            assert result[0].operator == op

    def test_invalid_operator_raises(self):
        with pytest.raises(ValueError, match="Unsupported filter operator"):
            parse_filters(["FIELD:contains:val"])

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Invalid filter format"):
            parse_filters(["BAD_FILTER"])

    def test_value_with_colon(self):
        """Value containing colons should be preserved (split on first 2 only)."""
        result = parse_filters(["FIELD:eq:value:with:colons"])
        assert result[0].value == "value:with:colons"

    def test_in_operator_value(self):
        result = parse_filters(["FLOW:in:IMPORT,EXPORT"])
        assert result[0].operator == "in"
        assert result[0].value == "IMPORT,EXPORT"


class TestParseSort:
    """Tests for parse_sort()."""

    def test_parse_sort_desc(self):
        result = parse_sort("FLOW:desc")
        assert len(result) == 1
        assert result[0].field == "FLOW"
        assert result[0].direction == "desc"

    def test_parse_sort_asc_default(self):
        result = parse_sort("FLOW")
        assert result[0].direction == "asc"

    def test_parse_sort_empty(self):
        assert parse_sort(None) == []
        assert parse_sort("") == []

    def test_field_uppercased(self):
        result = parse_sort("flow:desc")
        assert result[0].field == "FLOW"

    def test_invalid_direction_raises(self):
        with pytest.raises(ValueError, match="Invalid sort direction"):
            parse_sort("FLOW:random")

    def test_multiple_sort_fields(self):
        result = parse_sort("FLOW:desc,PARTNER_COUNTRY:asc")
        assert len(result) == 2
        assert result[0].field == "FLOW"
        assert result[1].field == "PARTNER_COUNTRY"
