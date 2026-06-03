# GDCE Orchestrator Service v2

## Overview

The Orchestrator Service v2 is an **independent microservice** that coordinates queries across multiple backend services (Retrieval, Calculator, Trade Data). It provides intelligent intent detection, service routing, and response aggregation.

This is a **new, clean implementation** that eliminates dependencies on local configuration files and follows proper microservice architecture patterns.

### Key Features

- **Intent-Based Routing**: Automatically detects question intent (calculation, trade query, definition) and routes to appropriate service
- **Multi-Service Orchestration**: Coordinates requests across Retrieval, Calculator, and Trade Data services
- **Intelligent Fallback**: Falls back to retrieval service when primary service fails
- **Policy-Driven Architecture**: Uses configurable policies for routing and validation
- **Request Tracking**: Full request/response lifecycle tracking with latency measurement
- **Health Monitoring**: Built-in health checks for all dependent services
- **Independent Configuration**: All configuration via environment variables - no local config files needed

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI App                             │
│                       (app.py / main.py)                        │
└──────────────────┬──────────────────────────────────────────────┘
                   │
         ┌─────────┴────────────────┐
         │                          │
    ┌────▼──────┐            ┌─────▼─────┐
    │   API     │            │ Core      │
    ├───────────┤            ├───────────┤
    │Endpoints  │            │Workflow   │
    │Schemas    │            │Coordinator│
    │           │            │Policies   │
    └─────┬─────┘            └──┬───┬───┘
          │                     │   │
    ┌─────▼─────────────────────┬─┬─┴──────────────────┐
    │                           │ │                    │
┌───▼─────────────┐     ┌──────▼─▼──┐        ┌────────▼────┐
│ Infrastructure  │     │  Config   │        │  Policies   │
├─────────────────┤     ├───────────┤        ├─────────────┤
│Service Clients  │     │Env-based  │        │Intent Rules │
│Retry/Fallback   │     │No local   │        │Validation   │
└─────────────────┘     │files      │        │Fallback     │
                        └───────────┘        └─────────────┘
         │                    │
         └────────────────────┴─────────────────────┐
                                                    │
        ┌───────────────────────────────────────────┴─────────────┐
        │                                                          │
   ┌────▼──────────────┐        ┌──────────────┐      ┌──────────▼──┐
   │   Retrieval       │        │  Calculator  │      │  Trade Data │
   │   Service         │        │  Service     │      │  Service    │
   └───────────────────┘        └──────────────┘      └─────────────┘
```

## Folder Structure

```
services_version2/orchestrator_version2/
├── core/                      # Core orchestration logic
│   ├── __init__.py
│   ├── workflow.py           # Workflow execution and intent detection
│   ├── coordinator.py        # Service coordination logic
│   └── policies.py           # Policies and routing rules
├── api/                      # FastAPI application
│   ├── __init__.py
│   ├── endpoints.py          # API route handlers
│   └── schemas.py            # Pydantic request/response models
├── infrastructure/           # Service communication
│   ├── __init__.py
│   └── clients.py            # HTTP clients for dependent services
├── tests/                    # Unit and integration tests
│   ├── __init__.py
│   ├── conftest.py          # Test fixtures
│   ├── test_workflow.py
│   ├── test_coordinator.py
│   └── test_endpoints.py
├── config.py                # Configuration management (env-based)
├── config.yaml              # Configuration documentation
├── app.py                   # FastAPI application factory
├── main.py                  # Entry point
├── __init__.py
└── README.md               # This file
```

## Configuration

### Environment Variables

All configuration is environment-based. No local configuration files are required.

**Server Configuration:**

```bash
ORCHESTRATOR_HOST=127.0.0.1
ORCHESTRATOR_PORT=8001
ORCHESTRATOR_RELOAD=false
ORCHESTRATOR_WORKERS=4
LOG_LEVEL=INFO
```

**Service URLs:**

```bash
RETRIEVAL_SERVICE_URL=http://localhost:8000
CALCULATOR_SERVICE_URL=http://localhost:8002
TRADE_DATA_SERVICE_URL=http://localhost:8004
```

**Vector/Search Configuration:**

```bash
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_SEARCH_COLLECTION=rag_documents
QUERY_EMBEDDING_MODEL=sentence-transformers/multilingual-e5-base
```

**LLM Configuration:**

```bash
VLLM_HOST=localhost
VLLM_PORT=8000
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=mistral-7b
```

**Security:**

```bash
RATE_LIMIT_REQUESTS=100
MAX_PAYLOAD_SIZE_MB=10
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000
```

### .env File

Create a `.env` file in the project root:

```bash
# Server
ORCHESTRATOR_HOST=127.0.0.1
ORCHESTRATOR_PORT=8001

