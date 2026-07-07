"""Generic metadata CRUD endpoints (admin-style)."""

from __future__ import annotations

from typing import Any
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import inspect, select

from app.api.deps import AuthClient, MetadataSession
from app.core.config import get_settings
from app.core.errors import DALError, ErrorCode
from app.core.rate_limit import limiter
from app.core.security import hash_api_key
from app.db.models import (
    ApiKey,
    ApiKeyDataset,
    AuditLog,
    CachePolicy,
    Dataset,
    DatasetMapping,
    DatasetVersion,
)
from app.schemas.response import ErrorResponse
from app.services import auth_service

router = APIRouter(prefix="/v1/crud", tags=["CRUD"])
CRUD_RATE_LIMIT = f"{get_settings().crud_rate_limit_per_minute}/minute"

_TABLE_MODELS = {
    "dataset": Dataset,
    "dataset-version": DatasetVersion,
    "dataset-mapping": DatasetMapping,
    "api-key": ApiKey,
    "api-key-dataset": ApiKeyDataset,
    "cache-policy": CachePolicy,
    "audit-log": AuditLog,
}

_CRUD_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "Authentication error"},
    403: {"model": ErrorResponse, "description": "Authorization error"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    500: {"model": ErrorResponse, "description": "Internal error"},
}

_CREATE_EXAMPLES = {
    "dataset": {
        "dataset_code": "trade_volume_v2",
        "name": "Trade Volume V2",
        "description": "Metadata dataset for trade analytics",
        "is_public": True,
        "status": "active",
    },
    "dataset-version": {
        "dataset_code": "trade_volume_v2",
        "version": "1.0",
        "status": "active",
        "is_default": True,
        "effective_date": "2026-05-01T00:00:00Z",
    },
    "dataset-mapping": {
        "dataset_code": "trade_volume_v2",
        "version": "1.0",
        "dataset_concept": {
            "dataset-code": "trade_volume_v2",
            "version": "1.0",
            "frequency": {"code": "FREQ", "default": "A", "query": "td.freq"},
            "period": {"code": "PERIOD", "query": "td.ref_year::TEXT"},
            "dimensions": [{"code": "FLOW", "query": "td.flow"}],
            "measures": [{"code": "VALUE_USD", "query": "td.value_usd", "aggregate": "SUM"}],
            "source": {"connection-key": "operational_db", "table": "trade_data as td"},
            "filters": {},
            "security": {"allow-raw-sql": False},
        },
    },
    "api-key": {
        "client_id": "partner_client",
        "key_plain": "PUBLIC_KEY_PLAIN",
        "status": "active",
        "tier": "developer",
        "rate_limit_per_minute": 60,
    },
    "api-key-dataset": {
        "key_id": "11111111-1111-1111-1111-111111111111",
        "dataset_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "scopes": ["query:read", "metadata:read"],
    },
    "cache-policy": {
        "dataset_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "ttl_seconds": 600,
        "enabled": True,
    },
    "audit-log": {
        "request_id": "33333333-3333-3333-3333-333333333333",
        "client_id": "partner_client",
        "dataset": "trade_volume_v2",
        "dataset_version": "1.0",
        "status_code": 200,
        "latency_ms": 34.7,
        "cache_hit": False,
        "query_fingerprint": "f2d73a4ac9187d4ec9b67ff4d6e8f52a67f8ab12f3f1a9bcadfe7b13b96e1022",
        "error_summary": None,
        "request_params": {
            "dimensions": ["FLOW"],
            "measures": ["VALUE_USD"],
            "frequency": "A",
        },
    },
}

_PATCH_EXAMPLES = {
    "dataset": {
        "name": "Trade Volume V2 Updated",
        "description": "Updated metadata dataset description",
        "is_public": False,
        "status": "inactive",
    },
    "dataset-version": {
        "status": "inactive",
        "is_default": False,
        "effective_date": "2026-06-01T00:00:00Z",
    },
    "dataset-mapping": {
        "dataset_concept": {
            "dataset-code": "trade_volume_v2",
            "version": "1.0",
            "frequency": {"code": "FREQ", "default": "M", "query": "td.freq"},
            "period": {"code": "PERIOD", "query": "td.ref_year || '-' || LPAD(td.ref_month::TEXT, 2, '0')"},
            "dimensions": [{"code": "FLOW", "query": "td.flow"}],
            "measures": [{"code": "VALUE_USD", "query": "td.value_usd", "aggregate": "SUM"}],
            "source": {"connection-key": "operational_db", "table": "trade_data as td"},
            "filters": {},
            "security": {"allow-raw-sql": False},
        }
    },
    "api-key": {
        "key_plain": "ROTATED_PUBLIC_KEY_PLAIN",
        "status": "active",
        "tier": "admin",
        "rate_limit_per_minute": 120,
    },
    "api-key-dataset": {
        "scopes": ["query:read"],
    },
    "cache-policy": {
        "ttl_seconds": 120,
        "enabled": False,
    },
    "audit-log": {
        "status_code": 500,
        "error_summary": "Downstream database timeout",
    },
}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _as_json_value(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_as_json_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _as_json_value(v) for k, v in value.items()}
    return value


