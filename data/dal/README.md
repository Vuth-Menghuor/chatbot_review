# DAL — Data Access Layer

A metadata-driven query API that provides secure, governed access to operational data. Built with **FastAPI**, **PostgreSQL**, **Redis**, and **Docker**.

## Architecture

```
Client → [x-api-key] → FastAPI → SlowAPI Limiter (fixed-window) → Auth → Dataset Resolution
  → Concept Validation → SQL Builder (metadata-driven) → Operational DB
  → Cache (Redis) → Structured Response + Audit Log
```

Key design principles:
- **No raw SQL from clients** — all queries are built from metadata-defined field mappings
- **Parameterized values** — user input is never concatenated into SQL
- **Fail-closed** — any field not explicitly in the dataset concept is rejected
- **Two isolated databases** — metadata DB and operational DB have separate connections
- **Redis-backed rate limiting** — `SlowAPI` enforces per-minute limits by `x-api-key` (HTTP 429 on exceed)

## Quick Start

### 1. Start services
```bash
# Copy environment config
cp .env.example .env

# Start all services (app, metadata DB, operational DB, Redis)
docker compose up -d
```

### 2. Run migrations
```bash
docker compose exec app alembic upgrade head
```

### 3. Seed data
```bash
# Seed metadata (datasets, API keys, cache policy)
docker compose exec app python -m scripts.seed_metadata

# Seed operational data (trade records)
docker compose exec app python -m scripts.seed_operational
```

### 4. Open Swagger docs
Navigate to [http://localhost:8989/docs](http://localhost:8989/docs)

### 5. Try a query
```bash
curl -H "x-api-key: dal-pub-key-abc123xyz789" \
  "http://localhost:8989/v1/query/trade_volume?dimensions=FREQ,PARTNER_COUNTRY,FLOW&measures=VALUE_USD,NETWEIGHT&frequency=M&start-period=2025-Q1&end-period=2026-Q2&limit=10"
```

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run unit tests (no DB required)
pytest tests/unit/ -v

# Run contract tests (no DB required)
pytest tests/contract/ -v

# Run all tests
pytest -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health/live` | Liveness probe |
| GET | `/health/ready` | Readiness probe (checks all deps) |
| GET | `/v1/query/{dataset}` | Execute a governed data query |
| GET | `/v1/metadata/datasets` | List available datasets |
| GET | `/v1/metadata/dataset/{dataset}` | Get details for a specific dataset |
| POST | `/v1/crud/{table}` | Create metadata row for a table |
| GET | `/v1/crud/{table}` | List metadata rows for a table |
| GET | `/v1/crud/{table}/{item_id}` | Get metadata row by primary key |
| PATCH | `/v1/crud/{table}/{item_id}` | Update metadata row by primary key |
| DELETE | `/v1/crud/{table}/{item_id}` | Delete metadata row by primary key |

Rate limiting:
- `SlowAPI` applies `DEFAULT_RATE_LIMIT_PER_MINUTE` as `{N}/minute` to query, metadata, and health endpoints
- Client identity is derived from `x-api-key` (fallback to client IP)
- Exceeded requests return HTTP 429 with DAL error envelope and `Retry-After: 60`

## Sample API Keys (Development Only)

| Key | Client | Access |
|-----|--------|--------|
| `dal-local-api-key` | local_dev_client | All local datasets (development only) |
| `dal-pub-key-abc123xyz789` | public_client | Public datasets |
| `dal-priv-key-def456uvw012` | private_client | Public + trade_volume (explicit grant) |

For Bruno or any local client, send `x-api-key: dal-local-api-key` in development, or use the seeded keys above if you want to exercise the DB-backed auth flow.

## Project Structure

```
dal/
├── app/
│   ├── api/v1/endpoints/    # HTTP endpoints
│   ├── core/                # Config, security, middleware, errors
│   ├── db/                  # DB sessions and ORM models
│   ├── schemas/             # Pydantic request/response models
│   ├── services/            # Business logic
│   └── utils/               # Parsing, normalization, hashing
├── tests/                   # Unit, integration, contract tests
├── scripts/                 # Seed scripts
├── alembic/                 # DB migrations
├── docker-compose.yml
└── Dockerfile
```

## Tech Stack

- Python 3.12+, FastAPI, Pydantic v2
- SQLAlchemy 2.0 (async), Alembic
- PostgreSQL 16 (metadata + operational)
- Redis 7 (query caching + SlowAPI rate-limit counters)
- Docker Compose
