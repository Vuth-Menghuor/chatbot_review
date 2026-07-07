"""
Main query endpoint — GET /v1/query/{dataset}

This is the primary data access endpoint. It:
1. Authenticates the caller
2. Rate limiting enforced by SlowAPI middleware (per x-api-key)
3. Resolves dataset + version
4. Authorizes access
5. Validates query parameters against the dataset concept
6. Executes the query (with caching)
7. Logs the audit record
8. Returns the structured response
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Query, Request

from app.api.deps import AuthClient, MetadataSession, OperationalSession
from app.core.config import get_settings
from app.core.errors import DALError, ErrorCode
from app.core.rate_limit import limiter
from app.schemas.query import NormalizedQuery
from app.schemas.response import (
    CacheInfo,
    ErrorResponse,
    MetaInfo,
    PaginationInfo,
    PeriodInfo,
    QueryResponse,
)
from app.services import audit_service, dataset_service, metadata_service, query_service
from app.utils.filter_parser import parse_filters, parse_sort
from app.utils.hashing import compute_query_fingerprint
from app.utils.normalization import normalize_list, normalize_string

router = APIRouter(prefix="/v1", tags=["Query"])


@router.get(
    "/query/{dataset}",
    summary="Execute a governed data query",
    description=(
        "Query a dataset using metadata-driven dimensions, measures, filters, and period ranges. "
        "All fields are validated against the dataset concept. No raw SQL is accepted."
    ),
    response_model=QueryResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Validation error"},
        401: {"model": ErrorResponse, "description": "Authentication error"},
        403: {"model": ErrorResponse, "description": "Authorization error"},
        404: {"model": ErrorResponse, "description": "Dataset not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal error"},
    },
)
@limiter.limit(
    f"{get_settings().default_rate_limit_per_minute}/minute"
)
async def query_dataset(
    request: Request,
    dataset: str,
    client: AuthClient,
    meta_session: MetadataSession,
    ops_session: OperationalSession,
    dimensions: str = Query(
        ...,
        description="Comma-separated dimension codes, e.g. FREQ,PARTNER_COUNTRY,FLOW",
        examples=["FREQ,PARTNER_COUNTRY,FLOW"],
    ),
    measures: str = Query(
        ...,
        description="Comma-separated measure codes, e.g. VALUE_USD,NETWEIGHT",
        examples=["VALUE_USD,NETWEIGHT"],
    ),
    version: str | None = Query(
        None,
        description="Dataset version. Defaults to the default version if omitted.",
        examples=["1.0"],
    ),
    start_period: str | None = Query(
        None,
        description="Start period, e.g. 2025, 2025-01, 2025-Q1",
        examples=["2025-Q1"],
        alias="start-period",
    ),
    end_period: str | None = Query(
        None,
        description="End period, e.g. 2026, 2026-06, 2026-Q2",
        examples=["2026-Q2"],
        alias="end-period",
    ),
    period: str | None = Query(
        None,
        description=(
            "Period range e.g. 2026, 2025-2026, 2026-Q1"
            "Overrides start_period and end_period if provided."
        ),
        examples=["2025-2026"],
    ),
    frequency: str | None = Query(
        None,
        description="Frequency code: A, S, Q, M. Uses dataset default if omitted.",
        examples=["M"],
    ),
    filter: list[str] | None = Query(
        None,
        description="Repeatable filter in FIELD:operator:value format",
        examples=["PARTNER_COUNTRY:eq:US"],
    ),
    sort: str | None = Query(
        None,
        description="Sort directive in FIELD:direction format",
        examples=["FLOW:desc"],
    ),
    limit: int = Query(
        100,
        ge=1,
        description="Max rows to return (default 100, max 10000)",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of rows to skip",
    ),
):
    """Execute a governed query against a dataset."""
    settings = get_settings()
    request_id = getattr(request.state, "request_id", "unknown")
    start_time = time.perf_counter()

    # Audit context
    audit_kwargs: dict = {
        "request_id": request_id,
        "client_id": client.client_id,
        "dataset": dataset,
    }

    try:
        # Rate limiting is handled by SlowAPI middleware (keyed by x-api-key)

        # --- Resolve dataset ---
        ds = await dataset_service.get_dataset(dataset, meta_session)

        # --- Resolve version ---
        ds_version = await dataset_service.resolve_version(dataset, version, meta_session)
        audit_kwargs["dataset_version"] = ds_version.version

        # --- Authorize ---
        from app.services import auth_service

        await auth_service.authorize_dataset(client, ds)

        # --- Load concept ---
        concept = await dataset_service.load_concept(dataset, ds_version.version, meta_session)

        # --- Parse and normalize inputs ---
        parsed_dims = normalize_list(dimensions)
        parsed_measures = normalize_list(measures)
        resolved_freq = normalize_string(frequency) or concept.frequency.default

        # Clamp limit
        clamped_limit = min(limit, settings.max_query_limit)

        # Parse filters and sort
        try:
            parsed_filters = parse_filters(filter)
        except ValueError as exc:
            raise DALError(ErrorCode.INVALID_FILTER, str(exc)) from exc

        try:
            parsed_sort = parse_sort(sort)
        except ValueError as exc:
            raise DALError(ErrorCode.INVALID_SORT, str(exc)) from exc

        # Build normalized query
        normalized = NormalizedQuery(
            dataset=dataset,
            version=ds_version.version,
            frequency=resolved_freq,
            dimensions=parsed_dims,
            measures=parsed_measures,
            start_period=start_period,
            end_period=end_period,
            period=period,
            filters=parsed_filters,
            sort=parsed_sort,
            limit=clamped_limit,
            offset=offset,
        )

        # --- Validate against concept ---
        query_service.validate_query_against_concept(normalized, concept)

        # --- Cache policy ---
        cache_policy = await metadata_service.get_cache_policy(ds.dataset_id, meta_session)
        cache_enabled = cache_policy.enabled if cache_policy else False
        cache_ttl = cache_policy.ttl_seconds if cache_policy else 300
        
        # Disable cache for debugging purposes
        # cache_enabled = False
        # cache_ttl = 300

        # --- Execute ---
        rows, cache_hit = await query_service.execute_query(
            normalized,
            concept,
            ops_session,
            cache_enabled=cache_enabled,
            cache_ttl=cache_ttl,
            is_public=ds.is_public,
            client_id=client.client_id,
        )

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # --- Audit (success) ---
        fingerprint = compute_query_fingerprint(normalized)
        await audit_service.write_audit_log(
            meta_session,
            **audit_kwargs,
            status_code=200,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            query_fingerprint=fingerprint,
            request_params={
                "dimensions": parsed_dims,
                "measures": parsed_measures,
                "frequency": resolved_freq,
                "period": period or f"{start_period}-{end_period}",
                "limit": clamped_limit,
                "offset": offset,
            },
        )
        
        period_info = {"period": period} if period else {"from": start_period, "to": end_period}

        # --- Build response ---
        return QueryResponse(
            request_id=request_id,
            dataset=dataset,
            version=ds_version.version,
            frequency=resolved_freq,
            dimensions=parsed_dims,
            measures=parsed_measures,
            period=PeriodInfo(**period_info),
            pagination=PaginationInfo(limit=clamped_limit, offset=offset),
            cache=CacheInfo(hit=cache_hit, ttl_seconds=cache_ttl if cache_enabled else None),
            meta=MetaInfo(latency_ms=latency_ms),
            row_count=len(rows),
            data=rows,
        )

    except DALError:
        # Re-raise DAL errors — middleware handles them
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        raise
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        # Audit (failure)
        await audit_service.write_audit_log(
            meta_session,
            **audit_kwargs,
            status_code=500,
            latency_ms=latency_ms,
            error_summary=str(exc)[:500],
        )
        raise DALError(ErrorCode.INTERNAL_ERROR, "An unexpected error occurred") from exc
