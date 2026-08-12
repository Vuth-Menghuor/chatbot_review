# General Retrieval Service — FAQ / Policy / Definition Queries

Semantic + keyword document retrieval service built on FastAPI, Qdrant, and
Google Gemini. Serves general customs and trade questions — import procedures,
tariff definitions, policy documents, and FAQ-style queries — against the
Cambodian GDCE document corpus.

> **Port:** `8005` &emsp;|&emsp; **Scope:** General / FAQ / definition / policy queries  
> HS code classification is handled by the companion
> [retrieval service](../retrieval) on port `8003`.

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
                             │ general / FAQ / definition / policy
                             ▼
                   ┌─────────────────────┐
                   │  General Retrieval   │
                   │  Service (port 8005) │
                   │                     │
                   │  POST /retrieval/   │
                   │       retrieve      │
                   │  GET  /health       │
                   └──┬──────┬──────┬───┘
                      │      │      │
              ┌───────┘      │      └──────────┐
              ▼              ▼                 ▼
        ┌──────────┐  ┌───────────┐    ┌───────────┐
        │  Qdrant   │  │  Gemini   │    │   Redis    │
        │ (port     │  │  (LLM     │    │  (answer   │
        │  6334)    │  │  answer)  │    │   cache)   │
        └──────────┘  └───────────┘    └───────────┘
```

### Retrieval Pipeline

1. **Query processing** — language detection (Khmer / English), text
   normalisation, abbreviation expansion (e.g. `CIF` → `cost insurance freight`),
   stopword removal, token extraction.
2. **Trade-data guard** — queries that look like trade analytics ("import
   statistics", "trade volume") are prompted for a time period before retrieval
   proceeds, to avoid returning irrelevant documents.
3. **Semantic search** — the processed query is embedded and searched against
   the `gdce_docs` Qdrant collection using cosine similarity.
4. **Structured search** — optional keyword-based search via a document
   repository (reserved for future OpenSearch / Elasticsearch integration).
5. **Lexical reranking** — results are re-scored using token overlap, exact
   phrase match, FAQ heading match, and metadata-chunk penalties to keep the
   most relevant documents on top.
6. **Answer generation** — a cascading strategy: Gemini LLM → vLLM (optional) →
   extractive fallback. Successful Gemini answers are cached in Redis.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for Qdrant & Redis)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)
- A pre-embedded document JSON data file (see [Data Setup](#data-setup))

### 1. Clone & enter the directory

```bash
cd general
```

### 2. Start infrastructure (Qdrant + Redis)

```bash
docker compose up -d
```

### 3. Seed the vector database

Place your pre-embedded document JSON file as `scripts/gdce_docs.json`, then
run:

```bash
python scripts/pdf_chunk.py    # chunk + embed (produces JSON)
python scripts/markdown_chunk.py  # if you have markdown sources
```

> See `scripts/` for the actual upload and embedding scripts used in your
> deployment pipeline.

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
uvicorn app.main:app --reload --host 127.0.0.1 --port 8005
```

The API documentation is available at **http://localhost:8005/docs**.

### 7. Quick smoke test

```bash
curl -X POST http://localhost:8005/retrieval/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query": "What documents do I need to import goods into Cambodia?", "generate_answer": true}'
```

---

## Configuration

All settings are read from environment variables (via `python-dotenv`).

| Variable | Default | Description |
|---|---|---|
| `GENERAL_HOST` | `127.0.0.1` | Bind address |
| `GENERAL_PORT` | `8005` | Bind port |
| `GENERAL_RELOAD` | `false` | Enable Uvicorn hot-reload |
| `GENERAL_WORKERS` | `4` | Number of Uvicorn worker processes |
| `QDRANT_HOST` | `localhost` | Qdrant server host |
| `QDRANT_PORT` | `6334` | Qdrant server port (dedicated instance) |
| `QDRANT_API_KEY` | `""` | Qdrant API key (if required) |
| `QDRANT_SEARCH_COLLECTION` | `gdce_docs` | Document collection name |
| `QDRANT_TIMEOUT` | `30.0` | Qdrant request timeout (seconds) |
| `QUERY_EMBEDDING_MODEL` | `BAAI/bge-m3` | HuggingFace sentence-transformers model |
| `TOP_K_DEFAULT` | `10` | Default number of results |
| `TOP_K_MAX` | `50` | Maximum allowed results |
| `SIMILARITY_THRESHOLD` | `0.1` | Minimum vector similarity score |
| `GEMINI_API_KEY` | `""` | Google AI Studio API key |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Gemini model ID |
| `GEMINI_ENABLED` | `true` | Enable/disable Gemini answer generation |
| `VLLM_ENABLED` | `false` | Enable optional vLLM fallback |
| `VLLM_HOST` / `VLLM_PORT` | `localhost:8000` | vLLM server address |
| `REDIS_HOST` | `localhost` | Redis server host |
| `REDIS_PORT` | `6380` | Redis server port |
| `REDIS_ENABLED` | `true` | Enable Redis answer caching |
| `REDIS_ANSWER_TTL` | `3600` | Answer cache TTL (seconds, 1h) |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | Comma-separated CORS origins |
| `LOG_LEVEL` | `INFO` | Python log level |
| `RATE_LIMIT_REQUESTS` | `100` | Per-window request limit |
| `CACHE_ENABLED` / `CACHE_TTL_SECONDS` | `true` / `3600` | General cache settings |

