"""
Query orchestration service.

Coordinates the full query lifecycle: validation → cache check →
SQL build → execution → cache store → response assembly.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DALError, ErrorCode
from app.core.logging import get_logger
from app.core.config import get_settings
from app.schemas.metadata import DatasetConcept, Metadata
from app.schemas.query import NormalizedDatasetInfoQuery, NormalizedQuery
from app.schemas.response import CodeConcept, ColumnInfo
from app.services import cache_service, sql_builder
from app.utils.hashing import compute_cache_key
from copy import deepcopy

logger = get_logger(__name__)
settings = get_settings()


def validate_query_against_concept(
    query: NormalizedQuery,
    concept: DatasetConcept,
) -> None:
    """
    Validate that all requested fields exist in the dataset concept.
    Fail-closed: reject anything not explicitly allowed.
    """
    valid_dims = {d.code for d in concept.dimensions} | {concept.frequency.code}
    valid_measures = {m.code for m in concept.measures}

    # Validate dimensions
    for dim in query.dimensions:
        if dim not in valid_dims:
            raise DALError(
                ErrorCode.INVALID_DIMENSION,
                f"Dimension '{dim}' is not defined in dataset concept. "
                f"Valid dimensions: {', '.join(sorted(valid_dims))}",
            )

    # Validate measures
    for meas in query.measures:
        if meas not in valid_measures:
            raise DALError(
                ErrorCode.INVALID_MEASURE,
                f"Measure '{meas}' is not defined in dataset concept. "
                f"Valid measures: {', '.join(sorted(valid_measures))}",
            )

    # Validate frequency
    # if query.frequency not in concept.frequency.valid:
    #     raise DALError(
    #         ErrorCode.INVALID_FREQUENCY,
    #         f"Frequency '{query.frequency}' is not valid. "
    #         f"Valid values: {', '.join(concept.frequency.valid)}",
    #     )

    # Validate filter fields
    for f in query.filters:
        if f.field not in valid_dims:
            raise DALError(
                ErrorCode.INVALID_FILTER,
                f"Cannot filter on '{f.field}'. "
                f"Valid filter fields: {', '.join(sorted(valid_dims))}",
            )

    # Validate sort fields
    all_valid_sort = valid_dims | valid_measures | {concept.period.code}
    for s in query.sort:
        if s.field not in all_valid_sort:
            raise DALError(
                ErrorCode.INVALID_SORT,
                f"Cannot sort on '{s.field}'. "
                f"Valid sort fields: {', '.join(sorted(all_valid_sort))}",
            )

async def execute_query(
    query: NormalizedQuery,
    concept: DatasetConcept,
    operational_session: AsyncSession,
    *,
    cache_enabled: bool = True,
    cache_ttl: int = 300,
    is_public: bool = True,
    client_id: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Execute a validated query with caching.

    Returns:
        (rows, cache_hit) tuple.
    """
    # Determine cache key
    identity = None if is_public else client_id
    cache_key = compute_cache_key(query, include_identity=identity)

    # Check cache
    if cache_enabled:
        cached = await cache_service.get_cached(cache_key)
        if cached is not None:
            if not settings.is_production:
                logger.info("Cache hit", extra={"cache_key": cache_key[:32]})
            return cached, True

    # Build SQL
    built = sql_builder.build_query(query, concept)

    # Execute against operational DB
    start = time.perf_counter()
    try:
        result = await operational_session.execute(text(built.sql), built.params)
        rows_raw = result.mappings().all()
        rows = [dict(row) for row in rows_raw]
    except Exception as exc:
        if not settings.is_production:
            logger.error(
                "Query execution failed",
                extra={"error": str(exc), "sql": built.sql[:200]},
            )
        raise DALError(
            ErrorCode.INTERNAL_ERROR,
            "Query execution failed",
        ) from exc
    finally:
        exec_ms = round((time.perf_counter() - start) * 1000, 2)
        if not settings.is_production:
            logger.info("Query executed", extra={"exec_ms": exec_ms})

    # Store in cache
    if cache_enabled and rows:
        await cache_service.set_cached(cache_key, rows, cache_ttl)

    return rows, False