def _serialize_row(row) -> dict:
    mapper = inspect(type(row))
    out: dict = {}
    for col in mapper.columns:
        out[col.name] = _as_json_value(getattr(row, col.name))
    return out


def _primary_key_column(model):
    mapper = inspect(model)
    return mapper.primary_key[0]


def _coerce_pk(pk_col, item_id: str):
    py_type = getattr(pk_col.type, "python_type", None)
    if py_type is UUID:
        try:
            return UUID(item_id)
        except ValueError as exc:
            raise DALError(ErrorCode.VALIDATION_ERROR, f"Invalid id format: {item_id}") from exc
    return item_id


def _coerce_payload(model, payload: dict) -> dict:
    mapper = inspect(model)
    by_name = {c.name: c for c in mapper.columns}
    coerced: dict = {}
    for key, value in payload.items():
        if key not in by_name:
            raise DALError(ErrorCode.VALIDATION_ERROR, f"Unknown column '{key}'")
        col = by_name[key]
        py_type = getattr(col.type, "python_type", None)
        if value is None:
            coerced[key] = None
        elif py_type is UUID:
            try:
                coerced[key] = UUID(str(value))
            except ValueError as exc:
                raise DALError(ErrorCode.VALIDATION_ERROR, f"Column '{key}' expects UUID") from exc
        elif py_type is int:
            try:
                coerced[key] = int(value)
            except (TypeError, ValueError) as exc:
                raise DALError(ErrorCode.VALIDATION_ERROR, f"Column '{key}' expects int") from exc
        elif py_type is float:
            try:
                coerced[key] = float(value)
            except (TypeError, ValueError) as exc:
                raise DALError(ErrorCode.VALIDATION_ERROR, f"Column '{key}' expects float") from exc
        elif py_type is bool:
            if isinstance(value, bool):
                coerced[key] = value
            elif isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "y"}:
                    coerced[key] = True
                elif lowered in {"false", "0", "no", "n"}:
                    coerced[key] = False
                else:
                    raise DALError(ErrorCode.VALIDATION_ERROR, f"Column '{key}' expects bool")
            elif isinstance(value, (int, float)):
                coerced[key] = bool(value)
            else:
                raise DALError(ErrorCode.VALIDATION_ERROR, f"Column '{key}' expects bool")
        else:
            coerced[key] = value
    return coerced


def _normalize_api_key_payload_for_write(payload: dict, *, create: bool) -> dict:
    payload_copy = dict(payload)
    key_plain = payload_copy.pop("key_plain", None)
    has_hashed = "hashed_key" in payload_copy

    if key_plain is not None and has_hashed:
        raise DALError(
            ErrorCode.VALIDATION_ERROR,
            "Provide either 'key_plain' or 'hashed_key', not both",
        )

    if key_plain is not None:
        payload_copy["hashed_key"] = hash_api_key(str(key_plain))
    elif has_hashed:
        # If client sends plain key in hashed_key field, persist securely as hash.
        payload_copy["hashed_key"] = hash_api_key(str(payload_copy["hashed_key"]))
    elif create:
        raise DALError(
            ErrorCode.VALIDATION_ERROR,
            "Either 'key_plain' or 'hashed_key' is required for api-key create",
        )

    return payload_copy


def _require_crud_tier(client: AuthClient) -> None:
    auth_service.authorize_crud_tier(client)


def _make_create_handler(table_name: str, model):
    @limiter.limit(CRUD_RATE_LIMIT)
    async def create_item(
        request: Request,
        payload: dict,
        client: AuthClient,
        session: MetadataSession,
    ):
        _require_crud_tier(client)
        payload_copy = dict(payload)
        if model is ApiKey:
            payload_copy = _normalize_api_key_payload_for_write(payload_copy, create=True)

        coerced = _coerce_payload(model, payload_copy)
        row = model(**coerced)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return {
            "request_id": _request_id(request),
            "table": table_name,
            "item": _serialize_row(row),
        }

    return create_item


