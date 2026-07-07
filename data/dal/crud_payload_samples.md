# CRUD Payload Samples

This file provides request payload examples for the metadata CRUD routes under `/v1/crud/{table}`.

## Header

Use a valid API key for every request.

```http
x-api-key: dal-pub-key-abc123xyz789
```

## Notes

- POST route: `/v1/crud/{table}`
- PATCH route: `/v1/crud/{table}/{item_id}`
- Primary key fields should not be included in PATCH payloads.
- Some fields have DB defaults. Include them only if you want to override defaults.
- CRUD endpoints require API key tier `admin` or `developer`.

## 1) dataset

POST `/v1/crud/dataset`

```json
{
  "dataset_code": "trade_volume_v2",
  "name": "Trade Volume V2",
  "description": "New metadata dataset for trade volume",
  "is_public": true,
  "status": "active"
}
```

PATCH `/v1/crud/dataset/{dataset_id}`

```json
{
  "name": "Trade Volume V2 Updated",
  "description": "Updated description",
  "is_public": false,
  "status": "inactive"
}
```

## 2) dataset-version

POST `/v1/crud/dataset-version`

```json
{
  "dataset_code": "trade_volume_v2",
  "version": "1.0",
  "status": "active",
  "is_default": true,
  "effective_date": "2026-05-01T00:00:00Z"
}
```

PATCH `/v1/crud/dataset-version/{dataset_version_id}`

```json
{
  "status": "inactive",
  "is_default": false,
  "effective_date": "2026-06-01T00:00:00Z"
}
```

## 3) dataset-mapping

POST `/v1/crud/dataset-mapping`

```json
{
  "dataset_code": "trade_volume_v2",
  "version": "1.0",
  "dataset_concept": {
    "dataset-code": "trade_volume_v2",
    "version": "1.0",
    "frequency": {
      "code": "FREQ",
      "default": "A",
      "query": "td.freq"
    },
    "period": {
      "code": "PERIOD",
      "query": "td.ref_year::TEXT"
    },
    "dimensions": [
      {"code": "FLOW", "query": "td.flow"}
    ],
    "measures": [
      {"code": "VALUE_USD", "query": "td.value_usd", "aggregate": "SUM"}
    ],
    "source": {
      "connection-key": "operational_db",
      "table": "trade_data as td"
    },
    "filters": {},
    "security": {"allow-raw-sql": false}
  }
}
```

PATCH `/v1/crud/dataset-mapping/{id}`

```json
{
  "dataset_concept": {
    "dataset-code": "trade_volume_v2",
    "version": "1.0",
    "frequency": {
      "code": "FREQ",
      "default": "M",
      "query": "td.freq"
    },
    "period": {
      "code": "PERIOD",
      "query": "td.ref_year || '-' || LPAD(td.ref_month::TEXT, 2, '0')"
    },
    "dimensions": [
      {"code": "FLOW", "query": "td.flow"}
    ],
    "measures": [
      {"code": "VALUE_USD", "query": "td.value_usd", "aggregate": "SUM"}
    ],
    "source": {
      "connection-key": "operational_db",
      "table": "trade_data as td"
    },
    "filters": {},
    "security": {"allow-raw-sql": false}
  }
}
```

## 4) api-key

POST `/v1/crud/api-key`

The API hashes plaintext key input before storing into `hashed_key`.

Equivalent behavior:

`hashed_key = hash_api_key(PUBLIC_KEY_PLAIN)`

```json
{
  "client_id": "partner_client",
  "key_plain": "PUBLIC_KEY_PLAIN",
  "status": "active",
  "tier": "standard",
  "rate_limit_per_minute": 60
}
```

PATCH `/v1/crud/api-key/{key_id}`

```json
{
  "key_plain": "ROTATED_PUBLIC_KEY_PLAIN",
  "status": "inactive",
  "tier": "premium",
  "rate_limit_per_minute": 120
}
```

## 5) api-key-dataset

POST `/v1/crud/api-key-dataset`

```json
{
  "key_id": "11111111-1111-1111-1111-111111111111",
  "dataset_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "scopes": ["query:read", "metadata:read"]
}
```

PATCH `/v1/crud/api-key-dataset/{id}`

```json
{
  "scopes": ["query:read"]
}
```

## 6) cache-policy

POST `/v1/crud/cache-policy`

```json
{
  "dataset_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "ttl_seconds": 600,
  "enabled": true
}
```

PATCH `/v1/crud/cache-policy/{id}`

```json
{
  "ttl_seconds": 120,
  "enabled": false
}
```

## 7) audit-log

POST `/v1/crud/audit-log`

```json
{
  "request_id": "33333333-3333-3333-3333-333333333333",
  "client_id": "partner_client",
  "dataset": "trade_volume_v2",
  "dataset_version": "1.0",
  "status_code": 200,
  "latency_ms": 34.7,
  "cache_hit": false,
  "query_fingerprint": "f2d73a4ac9187d4ec9b67ff4d6e8f52a67f8ab12f3f1a9bcadfe7b13b96e1022",
  "error_summary": null,
  "request_params": {
    "dimensions": ["FLOW"],
    "measures": ["VALUE_USD"],
    "frequency": "A"
  }
}
```

PATCH `/v1/crud/audit-log/{id}`

```json
{
  "status_code": 500,
  "error_summary": "Downstream database timeout"
}
```