---

## API Reference

### `POST /retrieval/retrieve`

Full retrieval pipeline — semantic + structured search, lexical reranking,
and LLM-powered answer generation.

**Request**
```json
{
  "query": "What documents do I need to import goods into Cambodia?",
  "top_k": 10,
  "generate_answer": true,
  "collection": "gdce_docs",
  "require_period_for_trade": true,
  "session_id": "optional-session-id"
}
```

**Response** (abbreviated)
```json
{
  "query": "What documents do I need to import goods into Cambodia?",
  "status": "success",
  "documents": [
    {
      "id": "abc123",
      "content": "Importers must submit a customs declaration form (Form D)...",
      "score": 0.92,
      "source": "semantic",
      "metadata": { "title": "Import Procedures FAQ" }
    }
  ],
  "total_count": 3,
  "semantic_count": 3,
  "structured_count": 0,
  "final_answer": "To import goods into Cambodia, you generally need a customs declaration, commercial invoice, packing list, and bill of lading...",
  "answer_source": "gemini_llm",
  "language": "en",
  "collection_used": "gdce_docs"
}
```

### `GET /health`

Liveness / readiness probe for orchestration tools.

```json
{
  "status": "healthy",
  "components": {
    "vector_store": { "status": "not_checked" },
    "embeddings": { "status": "not_checked" },
    "repository": { "status": "not_checked" }
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

---

## Testing

### Unit Tests (`tests/test_helpers.py`) — 28 tests

Pure-logic tests for:
- **Language detection** — Khmer (Unicode U+1780–U+17FF) vs English.
- **Text normalisation** — whitespace collapse, Khmer→English term expansion.
- **Query processing** — validation, abbreviation expansion (`CIF` → `cost insurance freight`), stopword removal, token deduplication.
- **Trade-data detection** — `_is_trade_data_query` and `_has_time_period` classification logic.
- **Lexical reranking** — exact phrase boost, metadata-chunk penalty, empty-input handling.

### API Integration Tests (`tests/test_api.py`) — 11 tests

FastAPI `TestClient` tests with a fully mocked `GeneralRetrievalService`:
- Request/response contracts and status codes.
- Pydantic validation (missing query, empty query → 422).
- Answer generation on/off.
- Clarification-required flow for trade-data queries.
- Backend failure graceful degradation.
- Service-not-initialised error handling.

---

## Load Testing

Two tools are provided.

### Quick: `concurrency_ramp_test.py`

```bash
pip install aiohttp

# Baseline — test /health first
python load_test/concurrency_ramp_test.py \
  --url http://localhost:8005 \
  --endpoint /health \
  --steps 1,5,10,25,50,100,200

# Full pipeline
python load_test/concurrency_ramp_test.py \
  --url http://localhost:8005 \
  --endpoint /retrieval/retrieve \
  --steps 1,5,10,25,50,100,200 \
  --requests-per-user 3
```

Example output from a real run:

```
 Users |   Reqs |     RPS |  Fail% |   p50ms |   p95ms |   p99ms |   maxms
--------------------------------------------------------------------------
     1 |      3 |     0.1 |   0.0% |  5490.5 | 15408.1 | 15408.1 | 15408.1
     5 |     15 |     0.9 |   0.0% |  4541.9 |  8937.1 |  8937.1 |  8937.1
    10 |     30 |     2.7 |   0.0% |  3184.8 |  6179.5 |  7113.8 |  7113.8
    25 |     75 |     2.5 |   0.0% |  8039.2 | 16287.3 | 24086.6 | 24086.6
    50 |    150 |     3.5 |   6.7% | 12258.6 | 29605.5 | 30907.1 | 30908.2
   100 |    300 |     3.4 |  31.7% | 23197.7 | 31006.2 | 31012.9 | 31013.5

