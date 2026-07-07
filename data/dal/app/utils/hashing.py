"""Hashing utilities for cache keys and query fingerprints."""

from __future__ import annotations

import hashlib
import json

from app.schemas.query import NormalizedDatasetInfoQuery, NormalizedQuery


def compute_cache_key(query: NormalizedQuery | NormalizedDatasetInfoQuery, *, include_identity: str | None = None) -> str:
    """
    Build a deterministic cache key from a normalized query.

    The key is a SHA-256 hex digest of the canonical JSON representation.
    For public datasets the key is shared; for private datasets the caller
    identity is mixed in to prevent cross-tenant cache leaks.
    """
    parts: dict = {
        "dataset": query.dataset,
        "version": query.version
    }
    
    if isinstance(query, NormalizedQuery):
        parts.update({
            "frequency": query.frequency,
            "dimensions": sorted(query.dimensions),
            "measures": sorted(query.measures),
            # "start_period": query.start_period,
            # "end_period": query.end_period,
            "filters": [
                {"field": f.field, "op": f.operator, "val": f.value}
                for f in sorted(query.filters, key=lambda f: (f.field, f.operator, f.value))
            ],
            "sort": [
                {"field": s.field, "dir": s.direction}
                for s in query.sort
            ],
            "limit": query.limit,
            "offset": query.offset,
        })
    if include_identity:
        parts["identity"] = include_identity

    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"dal:cache:{digest}"


def compute_query_fingerprint(query: NormalizedQuery | NormalizedDatasetInfoQuery) -> str:
    """Short fingerprint (first 16 hex chars) for audit logs."""
    full = compute_cache_key(query)
    # Strip prefix and take first 16 chars of the hash
    return full.replace("dal:cache:", "")[:16]