def _make_list_handler(table_name: str, model):
    @limiter.limit(CRUD_RATE_LIMIT)
    async def list_items(
        request: Request,
        client: AuthClient,
        session: MetadataSession,
        limit: int = 100,
        offset: int = 0,
    ):
        _require_crud_tier(client)
        safe_limit = max(1, min(limit, 500))
        safe_offset = max(0, offset)
        result = await session.execute(select(model).limit(safe_limit).offset(safe_offset))
        rows = result.scalars().all()
        return {
            "request_id": _request_id(request),
            "table": table_name,
            "limit": safe_limit,
            "offset": safe_offset,
            "count": len(rows),
            "items": [_serialize_row(r) for r in rows],
        }

    return list_items


def _make_get_handler(table_name: str, model):
    pk_col = _primary_key_column(model)

    @limiter.limit(CRUD_RATE_LIMIT)
    async def get_item(
        request: Request,
        item_id: str,
        client: AuthClient,
        session: MetadataSession,
    ):
        _require_crud_tier(client)
        pk_value = _coerce_pk(pk_col, item_id)
        result = await session.execute(select(model).where(pk_col == pk_value))
        row = result.scalar_one_or_none()
        if row is None:
            raise DALError(ErrorCode.VALIDATION_ERROR, f"Record not found in '{table_name}'")
        return {
            "request_id": _request_id(request),
            "table": table_name,
            "item": _serialize_row(row),
        }

    return get_item


def _make_update_handler(table_name: str, model):
    pk_col = _primary_key_column(model)
    pk_name = pk_col.name

    @limiter.limit(CRUD_RATE_LIMIT)
    async def update_item(
        request: Request,
        item_id: str,
        payload: dict,
        client: AuthClient,
        session: MetadataSession,
    ):
        _require_crud_tier(client)
        pk_value = _coerce_pk(pk_col, item_id)
        result = await session.execute(select(model).where(pk_col == pk_value))
        row = result.scalar_one_or_none()
        if row is None:
            raise DALError(ErrorCode.VALIDATION_ERROR, f"Record not found in '{table_name}'")

        if pk_name in payload:
            raise DALError(ErrorCode.VALIDATION_ERROR, f"Primary key '{pk_name}' cannot be updated")

        payload_copy = dict(payload)
        if model is ApiKey:
            payload_copy = _normalize_api_key_payload_for_write(payload_copy, create=False)

        coerced = _coerce_payload(model, payload_copy)
        for key, value in coerced.items():
            setattr(row, key, value)

        await session.commit()
        await session.refresh(row)
        return {
            "request_id": _request_id(request),
            "table": table_name,
            "item": _serialize_row(row),
        }

    return update_item


def _make_delete_handler(table_name: str, model):
    pk_col = _primary_key_column(model)

    @limiter.limit(CRUD_RATE_LIMIT)
    async def delete_item(
        request: Request,
        item_id: str,
        client: AuthClient,
        session: MetadataSession,
    ):
        _require_crud_tier(client)
        pk_value = _coerce_pk(pk_col, item_id)
        result = await session.execute(select(model).where(pk_col == pk_value))
        row = result.scalar_one_or_none()
        if row is None:
            raise DALError(ErrorCode.VALIDATION_ERROR, f"Record not found in '{table_name}'")

        await session.delete(row)
        await session.commit()
        return {
            "request_id": _request_id(request),
            "table": table_name,
            "deleted": True,
            "item_id": item_id,
        }

    return delete_item


for _table_name, _model in _TABLE_MODELS.items():
    _base_path = f"/{_table_name}"
    router.add_api_route(
        _base_path,
        _make_create_handler(_table_name, _model),
        methods=["POST"],
        summary=f"Create {_table_name} row",
        description=f"Create a row in '{_table_name}' table.",
        responses=_CRUD_ERROR_RESPONSES,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": _CREATE_EXAMPLES.get(_table_name, {}),
                    }
                },
            }
        },
    )
    router.add_api_route(
        _base_path,
        _make_list_handler(_table_name, _model),
        methods=["GET"],
        summary=f"List {_table_name} rows",
        responses=_CRUD_ERROR_RESPONSES,
    )
    router.add_api_route(
        f"{_base_path}/{{item_id}}",
        _make_get_handler(_table_name, _model),
        methods=["GET"],
        summary=f"Get {_table_name} row",
        responses=_CRUD_ERROR_RESPONSES,
    )
    router.add_api_route(
        f"{_base_path}/{{item_id}}",
        _make_update_handler(_table_name, _model),
        methods=["PATCH"],
        summary=f"Update {_table_name} row",
        description=f"Patch a row in '{_table_name}' table by primary key.",
        responses=_CRUD_ERROR_RESPONSES,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "example": _PATCH_EXAMPLES.get(_table_name, {}),
                    }
                },
            }
        },
    )
    router.add_api_route(
        f"{_base_path}/{{item_id}}",
        _make_delete_handler(_table_name, _model),
        methods=["DELETE"],
        summary=f"Delete {_table_name} row",
        responses=_CRUD_ERROR_RESPONSES,
    )
