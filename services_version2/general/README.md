# General Retrieval Service

Independent microservice for general / FAQ / definition / policy-style document
retrieval. This is a sibling of `services_version2/retrieval` (the HS-code
focused service on port 8003), but with all HS-code-specific logic removed
(no ambiguity detection, no GIR reasoning, no rule-based HS matching, no
hs_mode/select/compare). It runs against its **own dedicated Qdrant
instance** so general document traffic and growth never compete with or
pollute HS code vector search.

| | HS-code retrieval service | General retrieval service |
|---|---|---|
| Port | 8003 | **8005** |
| Qdrant (Docker internal) | `qdrant:6333` | `qdrant-general:6333` |
| Qdrant (host-mapped) | `localhost:6333` | `localhost:6334` |
| Collections | `gdce_docs`, `gdce_hs_code` | `gdce_docs` |
| Endpoints | `/retrieval/retrieve`, `/hs-code-candidates`, `/hs-code-ranked`, `/health` | `/retrieval/retrieve`, `/health` |

## Architecture

```
general/
├── core/                      # Business logic (trade-period guard, lexical rerank)
│   ├── query.py
│   ├── retrieval.py
│   ├── service.py             # GeneralRetrievalService — no HS logic
│   ├── answer_generator.py
│   ├── language_utils.py
│   └── exceptions.py
├── api/                       # API layer
│   ├── endpoints.py           # POST /retrieval/retrieve, GET /health, GET /
│   ├── schemas.py
│   └── exceptions.py
├── infrastructure/            # External integrations
│   ├── vector_store.py        # Qdrant client
│   ├── embeddings.py          # sentence-transformers (with keyword fallback)
│   ├── repositories.py
│   └── gemini_client.py       # Generic Q&A prompt only
├── config.py                  # Environment-based configuration
├── app.py                     # FastAPI application factory
├── main.py                    # Entry point
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── up.sh
└── .env.example
```

## Quickstart (Docker Compose)

1. **Install Docker & Docker Compose**
2. **Create the external Qdrant volume (one-time):**
   ```bash
   docker volume create general_version2_qdrant_data
   ```
3. **Configure environment**
   - Copy `.env.example` to `.env` and fill in `GEMINI_API_KEY` at minimum.
   - `docker-compose.yml` already overrides `QDRANT_HOST`/`QDRANT_PORT` for
     the in-container network (`qdrant-general:6333`), so you don't need to
     change those for Docker runs.
4. **Start services:**
   ```bash
   cd services_version2/general
   ./up.sh
   # or: docker compose up -d
   ```
5. **Seed the `gdce_docs` collection** in this Qdrant instance (point your
   existing document-loading script at `localhost:6334` instead of `6333`,
   or `qdrant-general:6333` if running the loader inside the same Docker
   network). No data was migrated automatically — this is a fresh Qdrant
   instance and needs its own ingestion run.

## Running locally (no Docker)

```bash
# Start a local Qdrant on port 6334
docker run -p 6334:6333 qdrant/qdrant:v1.17.0

# In .env (or exported env vars):
#   QDRANT_HOST=localhost
#   QDRANT_PORT=6334

cd services_version2/general
pip install -r requirements.txt
python -m services_version2.general.main
# or: uvicorn app:app --reload --host 127.0.0.1 --port 8005
```

## API Usage

### `POST /retrieval/retrieve`

```json
{
  "query": "What documents do I need to import goods into Cambodia?",
  "top_k": 10,
  "generate_answer": true
}
```

Response:

```json
{
  "query": "What documents do I need to import goods into Cambodia?",
  "status": "success",
  "documents": [
    {
      "id": "doc-001",
      "content": "Importers must submit a customs declaration form...",
      "score": 0.92,
      "source": "semantic",
      "metadata": { "title": "Import Procedures FAQ" }
    }
  ],
  "total_count": 1,
  "final_answer": "To import goods into Cambodia, you generally need a customs declaration, commercial invoice, and packing list.",
  "answer_source": "gemini_llm",
  "collection_used": "gdce_docs"
}
```

### `GET /health`

Returns service status. Component-level checks (`vector_store`, `embeddings`,
`repository`) return `"not_checked"` by default for fast response times,
consistent with the HS-code retrieval service's health endpoint.

## Troubleshooting

- **`Not found: Collection 'gdce_docs' doesn't exist!`** — this Qdrant
  instance starts empty. Run a document-loading script against
  `localhost:6334` (or `qdrant-general:6333` inside Docker) to seed it.
- **Connection refused on 6334** — confirm the `qdrant-general` container is
  running: `docker ps | grep qdrant-general`, and check logs with
  `docker logs qdrant-general`.
- **Port conflicts with the existing retrieval service** — this service
  uses 8005/6334 specifically to avoid colliding with retrieval's 8003/6333.
  If you changed those defaults, double check `.env` and `docker-compose.yml`
  stay in sync.
