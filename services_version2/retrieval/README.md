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
