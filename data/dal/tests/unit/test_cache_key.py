"""Unit tests for cache key generation and query fingerprints."""

from app.schemas.query import FilterItem, NormalizedQuery, SortItem
from app.utils.hashing import compute_cache_key, compute_query_fingerprint


def _make_query(**overrides) -> NormalizedQuery:
    defaults = {
        "dataset": "trade_volume",
        "version": "1.0",
        "frequency": "M",
        "dimensions": ["FLOW", "FREQ", "PARTNER_COUNTRY"],
        "measures": ["VALUE_USD", "NETWEIGHT"],
        "period_from": "2025-Q1",
        "period_to": "2026-Q2",
        "filters": [],
        "sort": [],
        "limit": 100,
        "offset": 0,
    }
    defaults.update(overrides)
    return NormalizedQuery(**defaults)


class TestComputeCacheKey:
    def test_deterministic(self):
        q = _make_query()
        key1 = compute_cache_key(q)
        key2 = compute_cache_key(q)
        assert key1 == key2

    def test_prefix(self):
        q = _make_query()
        key = compute_cache_key(q)
        assert key.startswith("dal:cache:")

    def test_different_datasets(self):
        q1 = _make_query(dataset="trade_volume")
        q2 = _make_query(dataset="other_dataset")
        assert compute_cache_key(q1) != compute_cache_key(q2)

    def test_different_limits(self):
        q1 = _make_query(limit=100)
        q2 = _make_query(limit=200)
        assert compute_cache_key(q1) != compute_cache_key(q2)

    def test_dimension_order_irrelevant(self):
        """Dimensions are sorted before hashing, so order shouldn't matter."""
        q1 = _make_query(dimensions=["FLOW", "FREQ"])
        q2 = _make_query(dimensions=["FREQ", "FLOW"])
        assert compute_cache_key(q1) == compute_cache_key(q2)

    def test_identity_changes_key(self):
        q = _make_query()
        key_public = compute_cache_key(q)
        key_private = compute_cache_key(q, include_identity="client_a")
        assert key_public != key_private

    def test_different_identities(self):
        q = _make_query()
        key_a = compute_cache_key(q, include_identity="client_a")
        key_b = compute_cache_key(q, include_identity="client_b")
        assert key_a != key_b

    def test_filters_affect_key(self):
        q1 = _make_query(filters=[])
        q2 = _make_query(
            filters=[FilterItem(field="FLOW", operator="eq", value="IMPORT")]
        )
        assert compute_cache_key(q1) != compute_cache_key(q2)

    def test_filter_order_irrelevant(self):
        f1 = FilterItem(field="FLOW", operator="eq", value="IMPORT")
        f2 = FilterItem(field="PARTNER_COUNTRY", operator="eq", value="US")
        q1 = _make_query(filters=[f1, f2])
        q2 = _make_query(filters=[f2, f1])
        assert compute_cache_key(q1) == compute_cache_key(q2)


class TestComputeQueryFingerprint:
    def test_returns_string(self):
        q = _make_query()
        fp = compute_query_fingerprint(q)
        assert isinstance(fp, str)

    def test_length(self):
        q = _make_query()
        fp = compute_query_fingerprint(q)
        assert len(fp) == 16

    def test_deterministic(self):
        q = _make_query()
        assert compute_query_fingerprint(q) == compute_query_fingerprint(q)