async def execute_query_dataset_codelist(
    query: NormalizedDatasetInfoQuery,
    concept: DatasetConcept,
    operational_session: AsyncSession,
    cache_enabled: bool = True,
    cache_ttl: int = 300,
    is_public: bool = True,
    client_id: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """
    Execute a validated query with caching.

    Returns:
        (rows, cache_hit) tuple.
    """
    # Determine cache key
    identity = None if is_public else client_id
    cache_key = compute_cache_key(query, include_identity=identity)

    # Check cache
    if cache_enabled:
        cached = await cache_service.get_dict_cached(cache_key)
        if cached is not None:
            if not settings.is_production:
                logger.info("Cache hit", extra={"cache_key": cache_key[:32]})
            cached = await cast_dataset_info_concept(cached)
            return cached, True

    # Build SQL
    built = sql_builder.build_query_dataset_codelist(concept)

    # Execute against operational DB
    start = time.perf_counter()
    dataset_info = {}
    try:
        for key, b in built.items() if built is not None else {}:
            concept_info = None
            code = ''
            if key == "frequency":
                concept_info = concept.frequency.metadata
                code = concept.frequency.code
            elif key == "period":
                concept_info = concept.period.metadata
                code = concept.period.code
            elif key == "dimensions":
                concept_info = concept.dimensions
            elif key == "measures":
                concept_info = concept.measures
                
            if concept_info is None:
                continue
            concept_info_data = []
            sub_concept_info_data = []
            if b is not None:
                if isinstance(b, sql_builder.BuiltQuery):
                    if b.data is not None:
                        concept_info_data = b.data
                    else:
                        result = await operational_session.execute(text(b.sql), b.params)
                        rows_raw = result.mappings().all()
                        concept_info_data = [dict(row) for row in rows_raw]
                elif isinstance(b, dict):
                    metric_concept = None
                    if key == "dimensions":
                        metric_concept = concept.dimensions
                    elif key == "measures":
                        metric_concept = concept.measures
                    if metric_concept is None:
                        continue
                    for sub_key, sub_b in b.items():
                        sub_concept_info = None
                        for sub_concept in metric_concept:
                            if isinstance(sub_concept, sql_builder.DimensionConcept) and sub_concept.code == sub_key:
                                sub_concept_info = sub_concept.metadata
                                break
                            elif isinstance(sub_concept, sql_builder.MeasureConcept) and sub_concept.unit and f"{sub_concept.code}.{sub_concept.unit.code}" == sub_key:
                                sub_concept_info = sub_concept.unit.metadata
                                break
                            elif isinstance(sub_concept, sql_builder.MeasureConcept) and sub_concept.code == sub_key:
                                sub_concept_info = sub_concept.metadata
                                break
                        
                        if sub_concept_info is None:
                            continue
                        if sub_b is not None and isinstance(sub_b, sql_builder.BuiltQuery):
                            if sub_b.data is not None:
                                concept_info_data = sub_b.data
                            else:
                                result = await operational_session.execute(text(sub_b.sql), sub_b.params)
                                rows_raw = result.mappings().all()
                                concept_info_data = [dict(row) for row in rows_raw]
                        if isinstance(sub_concept_info, Metadata):
                            sub_concept_info_data.append({
                                "code": sub_key,
                                "description": sub_concept_info.description,
                                "type": sub_concept_info.type,
                                "auto_generate": sub_concept_info.auto_generate,
                                "data": concept_info_data,
                            })
                     
            # Cast concept_info_data to CodeConcept list if it's a list of dicts with 'code' keys
            if isinstance(concept_info, Metadata):
                dataset_info[str(key)] = {
                    "code": code,
                    "description": concept_info.description,
                    "type": concept_info.type,
                    "auto_generate": concept_info.auto_generate,
                    "data": concept_info_data,
                }
            elif isinstance(concept_info, list):
                dataset_info[str(key)] = sub_concept_info_data
    except Exception as exc:
        if not settings.is_production:
            logger.error(
                "Query execution failed",
                extra={"error": str(exc)},
            )
        raise DALError(
            ErrorCode.INTERNAL_ERROR,
            "Query execution failed",
        ) from exc
    finally:
        exec_ms = round((time.perf_counter() - start) * 1000, 2)
        if not settings.is_production:
            logger.info("Query executed", extra={"exec_ms": exec_ms})

    # Store in cache
    if cache_enabled and dataset_info:
        await cache_service.set_dict_cached(cache_key, dataset_info, cache_ttl)
    dataset_info = await cast_dataset_info_concept(dataset_info)
    return dataset_info, False


async def cast_dataset_info_concept(
    payload: dict[str, Any],
) -> dict[str, ColumnInfo | list[ColumnInfo] | None]:
    """
    Cast dataset concept info payload to expected types.
    """
    casted = {}
    for key, value in payload.items():
        if isinstance(value, dict) and "code" in value:
            # Single concept
            casted[key] = ColumnInfo(
                                code=value.get("code", ""),
                                description=value.get("description"),
                                type=value.get("type"),
                                auto_generate=value.get("auto_generate", False),
                                data=[CodeConcept(**item) for item in value.get("data", [])] if value.get("data") else None
                            )
        elif isinstance(value, list):
            # List of concepts
            _value = []
            for item in value:
                if isinstance(item, dict) and "code" in item:
                    _value.append(ColumnInfo(
                        code=item.get("code", ""),
                        description=item.get("description"),
                        type=item.get("type"),
                        auto_generate=item.get("auto_generate", False),
                        data=[CodeConcept(**sub_item) for sub_item in item.get("data", [])] if item.get("data") else None
                    ))
            casted[key] = _value
        else:
            casted[key] = None
    return casted