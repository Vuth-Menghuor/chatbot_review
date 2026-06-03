
# Retrieval Service v2

Independent microservice for retrieving relevant documents and HS code candidates via semantic and structured search.

## Architecture

```
retrieval/
├── core/                      # Business logic
│   ├── ...
├── api/                       # API layer
│   ├── ...
├── infrastructure/            # External integrations
│   ├── ...
├── config.py                  # Environment-based configuration
├── app.py                     # FastAPI application factory
├── main.py                    # Entry point
├── docs/                      # Documentation
```

## Quickstart (Docker Compose)

1. **Install Docker & Docker Compose**
2. **Clone the repository**
3. **Configure Environment**
   - Edit `.env` in `retrieval/`:
     ```env
     QDRANT_HOST=qdrant
     QDRANT_PORT=6333
     ...
     ```
4. **Start services:**
   ```bash
   cd services_version2/retrieval
   sudo docker compose up -d
   ```
5. **Seed Qdrant collections:**
   - Run your collection creation/seed script (e.g., `init_db.py`) with `QDRANT_HOST=qdrant` and `QDRANT_PORT=6333`.
   - Example:
     ```bash
     export QDRANT_HOST=qdrant
     export QDRANT_PORT=6333
     python init_db.py
     ```

## API Usage

### `/v1/hs-code-candidates` (LLM-powered)
- Returns all possible HS code candidates for a product description, with Gemini LLM-powered explanations for each candidate.
- Example request:
  ```json
  {
    "query": "cotton fabric",
    "generate_answer": true
  }
  ```
- Example response:
  ```json
  {
    "documents": [ ... ],
    "final_answer": "5208: Used for woven cotton fabrics, typically plain weave. 5209: Unbleached cotton fabrics, often used for further processing.",
    "answer_source": "gemini_llm"
  }
  ```

## Troubleshooting
- If you see `Not found: Collection 'gdce_hs_code' doesn't exist!`, ensure you have seeded the collection in the Docker Qdrant instance.
- If Qdrant is `unhealthy`, check logs with `sudo docker logs qdrant` and resolve any errors.
- Always use `QDRANT_HOST=qdrant` in Docker Compose; use `localhost` only for local (non-Docker) runs.

## Documentation
- See `docs/README.md`, `docs/retrieval_api.md`, and other files in `docs/` for full API and integration details.

### 3. Run Service

```bash
# Using Python module
python -m services_version2.retrieval.main

# Using Uvicorn directly
uvicorn services_version2.retrieval.app:app --reload
```

Service will be available at `http://localhost:8001`



## API Endpoints

### POST /v1/hs-code-lookup

HS code lookup. Returns all candidate codes in the `documents`, `candidate_docs`, and `candidates` fields. The orchestrator or UI should display these for user review and selection. Retrieval does not make the final HS code selection in best-mode.

### POST /v1/hs-code-candidates

Returns all possible HS code candidates for a product description, with Gemini LLM-powered explanations for each candidate. The LLM does not summarize the HS code descriptions, but explains each clearly and concisely, especially when the context is broad.

**Request:**

```json
{
  "query": "cotton fabric",
  "generate_answer": true
}
```

**Response:**

```json
{
  "query": "cotton fabric",
  "documents": [
    { "id": "1", "content": "Woven fabrics of cotton", "score": 0.95, "source": "semantic", "metadata": { "hs_code": "5208" } },
    { "id": "2", "content": "Unbleached cotton fabrics", "score": 0.91, "source": "semantic", "metadata": { "hs_code": "5209" } }
  ],
  "final_answer": "5208: Used for woven cotton fabrics, typically plain weave. 5209: Unbleached cotton fabrics, often used for further processing.",
  "answer_source": "gemini_llm",
  "status": "success",
  "api_called": "/v1/hs-code-candidates",
  "total_count": 2
}
```

---

### GET /api/v1/retrieval/health

Check health of all service components.

**Response:**

```json
{
  "status": "healthy",
  "components": {
    "vector_store": {
      "status": "healthy",
      "host": "localhost",
      "port": 6333,
      "collection": "documents",
      "collection_exists": true
    },
    "embeddings": {
      "status": "healthy",
      "model": "all-MiniLM-L6-v2",
      "embedding_dim": 384
    },
    "repository": {
      "status": "healthy"
    }
  }
}
```

## Components

### Query Processor

- Validates query length and content
- Normalizes text (lowercase, whitespace)
- Expands with synonyms (CIF, VAT, HS Code, etc.)
- Tokenizes and extracts meaningful tokens

### Retrieval Orchestrator

- Coordinates semantic and structured search
- Executes parallel searches when applicable
- Aggregates and deduplicates results
- Ranks results if ranker available

### Service Layer

- Implements business rules for top-k and filtering
- Manages component initialization
- Provides health checks
- Handles error cases gracefully

### Infrastructure

- **VectorStoreClient**: Wraps Qdrant for semantic search
- **EmbeddingClient**: Lazy-loads sentence-transformer models
- **DocumentRepository**: Provides structured data access
- **DBPool**: Connection pooling for database access

## Configuration

All configuration via environment variables (no local files).

| Variable          | Default          | Description               |
| ----------------- | ---------------- | ------------------------- |
| RETRIEVAL_HOST    | 0.0.0.0          | Service host              |
| RETRIEVAL_PORT    | 8001             | Service port              |
| QDRANT_HOST       | localhost        | Qdrant host               |
| QDRANT_PORT       | 6333             | Qdrant port               |
| QDRANT_COLLECTION | documents        | Vector collection name    |
| EMBEDDING_MODEL   | all-MiniLM-L6-v2 | Embedding model           |
| TOP_K_DEFAULT     | 10               | Default results limit     |
| TOP_K_MAX         | 50               | Maximum results limit     |
| REQUEST_TIMEOUT   | 30               | Request timeout (seconds) |

## Testing

Create test file `test_retrieval.py`:

```python
import pytest
from httpx import AsyncClient
from services_version2.retrieval_version2.app import app


@pytest.mark.asyncio
async def test_retrieve():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/retrieval/retrieve",
            json={"query": "test query", "top_k": 5}
        )
        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "status" in data


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/v1/retrieval/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
```

Run tests:

```bash
pytest test_retrieval.py -v
```


## Integration with Orchestrator

The orchestrator should call the `/v1/hs-code-lookup` endpoint for HS code queries and display the `documents`, `candidate_docs`, and `candidates` fields for user review. The retrieval service is responsible for candidate discovery and validation, not for making the final HS code selection in best-mode.

## Troubleshooting

### Vector Store Connection Error

- Ensure Qdrant is running: `docker-compose up qdrant`
- Verify QDRANT_HOST and QDRANT_PORT

### Embedding Model Loading Error

- First run downloads model (~100MB)
- Ensure internet connection
- Check disk space

### No Results Returned

- Verify collection exists in Qdrant
- Check if documents are indexed
- Review query tokens in logs

## Performance

- **Query Processing**: < 10ms
- **Embedding**: ~100-500ms (first run) or ~50-100ms (cached)
- **Vector Search**: ~10-50ms depending on collection size
- **End-to-end**: ~200-600ms typical

## Future Enhancements

- [ ] Result caching (Redis)
- [ ] Batch retrieval API
- [ ] Custom ranker implementation
- [ ] Structured query language support
- [ ] Query analytics and logging
