# GDCE Orchestrator Service

The **Orchestrator** is the central API gateway for the GDCE Customs Chatbot platform. It receives user queries, detects intent, rewrites context-aware follow-up questions, and routes requests to the appropriate downstream microservices.

---

## Architecture Overview

```
User Query
    │
    ▼
┌──────────────────────────────┐
│       Orchestrator (8001)    │
│  ┌──────────────────────┐   │
│  │  InputRewriter       │   │  ← Context-aware query rewriting
│  │  (Gemini / Ollama)   │   │     using session history + slots
│  └──────────────────────┘   │
│  ┌──────────────────────┐   │
│  │  Intent Detection    │   │  ← Classify: hs_code / calculation
│  │  (LLM First Layer)   │   │     / trade_query / general
│  └──────────────────────┘   │
│  ┌──────────────────────┐   │
│  │  Coordinator         │   │  ← Route to downstream service
│  └──────────────────────┘   │
└──────────────┬───────────────┘
               │
    ┌──────────┼──────────┐
    ▼          ▼          ▼
 Retrieval  Calculator  Trade Data
 (8003)     (8002)      (8004)
```

---

## Services

| Service | Port | Purpose |
|---|---|---|
| Orchestrator | 8001 | Main entry point, intent routing |
| Calculator | 8002 | Import/export duty calculation |
| Retrieval | 8003 | RAG document retrieval (Qdrant) |
| Trade Data | 8004 | Trade statistics queries |
| General | 8005 | General GDCE information |

---

## Quick Start

### 1. Clone and setup environment

```bash
cp .env.example .env
# Fill in your real values in .env
```

### 2. Run in development mode

```bash
bash scripts/run_dev.sh
```

### 3. Run tests

```bash
bash scripts/test.sh
```

### 4. Run with Docker

> [!IMPORTANT]
> The Docker Compose configuration uses an external network named `gdce-network` for communication between all microservices. You must create this network before booting up the container.

```bash
# 1. Create the external docker network
docker network create gdce-network

# 2. Boot up the containers
docker-compose up --build
```

### 5. Caching and Redis Setup

By default, the Redis caching layer is disabled in the `.env` file (`CACHE_ENABLED=false`). To enable caching of downstream service calls (like customs calculations, trade statistics, and HS code lookups):

1. Set `CACHE_ENABLED=true` in your `.env` file.
2. Ensure the Redis container is running (it starts automatically with `docker-compose`).

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/chat` | Main chat endpoint |
| GET | `/health` | Service health check |
| GET | `/api/v1/session/{session_id}` | Get session context |
| DELETE | `/api/v1/session/{session_id}` | Clear session |

Full API docs available at `http://localhost:8001/docs` when running.

---

## Project Structure

```
orchestrator/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── api/                 # API routes and schemas
│   ├── core/                # Config, logging, exceptions, middleware
│   ├── services/ (→ core/)  # Business logic (coordinator, workflow, rewriter)
│   ├── ai/ (→ llm_service/) # LLM providers (Gemini, Ollama)
│   ├── infrastructure/      # HTTP clients, Redis cache, health checks
│   ├── prompts/             # Dynamic prompt system (YAML-based)
│   └── utils.py             # Shared utilities
├── tests/                   # Automated test suite
├── scripts/                 # Dev/deploy helper scripts
├── docs/                    # Architecture and API documentation
├── .env.example             # Environment variable template
└── Dockerfile               # Container build config
```

---

## LLM Provider Priority

The `InputRewriter` uses a tiered provider system:

1. **Gemini** (primary) — fast cloud inference, uses `GEMINI_API_KEY`
2. **Ollama** (fallback) — local model, uses `OLLAMA_HOST`
3. **Deterministic slots** (always) — regex-based, zero latency, always works offline

---

## Environment Variables

See [.env.example](.env.example) for the full list of required variables.

Key variables:

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Gemini model name (e.g. `gemini-2.0-flash-lite`) |
| `OLLAMA_HOST` | Ollama server URL (e.g. `http://localhost:11434`) |
| `ORCHESTRATOR_PORT` | Port to run the service on (default: 8001) |
| `RETRIEVAL_SERVICE_URL` | URL of the retrieval microservice |
| `CALCULATOR_SERVICE_URL` | URL of the calculator microservice |

---

## Running Tests

```bash
# All tests
pytest tests/ -v

# Specific test file
pytest tests/test_input_rewriter.py -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```