# Services
RETRIEVAL_SERVICE_URL=http://localhost:8000
CALCULATOR_SERVICE_URL=http://localhost:8002
TRADE_DATA_SERVICE_URL=http://localhost:8004

# Vector Search
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Security
RATE_LIMIT_REQUESTS=100
ALLOWED_ORIGINS=http://localhost:3000
```

## Installation

1. **Install Dependencies:**

```bash
cd services_version2/orchestrator_version2
pip install -r requirements.txt
```

Required packages:

- fastapi >= 0.109.0
- uvicorn >= 0.27.0
- pydantic >= 2.7.0
- httpx >= 0.26.0
- python-dotenv >= 1.0.1
- pytest >= 7.4.4
- pytest-asyncio >= 0.23.3

2. **Configure Environment:**

```bash
# Copy config.yaml to understand available settings
cat config.yaml

# Create .env file with your configuration
cp .env.example .env
# Edit .env with your service URLs
```

3. **Verify Installation:**

```bash
python -c "from app import app; print('✓ Installation successful')"
```

## Running the Service

### Development Mode

```bash
# With auto-reload
ORCHESTRATOR_RELOAD=true python main.py
```

### Production Mode

```bash
# With multiple workers
ORCHESTRATOR_WORKERS=4 python main.py
```

### Using Uvicorn Directly

```bash
uvicorn app:app --host 127.0.0.1 --port 8001 --workers 4
```

## API Endpoints

### POST `/query`

Process a user query and route to appropriate service(s).

**Request:**

```json
{
  "question": "What is the import tax on 100 USD of electronics from China?",
  "session_id": "optional_session_123"
}
```

**Response:**

```json
{
  "request_id": "req_abc123",
  "question": "What is the import tax on 100 USD of electronics from China?",
  "answer": "Based on the calculation...",
  "intent": "calculation",
  "status": "completed",
  "citations": [
    {
      "doc_id": "HS_8471",
      "title": "HS Code 84.71",
      "snippet": "Electronic data processing machines...",
      "score": 0.95
    }
  ],
  "latency_ms": 234.5,
  "metadata": {}
}
```

### GET `/health`

Check health status of orchestrator and all dependent services.

**Response:**

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2024-01-15T10:30:45.123Z",
  "services": {
    "retrieval": {
      "status": "healthy",
      "latency_ms": 50
    },
    "calculator": {
      "status": "healthy",
      "latency_ms": 30
    }
  }
}
```

### GET `/status`

Get service status and configuration.

### GET `/info`

Get service information and capabilities.

### POST `/query/explain`

Explain how the orchestrator will handle a query (useful for debugging).

**Request:**

```json
{
  "question": "Calculate import tax on 100 USD of goods"
}
```

**Response:**

```json
{
  "question": "Calculate import tax on 100 USD of goods",
  "intent": "calculation",
  "intent_details": {
    "name": "calculation",
    "description": "Query detected as calculation query"
  },
  "routing": {
    "sequence": ["calculator"],
    "services_to_call": ["calculator"]
  },
  "validation": {
    "calculation_valid": true,
    "missing_fields": null
  }
}
```

## Intent Detection

The orchestrator automatically detects query intent:

