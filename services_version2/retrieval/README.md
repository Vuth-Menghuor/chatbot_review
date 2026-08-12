# Retrieval Service (v2) — HS Code Classification

Semantic + structured HS code classification service built on FastAPI, Qdrant,
and Google Gemini. Serves as the backend for product-to-tariff-code lookups
against the Cambodian GDCE customs tariff database.

> **Port:** `8003` &emsp;|&emsp; **Scope:** HS code classification only  
> General / FAQ / policy queries are handled by the companion
> [general retrieval service](#) on port `8005`.

---

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Development](#development)
- [Testing](#testing)
- [Load Testing](#load-testing)
- [Deployment](#deployment)
- [Project Structure](#project-structure)

---

## Architecture

```
                   ┌─────────────────────┐
                   │   Orchestrator       │
                   │   (port 8001)        │
                   └─────────┬───────────┘
                             │ HS_CODE_LOOKUP intent
                             ▼
                   ┌─────────────────────┐
                   │  Retrieval Service   │
                   │  (port 8003)         │
                   │                     │
                   │  POST /hs-code-     │
                   │       candidates    │
                   │  POST /hs-code-     │
                   │       ranked        │
                   │  GET  /health       │
                   └──┬──────┬──────┬───┘
                      │      │      │
              ┌───────┘      │      └──────────┐
              ▼              ▼                 ▼
        ┌──────────┐  ┌───────────┐    ┌───────────┐
        │  Qdrant   │  │  Gemini   │    │   Redis    │
        │ (vector   │  │  (LLM     │    │  (corpus   │
        │  store)   │  │  answer)  │    │   cache)   │
        └──────────┘  └───────────┘    └───────────┘
```

### Retrieval Pipeline

1. **Gemini prefix extraction** — the user query is sent to Gemini to extract a
   6-digit HS heading prefix (e.g. `"BMW M8 Competition"` → `"870323"`).
2. **Structured prefix scan** — the in-memory HS corpus is filtered to all
   codes under that prefix family, scored by token overlap, and hard-filtered
   by vehicle constraints (fuel, body, drive, cc, assembly).
3. **Semantic search** — runs in parallel; used to fill gaps when the prefix
   scan yields fewer than 3 candidates, or as the sole source when Gemini
   cannot extract a prefix.
4. **Gemini ranked answer** — the top candidates are sent to Gemini with a
   structured prompt to produce a ranked list, natural-language summary, and
   clarifying questions for generic queries. Falls back to extractive lexical
   ranking if Gemini is unavailable.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for Qdrant & Redis)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)
- A pre-embedded HS code JSON data file (see [Data Setup](#data-setup))

### 1. Clone & enter the directory

```bash
cd retrieval
```

### 2. Start infrastructure (Qdrant + Redis)

```bash
docker compose up -d qdrant redis-retrieval
```

### 3. Seed the vector database

Place your pre-embedded HS code JSON file as `scripts/gdce_hs_code.json`,
then run:

```bash
python scripts/hs_code.py
```

> This creates the `gdce_hs_code` collection and uploads all points in batches.
> The script is idempotent — re-running it will skip collection creation if it
> already exists and re-upload the data.

### 4. Set environment variables

```bash
cp .env.example .env
# Edit .env — at minimum set:
#   GEMINI_API_KEY=your-key-here
```

### 5. Install dependencies

```bash
pip install -r requirements.txt
```

### 6. Run the service

```bash
uvicorn app.app:app --reload --host 127.0.0.1 --port 8003
```

The API documentation is available at **http://localhost:8003/docs**.

### 6. Quick smoke test

```bash
curl -X POST http://localhost:8003/hs-code-candidates \
  -H "Content-Type: application/json" \
  -d '{"query": "BMW M8 Competition", "generate_answer": true}'
```

---

## Configuration

All settings are read from environment variables (via `python-dotenv`).

| Variable | Default | Description |
|---|---|---|
| `RETRIEVAL_HOST` | `127.0.0.1` | Bind address |
| `RETRIEVAL_PORT` | `8003` | Bind port |
| `RETRIEVAL_RELOAD` | `false` | Enable Uvicorn hot-reload |
| `RETRIEVAL_WORKERS` | `4` | Number of Uvicorn worker processes |
| `QDRANT_HOST` | `localhost` | Qdrant server host |
| `QDRANT_PORT` | `6333` | Qdrant server port |
| `QDRANT_API_KEY` | `""` | Qdrant API key (if required) |
| `QDRANT_HS_CODE_COLLECTION` | `gdce_hs_code` | HS code collection name |
| `QDRANT_TIMEOUT` | `30.0` | Qdrant request timeout (seconds) |
| `QUERY_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | HuggingFace sentence-transformers model |
| `TOP_K_DEFAULT` | `10` | Default number of candidates |
| `TOP_K_MAX` | `50` | Maximum allowed candidates |
| `GEMINI_API_KEY` | `""` | Google AI Studio API key |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model ID |
| `GEMINI_ENABLED` | `true` | Enable/disable Gemini answer generation |
| `REDIS_HOST` | `localhost` | Redis server host |
| `REDIS_PORT` | `6381` | Redis server port |
| `REDIS_CORPUS_TTL` | `21600` | HS corpus cache TTL (seconds, 6h) |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | Comma-separated CORS origins |
| `LOG_LEVEL` | `INFO` | Python log level |
| `GDCE_TARIFF_SEARCH_URL` | `https://customs.gov.kh/...` | Public tariff lookup URL |

---

## API Reference

### `POST /hs-code-candidates`

Full retrieval pipeline — returns ranked candidates with a generated answer.

**Request**
```json
{
  "query": "BMW M8 Competition",
  "top_k": 10,
  "generate_answer": true,
  "session_id": "optional-session-id"
}
```

**Response** (abbreviated)
```json
{
  "status": "success",
  "total_count": 3,
  "documents": [
    {
      "id": "abc123",
      "content": "Motor cars, spark-ignition engine, 3000-4500cc, CBU",
      "score": 0.95,
      "source": "structured_prefix_scan",
      "metadata": { "hs_code": "8703.23.10" }
    }
  ],
  "final_answer": "1. HS 8703.23.10 — Petrol-engine passenger car, 3000-4500cc, fully built unit\n...",
  "answer_source": "gemini_llm",
  "is_generic": true,
  "clarifying_note": "This is a best guess — the exact code depends on engine size, fuel type, and assembly state.",
  "clarifying_questions": [
    "What is the engine displacement (cc)?",
    "Is the vehicle petrol, diesel, electric, or hybrid?",
    "Is the vehicle imported fully assembled (CBU) or as a kit (CKD)?"
  ],
  "reference_url": "https://customs.gov.kh/en/publications/14037-customs-tariff-of-cambodia-km-2022"
}
```

### `POST /hs-code-ranked`

Lightweight endpoint — returns only the ranked answer (no raw documents).
Same request shape as `/hs-code-candidates`; response uses `RankedHSResponse`.

### `GET /health`

Liveness / readiness probe for orchestration tools.

```json
{
  "status": "healthy",
  "components": {
    "vector_store": { "status": "not_checked" },
    "embeddings": { "status": "not_checked" }
  }
}
```

### `GET /`

Service identity — returns version, port, and available endpoints.

---

## Development

### Install dev dependencies

```bash
pip install pytest pytest-asyncio httpx aiohttp locust
```

### Run tests

```bash
# Pure logic tests (fast, no external dependencies)
pytest tests/test_helpers.py -v

# API integration tests (mocked service)
pytest tests/test_api.py -v

# All tests
pytest tests/ -v
```

### Code quality

```bash
# Compile-check all files
python -m py_compile app/api/schemas.py app/llm/gemini_client.py app/config.py \
  app/app.py app/api/endpoints.py app/cache/redis_client.py \
  app/embeddings/embeddings.py app/rag/retrieval.py app/rag/service.py \
  app/vectorstore/vector_store.py prompts/loader.py main.py config.py \
  tests/conftest.py tests/test_api.py tests/test_helpers.py
```

---

## Load Testing

Two tools are provided to determine how many concurrent users the service can
handle before latency or error rate degrades.

### Quick: `concurrency_ramp_test.py`

No extra tooling needed — pure `asyncio` + `aiohttp`.

```bash
pip install aiohttp

# Baseline — test /health first (cheapest endpoint)
python load_test/concurrency_ramp_test.py \
  --url http://localhost:8003 \
  --endpoint /health \
  --steps 1,5,10,25,50,100,200

# Full pipeline
python load_test/concurrency_ramp_test.py \
  --url http://localhost:8003 \
  --endpoint /hs-code-candidates \
  --steps 1,5,10,25,50,100,200 \
  --requests-per-user 3
```

The script fires waves of N concurrent virtual users and prints a table with
throughput, failure rate, and latency percentiles per step:

```
 Users |   Reqs |     RPS |  Fail% |   p50ms |   p95ms |   p99ms |   maxms
--------------------------------------------------------------------------
     1 |      1 |     0.2 |   0.0% |  5883.4 |  5883.4 |  5883.4 |  5883.4
     5 |      5 |     0.6 |   0.0% |  5183.4 |  8023.9 |  8023.9 |  8023.9
    10 |     10 |     1.4 |   0.0% |  6146.8 |  7213.8 |  7213.8 |  7213.8
    25 |     25 |     1.8 |   0.0% | 10253.2 | 13445.6 | 13553.1 | 13553.1
    50 |     50 |     2.0 |   0.0% | 18819.6 | 24385.7 | 25034.1 | 25034.1
   100 |    100 |     3.2 |  61.0% | 30759.4 | 30769.3 | 30771.3 | 30771.3

Failure rate 61.0% exceeded threshold (20%) at 100 concurrent users — stopping ramp.
Practical concurrency ceiling looks to be just below 100 users.
```

**How to read this:** watch for the step where `Fail%` starts climbing or
`p95ms` jumps sharply relative to the previous step — not just rising
proportionally, but a sudden knee in the curve. That's your practical
concurrency ceiling. The script auto-stops once failure rate crosses
`--fail-fast-threshold` (default 20%).

Test `/health` first as a baseline (cheap, no LLM / vector-store work) — if
that also degrades at similar concurrency, the ceiling is coming from the
web server / connection handling, not the classification logic itself. If
`/health` stays fast while `/hs-code-candidates` degrades, the bottleneck is
Qdrant, Gemini, or the CPU-bound scoring logic.

### Full-featured: Locust

```bash
pip install locust

# Interactive web UI
locust -f load_test/locustfile.py --host http://localhost:8003
# → open http://localhost:8089

# Headless (CI-friendly)
locust -f load_test/locustfile.py --host http://localhost:8003 \
  --users 100 --spawn-rate 10 --run-time 2m --headless --csv=results/run1
```

---

## Deployment

### Docker Compose (full stack)

```bash
docker compose up -d
```

This starts three services:
- `qdrant` — vector database (port `6333`)
- `redis-retrieval` — corpus cache (port `6381`)
- `retrieval-service` — the FastAPI app (port `8003`)

### Build only the app image

```bash
docker build -t retrieval-service .
docker run -p 8003:8003 --env-file .env retrieval-service
```

---

## Data Setup

The service requires a pre-embedded HS code dataset in Qdrant. The
`scripts/hs_code.py` uploader handles this.

### Data file format

Place your JSON file at `scripts/gdce_hs_code.json`. Each entry must have:

```json
{
  "id": "unique-point-id",
  "vector": [0.123, -0.456, ...],
  "payload": {
    "hs_code": "8703.23.10",
    "description": "Motor cars, spark-ignition engine, 3000-4500cc, CBU",
    "title": "Passenger Vehicles",
    "text": "Full description text for search..."
  }
}
```

- `vector` must be **384-dimensional** (matching `all-MiniLM-L6-v2`).
- The `payload` fields are searched and returned by the retrieval service.
- Use `sentence-transformers` to generate embeddings before uploading.

### Upload

```bash
# Ensure Qdrant is running first
docker compose up -d qdrant

# Seed the database (idempotent — safe to re-run)
python scripts/hs_code.py
```

---

## Project Structure

```
retrieval/
├── app/
│   ├── __init__.py              # Package docstring
│   ├── app.py                   # FastAPI application factory + lifecycle
│   ├── config.py                # Centralised configuration (env vars)
│   ├── api/
│   │   ├── __init__.py          # Router + schema re-exports
│   │   ├── endpoints.py         # HTTP handlers + classification logic
│   │   └── schemas.py           # Pydantic request/response models
│   ├── cache/
│   │   └── redis_client.py      # Fail-open Redis cache client
│   ├── embeddings/
│   │   └── embeddings.py        # Sentence-transformer embeddings + fallback
│   ├── llm/
│   │   └── gemini_client.py     # Gemini LLM client (async wrapper)
│   ├── rag/
│   │   ├── retrieval.py         # Semantic search orchestration
│   │   └── service.py           # HS corpus loading, prefix lookup, scoring
│   └── vectorstore/
│       └── vector_store.py      # Qdrant client wrapper
├── scripts/
│   ├── hs_code.py               # Data uploader (JSON → Qdrant)
│   └── gdce_hs_code.json        # Pre-embedded HS code dataset (not tracked)
├── prompts/
│   ├── __init__.py              # Prompt loader re-exports
│   ├── loader.py                # File-backed prompt template loader
│   ├── gemini_extract_specs.txt # HS prefix extraction prompt
│   ├── gemini_extract_specs_retry.txt
│   └── gemini_ranked_hs.txt     # Ranked answer generation prompt
├── tests/
│   ├── conftest.py              # sys.path setup for test imports
│   ├── test_api.py              # FastAPI integration tests (mocked)
│   └── test_helpers.py          # Pure-logic unit tests
├── load_test/
│   ├── concurrency_ramp_test.py # Standalone async concurrency tester
│   ├── locustfile.py            # Locust load-test definition
│   └── README.md                # Load-testing guide
├── main.py                      # Entry point (uvicorn bootstrap)
├── config.py                    # Compatibility re-export shim
├── requirements.txt             # Python dependencies
├── Dockerfile                   # App container image
├── docker-compose.yml           # Full stack (Qdrant + Redis + App)
├── up.sh                        # One-command start script
└── README.md                    # This file
```