Failure rate 31.7% exceeded threshold (20%) at 100 concurrent users — stopping ramp.
Practical concurrency ceiling looks to be just below 100 users.
```

**How to read:** watch for the step where `Fail%` starts climbing or
`p95ms` jumps sharply (a sudden knee in the curve). The script auto-stops
when failure rate crosses `--fail-fast-threshold` (default 20%).

### Full-featured: Locust

```bash
pip install locust

# Interactive web UI
locust -f load_test/locustfile.py --host http://localhost:8005
# → open http://localhost:8089

# Headless (CI-friendly)
locust -f load_test/locustfile.py --host http://localhost:8005 \
  --users 100 --spawn-rate 10 --run-time 2m --headless --csv=results/run1
```

---

## Deployment

### Docker Compose (full stack)

```bash
docker compose up -d
```

This starts three services:
- `qdrant-general` — vector database (port `6334`)
- `redis-general` — answer cache (port `6380`)
- `general-service` — the FastAPI app (port `8005`)

### Build only the app image

```bash
docker build -t general-service .
docker run -p 8005:8005 --env-file .env general-service
```

---

## Project Structure

```
general/
├── app/
│   ├── main.py                   # FastAPI app entrypoint + service wiring
│   ├── api/
│   │   ├── __init__.py           # Router + schema re-exports
│   │   ├── endpoints.py          # POST /retrieval/retrieve, GET /health, GET /
│   │   ├── exceptions.py         # Domain → HTTP exception mapping
│   │   └── schemas.py            # Pydantic request/response models
│   ├── cache/
│   │   └── redis_client.py       # Fail-open Redis cache client
│   ├── config/
│   │   └── config.py             # Centralised configuration (env vars)
│   ├── core/
│   │   ├── __init__.py           # Component re-exports
│   │   └── exceptions.py         # Exception re-exports
│   ├── embeddings/
│   │   └── embeddings.py         # BAAI/bge-m3 embeddings + keyword fallback
│   ├── exceptions/
│   │   └── exceptions.py         # Domain exception hierarchy
│   ├── llm/
│   │   └── gemini_client.py      # Gemini LLM client (async wrapper)
│   ├── rag/
│   │   ├── answer_generator.py   # Cascading answer: Gemini → vLLM → extractive
│   │   ├── query.py              # Query normalisation, expansion, tokenisation
│   │   ├── retrieval.py          # Semantic + structured search orchestration
│   │   └── service.py            # Business logic: trade-data guard, reranking
│   ├── repositories/
│   │   └── repositories.py       # Optional structured search backend (stub)
│   ├── utils/
│   │   └── language_utils.py     # Khmer/English detection + expansion
│   └── vectorstore/
│       └── vector_store.py       # Qdrant client (dedicated port 6334)
├── prompts/
│   ├── __init__.py               # Prompt loader re-exports
│   ├── loader.py                 # File-backed prompt template loader
│   ├── gemini_system.txt         # Gemini system prompt (customs assistant)
│   ├── gemini_user.txt           # Gemini user prompt (context-grounded)
│   ├── gemini_retry_system.txt   # Gemini retry system prompt
│   ├── gemini_retry_user.txt     # Gemini retry user prompt (reduced context)
│   ├── vllm_system.txt           # vLLM system prompt
│   ├── vllm_user.txt             # vLLM user prompt
│   ├── context_documents.txt     # Context block template
│   ├── context_documents_empty.txt
│   ├── extractive_prefix.txt     # Extractive fallback prefix
│   ├── no_results.txt            # "No results" message
│   ├── no_results_extractive.txt
│   └── clarification_required.txt
├── scripts/
│   ├── markdown_chunk.py         # Chunk + embed Markdown → JSON
│   ├── pdf_chunk.py              # Chunk + embed PDF → JSON
│   └── gdce_docs.json            # Pre-embedded document dataset (not tracked)
├── tests/
│   ├── conftest.py               # sys.path setup for test imports
│   ├── test_api.py               # FastAPI integration tests (11 tests)
│   └── test_helpers.py           # Pure-logic unit tests (28 tests)
├── load_test/
│   ├── concurrency_ramp_test.py  # Standalone async concurrency tester
│   ├── locustfile.py             # Locust load-test definition
│   └── README.md                 # Load-testing guide
├── flowchart/
│   └── endpoint_retrieval_retrieve.png  # Endpoint flow diagram
├── main.py                       # Entry point (Uvicorn bootstrap)
├── requirements.txt              # Python dependencies
├── Dockerfile                    # App container image
├── docker-compose.yml            # Full stack (Qdrant + Redis + App)
├── up.sh                         # One-command start script
└── README.md                     # This file
```