| Intent           | Pattern                                                  | Routed To          |
| ---------------- | -------------------------------------------------------- | ------------------ |
| **calculation**  | Contains: calculate, compute, how much, import tax, duty | Calculator Service |
| **trade_query**  | Contains: trade, export, import, shipping, cargo         | Trade Data Service |
| **definition**   | Contains: what is, define, explain                       | Retrieval Service  |
| **policy_query** | General customs/procedure questions                      | Retrieval Service  |

## Testing

### Run All Tests

```bash
pytest tests/
```

### Run Specific Test Module

```bash
pytest tests/test_workflow.py -v
pytest tests/test_coordinator.py -v
pytest tests/test_endpoints.py -v
```

### Run with Coverage

```bash
pytest tests/ --cov=. --cov-report=html
```

### Run Specific Test

```bash
pytest tests/test_workflow.py::TestWorkflowIntentDetection::test_detect_calculation_intent -v
```

## Development

### Project Layout Philosophy

- **core/**: Pure Python business logic - no dependencies on FastAPI/HTTP
- **api/**: FastAPI routes, schemas, dependency injection
- **infrastructure/**: Service clients, connection handling
- **config.py**: Configuration management (env-based)

### Adding New Intent Type

1. Add to `WorkflowIntent` enum in `core/workflow.py`
2. Add detection pattern to `WorkflowExecutor.detect_intent()`
3. Add routing in `core/coordinator.py`
4. Add tests in `tests/test_workflow.py`

### Adding New Service

1. Create client in `infrastructure/clients.py`
2. Update `ServiceClientFactory`
3. Register in `initialize_service_clients()` in `app.py`
4. Update routing policies in `core/policies.py`
5. Add tests

## Debugging

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG python main.py
```

### Check Service Configuration

```bash
curl http://localhost:8001/status
```

### Health Check

```bash
curl http://localhost:8001/health
```

### Query Explanation

```bash
curl -X POST http://localhost:8001/query/explain \
  -H "Content-Type: application/json" \
  -d '{"question":"What is HS code?"}'
```

### View API Documentation

- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

## Performance

### Optimization Tips

1. **Tune Worker Count**: Match number of available CPU cores

   ```bash
   ORCHESTRATOR_WORKERS=4 python main.py
   ```

2. **Connection Pooling**: Automatically handled by httpx client

3. **Caching**: Implement result caching based on intent type

4. **Service Timeouts**: Adjust via environment variables

### Monitoring

The service provides metrics via:

- Request latency tracking
- Service health endpoints
- Error logging and tracking

## Troubleshooting

### Service Won't Start

Check configuration:

```bash
python -c "from config import get_config; config = get_config(); print(config.to_dict())"
```

### Dependent Services Not Responding

Check health:

```bash
curl http://localhost:8001/health
```

### Intent Detection Issues

Test with explain endpoint:

```bash
curl -X POST http://localhost:8001/query/explain \
  -H "Content-Type: application/json" \
  -d '{"question":"Your test question"}'
```

## Production Deployment

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

### Environment Setup

```bash
# Use strong secrets for CORS origins
ALLOWED_ORIGINS=https://your-domain.com

# Configure actual service URLs
RETRIEVAL_SERVICE_URL=https://retrieval.your-domain.com
CALCULATOR_SERVICE_URL=https://calculator.your-domain.com

# Set log level
LOG_LEVEL=INFO

# Use appropriate worker count
ORCHESTRATOR_WORKERS=8
```

### Health Check

Include in deployment configs:

```bash
HEALTHCHECK --interval=30s --timeout=10s \
  CMD curl -f http://localhost:8001/health || exit 1
```

## References

- FastAPI Documentation: https://fastapi.tiangolo.com
- Pydantic Documentation: https://docs.pydantic.dev
- Testing: See `tests/` directory for examples

## Versioning

- **Current Version**: 2.0.0
- **Previous Version**: 1.x (legacy, in `services/orchestrator/`)
- **Status**: Production-ready

## License

Part of GDCE (General Department of Customs and Excise) project.

## Support

For issues or questions:

1. Check `troubleshooting` section above
2. Review test cases in `tests/`
3. Check service health with `/health` endpoint
4. Enable debug logging with `LOG_LEVEL=DEBUG`
