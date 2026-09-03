"""
Retrieval Service Package (v2).

This package contains the FastAPI application, API routes, and all
infrastructure clients (vector store, embeddings, LLM, cache) needed
to serve HS-code classification queries against the ``gdce_hs_code``
Qdrant collection.

Sub-packages
------------
api         — FastAPI router, request/response schemas, endpoint handlers.
cache       — Redis cache client (fail-open, async).
embeddings  — Sentence-transformer query embedding with keyword fallback.
llm         — Gemini (Google Generative AI) client for answer generation.
rag         — Retrieval orchestration and high-level service layer.
vectorstore — Qdrant vector-database client.
"""