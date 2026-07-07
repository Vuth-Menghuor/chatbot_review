"""
Prometheus metrics for Orchestrator v2 Service
Tracks query counts, durations, service errors, and cache hit rates.
"""

from prometheus_client import REGISTRY, Counter, Histogram


def _counter(name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> Counter:
    """Return an existing counter if already registered (e.g. during test re-import)."""
    for collector, names in REGISTRY._collector_to_names.items():
        if name in names and isinstance(collector, Counter):
            return collector
    return Counter(name, documentation, list(labelnames))


def _histogram(name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> Histogram:
    for collector, names in REGISTRY._collector_to_names.items():
        if name in names and isinstance(collector, Histogram):
            return collector
    return Histogram(name, documentation, list(labelnames))


# Query Metrics
QUERY_COUNT = _counter(
    "gdce_query_count_total",
    "Total number of queries processed",
    ("intent", "status"),
)

QUERY_DURATION = _histogram(
    "gdce_query_duration_seconds",
    "Time taken to process queries",
    ("intent",),
)

# Service Error Metrics
SERVICE_ERRORS = _counter(
    "gdce_service_errors_total",
    "Total number of downstream service errors",
    ("service_name", "error_type"),
)

# Cache Metrics
CACHE_HITS = _counter(
    "gdce_cache_hits_total",
    "Total cache hits",
    ("cache_level",),
)

CACHE_MISSES = _counter(
    "gdce_cache_misses_total",
    "Total cache misses",
    ("cache_level",),
)

def record_query(intent: str, status: str, duration_sec: float):
    """Record a completed query's count and duration."""
    # Ensure intent isn't None
    intent_str = str(intent) if intent else "unknown"
    status_str = str(status) if status else "unknown"
    
    QUERY_COUNT.labels(intent=intent_str, status=status_str).inc()
    QUERY_DURATION.labels(intent=intent_str).observe(duration_sec)

def record_service_error(service_name: str, error_type: str):
    """Record a downstream service error."""
    SERVICE_ERRORS.labels(service_name=service_name, error_type=error_type).inc()

def record_cache_hit(cache_level: str = "memory"):
    """Record a cache hit."""
    CACHE_HITS.labels(cache_level=cache_level).inc()

def record_cache_miss(cache_level: str = "memory"):
    """Record a cache miss."""
    CACHE_MISSES.labels(cache_level=cache_level).inc()
