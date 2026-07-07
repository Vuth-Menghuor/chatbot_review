"""Unit tests for the metadata-driven SQL builder."""

import pytest

from app.core.errors import DALError
from app.schemas.metadata import DatasetConcept
from app.schemas.query import FilterItem, NormalizedQuery, SortItem
from app.services.sql_builder import build_query
from tests.fixtures.sample_concept import TRADE_VOLUME_CONCEPT


@pytest.fixture
def concept():
    return DatasetConcept.model_validate(TRADE_VOLUME_CONCEPT)


def _make_query(**overrides) -> NormalizedQuery:
    defaults = {
        "dataset": "trade_volume",
        "version": "1.0",
        "frequency": "M",
        "dimensions": ["PARTNER_COUNTRY", "FLOW"],
        "measures": ["VALUE_USD", "NETWEIGHT"],
        "start_period": None,
        "end_period": None,
        "filters": [],
        "sort": [],
        "limit": 100,
        "offset": 0,
    }
    defaults.update(overrides)
    return NormalizedQuery(**defaults)


class TestBuildQuery:
    def test_basic_select(self, concept):
        q = _make_query()
        result = build_query(q, concept)
        assert "SELECT" in result.sql
        assert '"PERIOD"' in result.sql
        assert '"FREQ"' in result.sql
        assert '"PARTNER_COUNTRY"' in result.sql
        assert '"FLOW"' in result.sql
        assert 'SUM(td.value_usd) AS "VALUE_USD"' in result.sql
        assert 'SUM(td.net_weight) AS "NETWEIGHT"' in result.sql

    def test_from_clause(self, concept):
        q = _make_query()
        result = build_query(q, concept)
        assert "FROM trade_data as td" in result.sql

    def test_joins_included(self, concept):
        q = _make_query()
        result = build_query(q, concept)
        assert "INNER JOIN countries as c" in result.sql
        assert "INNER JOIN mode_of_transport as mot" in result.sql

    def test_group_by(self, concept):
        q = _make_query()
        result = build_query(q, concept)
        assert "GROUP BY" in result.sql

    def test_limit_offset(self, concept):
        q = _make_query(limit=50, offset=10)
        result = build_query(q, concept)
        assert "LIMIT :p_limit OFFSET :p_offset" in result.sql
        assert result.params["p_limit"] == 50
        assert result.params["p_offset"] == 10

    def test_frequency_in_select(self, concept):
        """Frequency should appear as a literal in SELECT, not as a WHERE filter."""
        q = _make_query(frequency="Q")
        result = build_query(q, concept)
        assert "'Q' AS \"FREQ\"" in result.sql
        # Frequency is NOT a DB column, so no p_freq param
        assert "p_freq" not in result.params

    def test_period_expressions_by_frequency(self, concept):
        """Monthly frequency should use month-based period expression."""
        q = _make_query(frequency="M")
        result = build_query(q, concept)
        assert "LPAD(td.ref_month::TEXT, 2, '0')" in result.sql

    def test_annual_frequency(self, concept):
        q = _make_query(frequency="A")
        result = build_query(q, concept)
        assert "td.ref_year::TEXT" in result.sql

    def test_filter_eq(self, concept):
        q = _make_query(
            filters=[FilterItem(field="PARTNER_COUNTRY", operator="eq", value="US")]
        )
        result = build_query(q, concept)
        assert "c.country_code  =  :p_filter_0" in result.sql
        assert result.params["p_filter_0"] == "US"

    def test_filter_in(self, concept):
        q = _make_query(
            filters=[FilterItem(field="FLOW", operator="in", value="IMPORT,EXPORT")]
        )
        result = build_query(q, concept)
        assert "td.flow IN" in result.sql
        assert ":p_filter_0_0" in result.sql

    def test_sort_dimension(self, concept):
        q = _make_query(sort=[SortItem(field="FLOW", direction="desc")])
        result = build_query(q, concept)
        assert "ORDER BY td.flow DESC" in result.sql

    def test_sort_measure(self, concept):
        q = _make_query(sort=[SortItem(field="VALUE_USD", direction="asc")])
        result = build_query(q, concept)
        assert "ORDER BY SUM(td.value_usd) ASC" in result.sql

    def test_unknown_dimension_raises(self, concept):
        q = _make_query(dimensions=["UNKNOWN_DIM", "FLOW"])
        with pytest.raises(DALError) as exc_info:
            build_query(q, concept)
        assert exc_info.value.error_code.value == "INVALID_DIMENSION"

    def test_unknown_measure_raises(self, concept):
        q = _make_query(measures=["UNKNOWN_MEASURE"])
        with pytest.raises(DALError) as exc_info:
            build_query(q, concept)
        assert exc_info.value.error_code.value == "INVALID_MEASURE"

    def test_invalid_frequency_raises(self, concept):
        q = _make_query(frequency="X")
        with pytest.raises(DALError) as exc_info:
            build_query(q, concept)
        assert exc_info.value.error_code.value == "INVALID_FILTER"

    def test_unknown_filter_field_raises(self, concept):
        q = _make_query(
            filters=[FilterItem(field="BAD_FIELD", operator="eq", value="X")]
        )
        with pytest.raises(DALError) as exc_info:
            build_query(q, concept)
        assert exc_info.value.error_code.value == "INVALID_FILTER"

    def test_unknown_sort_field_raises(self, concept):
        q = _make_query(sort=[SortItem(field="BAD_FIELD", direction="asc")])
        with pytest.raises(DALError) as exc_info:
            build_query(q, concept)
        assert exc_info.value.error_code.value == "INVALID_SORT"

    @pytest.mark.integration
    def test_period_from_filter(self, concept):
        q = _make_query(start_period="2025")
        result = build_query(q, concept)
        assert "td.ref_year >= '2025'" in result.sql

    @pytest.mark.integration
    def test_period_to_filter(self, concept):
        q = _make_query(end_period="2026")
        result = build_query(q, concept)
        assert "td.ref_year <= '2026'" in result.sql

    @pytest.mark.integration
    def test_period_quarterly(self, concept):
        q = _make_query(start_period="2025-Q1")
        result = build_query(q, concept)
        assert "'2025'" in result.sql
        assert "'01'" in result.sql

    @pytest.mark.integration
    def test_invalid_period_format_raises(self, concept):
        q = _make_query(start_period="invalid-period")
        with pytest.raises(DALError) as exc_info:
            build_query(q, concept)
        assert exc_info.value.error_code.value == "INVALID_PERIOD"

    def test_measure_with_unit(self, concept):
        """QUANTITY measure has a unit field that should be included."""
        q = _make_query(measures=["QUANTITY"])
        result = build_query(q, concept)
        assert 'SUM(COALESCE(td.quantity, td.net_weight)) AS "QUANTITY"' in result.sql
        assert '"UNIT"' in result.sql

    def test_no_sql_injection_in_filter_value(self, concept):
        """Values are parameterized, not concatenated into SQL."""
        q = _make_query(
            filters=[
                FilterItem(
                    field="FLOW",
                    operator="eq",
                    value="'; DROP TABLE trade_data; --",
                )
            ]
        )
        result = build_query(q, concept)
        # The malicious value should be in params, NOT in the SQL text
        assert "DROP TABLE" not in result.sql
        assert result.params["p_filter_0"] == "'; DROP TABLE trade_data; --"
