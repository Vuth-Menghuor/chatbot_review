"""
Service Layer — Retrieval Service.

High-level service that owns:

- **HS corpus loading** — full-collection scroll from Qdrant, cached
  in-process (fast) and optionally in Redis (cross-process).
- **6-digit HS prefix lookup** — given a prefix like ``"870323"``, returns
  all documents under that international subheading family.
- **Lexical candidate scoring** — token-overlap + heading-match scoring
  to re-rank prefix-scan results.
- **Health reporting** — lightweight liveness check.

This module is the bridge between the thin ``RetrievalOrchestrator`` and
the API layer in ``endpoints.py``.
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    High-level retrieval service for HS code classification.

    Responsibilities
    ----------------
    - Maintain a cached, in-memory scan of the ``gdce_hs_code`` Qdrant
      collection (with optional Redis-backed cross-process caching) so
      6-digit HS prefix lookups don't require a full collection scroll
      per request.
    - Score HS candidates against a free-text query using simple lexical
      heading / token matching.
    - Report service health.

    Parameters
    ----------
    retrieval_orchestrator : RetrievalOrchestrator
        Semantic search wrapper.
    config : RetrievalConfig
        Service configuration.
    gemini_client : Optional[GeminiClient]
        Gemini LLM client for answer generation (optional).
    cache_client : Optional[CacheClient]
        Redis cache client for HS corpus caching (optional).
    """

    def __init__(
        self,
        retrieval_orchestrator,
        config=None,
        gemini_client=None,
        cache_client=None,
    ):
        self.orchestrator = retrieval_orchestrator
        self.config = config
        self.gemini_client = gemini_client
        self.cache = cache_client
        # In-process HS corpus cache: {collection_name: [entry, ...]}
        self._hs_corpus_cache: Dict[str, List[dict]] = {}

    # ==================================================================
    # Startup pre-warm
    # ==================================================================

    async def prewarm(self) -> None:
        """
        Pre-load the HS corpus at startup so the first client request
        does not pay the full-collection scroll penalty.
        """
        collection = getattr(
            self.config, "qdrant_hs_code_collection", "gdce_hs_code"
        )
        logger.info("Pre-warming HS corpus for collection: %s", collection)
        corpus = await self._load_hs_corpus_async(collection)
        logger.info("Pre-warm complete — %d HS entries cached", len(corpus))

    # ==================================================================
    # HS Corpus Loading (in-memory + Redis)
    # ==================================================================

    @staticmethod
    def _tokenize_text(value: str) -> List[str]:
        """Extract lowercase alphanumeric tokens from a string."""
        return re.findall(r"[a-z0-9]+", (value or "").lower())

    def _load_hs_corpus(self, collection_name: str) -> List[dict]:
        """
        Synchronous full scroll of the HS Qdrant collection.

        **Always call via ``_load_hs_corpus_async`` from async contexts.**
        This method blocks and must be wrapped in ``asyncio.to_thread``.

        Returns a list of lightweight entry dicts:
        ``{"id": ..., "hs_code": ..., "text": ..., "tokens": set(...)}``.
        Result is cached in ``self._hs_corpus_cache``.
        """
        # Return cached if already loaded in this process.
        cached = self._hs_corpus_cache.get(collection_name)
        if cached is not None:
            return cached

        vector_store = getattr(self.orchestrator, "vector_store", None)
        client = getattr(vector_store, "client", None)
        if client is None:
            self._hs_corpus_cache[collection_name] = []
            return []

        corpus: List[dict] = []
        offset = None
        page_size = 1024  # scroll in pages to keep memory bounded

        try:
            while True:
                points, offset = client.scroll(
                    collection_name=collection_name,
                    offset=offset,
                    limit=page_size,
                    with_payload=True,
                    with_vectors=False,  # we only need payload text
                )
                if not points:
                    break

                for point in points:
                    payload = point.payload or {}
                    hs_code = payload.get("hs_code")
                    if not hs_code:
                        continue
                    # Build a single searchable text blob from all payload fields.
                    text = " ".join(
                        str(payload.get(field) or "")
                        for field in (
                            "description", "title", "text", "content", "hs_code",
                        )
                    ).strip()
                    tokens = set(self._tokenize_text(text))
                    corpus.append({
                        "id": point.id,
                        "hs_code": str(hs_code),
                        "text": text,
                        "tokens": tokens,
                    })

                if offset is None:
                    break
        except Exception as exc:
            logger.debug("HS corpus scan failed: %s", exc)
            corpus = []

        self._hs_corpus_cache[collection_name] = corpus
        logger.info(
            "HS corpus loaded: %d entries for '%s'", len(corpus), collection_name
        )
        return corpus

    async def _load_hs_corpus_async(self, collection_name: str) -> List[dict]:
        """
        Async wrapper for corpus loading with three-tier cache:

        1. **In-process** — instant if already loaded.
        2. **Redis** — shared across workers; avoids duplicate scrolls.
        3. **Qdrant scroll** — blocking full scan, run in thread pool.
        """
        # Tier 1: in-process cache.
        cached = self._hs_corpus_cache.get(collection_name)
        if cached is not None:
            return cached

        # Tier 2: Redis cache.
        if self.cache:
            redis_key = self.cache.make_key("hs_corpus", collection_name)
            cached_remote = await self.cache.get_json(redis_key)
            if cached_remote is not None:
                # JSON round-trips ``set`` → ``list``; restore token sets.
                for entry in cached_remote:
                    entry["tokens"] = set(entry.get("tokens", []))
                self._hs_corpus_cache[collection_name] = cached_remote
                logger.info(
                    "HS corpus loaded from Redis: %d entries", len(cached_remote)
                )
                return cached_remote

        # Tier 3: full Qdrant scroll (blocking → thread pool).
        import asyncio

        corpus = await asyncio.to_thread(
            self._load_hs_corpus, collection_name
        )

        # Write back to Redis for other workers.
        if self.cache and corpus:
            serializable = [
                {**e, "tokens": list(e["tokens"])} for e in corpus
            ]
            redis_key = self.cache.make_key("hs_corpus", collection_name)
            ttl = getattr(self.config, "redis_corpus_ttl", 21600)
            await self.cache.set_json(redis_key, serializable, ttl=ttl)

        return corpus

    # ==================================================================
    # HS Prefix Lookup
    # ==================================================================

    def fetch_hs_documents_by_prefix(
        self, prefix: str, collection_name: str, limit: int = 300
    ) -> List[dict]:
        """
        Fetch all HS documents whose HS code starts with the given 6-digit
        prefix. Requires a warm corpus (loaded via ``_load_hs_corpus``).

        Returns up to ``limit`` document dicts in a standard shape suitable
        for the candidate pipeline.
        """
        prefix_digits = re.sub(r"\D", "", str(prefix or ""))[:6]
        if len(prefix_digits) < 6:
            return []

        docs: List[dict] = []
        seen_doc_ids: set = set()
        for entry in self._load_hs_corpus(collection_name):
            hs_code = str(entry.get("hs_code") or "")
            hs_digits = re.sub(r"\D", "", hs_code)
            if not hs_digits.startswith(prefix_digits):
                continue

            doc_id = str(entry.get("id") or hs_code)
            if doc_id in seen_doc_ids:
                continue
            seen_doc_ids.add(doc_id)

            docs.append({
                "id": entry.get("id") or hs_code,
                "score": 0.95,  # prefix match = high baseline confidence
                "retrieval_source": "structured_prefix_scan",
                "hs_code": hs_code,
                "description": entry.get("text") or entry.get("description") or "",
                "search_text": entry.get("text") or entry.get("description") or "",
                "text": entry.get("text") or entry.get("description") or "",
                "content": entry.get("text") or entry.get("description") or "",
                "metadata": {
                    "hs_code": hs_code,
                    "hs_prefix": prefix_digits,
                },
            })
            if len(docs) >= limit:
                break

        return docs

    async def fetch_hs_documents_by_prefix_async(
        self, prefix: str, collection_name: str, limit: int = 100
    ) -> List[dict]:
        """
        Non-blocking version of ``fetch_hs_documents_by_prefix``.

        Ensures the corpus is warm, then runs the synchronous lookup in a
        thread pool to avoid blocking the event loop.
        """
        import asyncio

        await self._load_hs_corpus_async(collection_name)
        return await asyncio.to_thread(
            self.fetch_hs_documents_by_prefix, prefix, collection_name, limit
        )

    # ==================================================================
    # Candidate Scoring
    # ==================================================================

    @staticmethod
    def _hs_heading(raw: Optional[str]) -> Optional[str]:
        """Extract the 4-digit HS heading from a full HS code."""
        if not raw:
            return None
        digits = re.sub(r"\D", "", str(raw))
        return digits[:4] if len(digits) >= 4 else None

    @staticmethod
    def _score_hs_candidates_by_query(
        query: str, documents: List[dict], target_heading: str
    ) -> List[dict]:
        """
        Apply light lexical scoring over prefix-scan candidates to improve
        subheading precision.

        Scoring factors:
        - Token-overlap ratio between query and document text.
        - Bonus if the document's 4-digit heading matches ``target_heading``.
        - Special-case bonuses for common HS disambiguation phrases
          (e.g. "same housing", "not exceeding", "spark-ignition",
          "marine", "diesel-electric").

        Returns the document list with adjusted ``score`` fields, sorted
        descending.
        """
        q = (query or "").lower()
        stop_words = {
            "what", "is", "the", "hs", "code", "for", "of", "to", "a", "an",
            "and", "or", "with", "in", "on", "applies", "covers", "use",
            "should", "i", "other", "type",
        }
        query_tokens = [
            t for t in re.findall(r"[a-z0-9\.\-]+", q)
            if t not in stop_words and len(t) > 1
        ]

        boosted: List[dict] = []
        for doc in documents or []:
            hs_code = doc.get("hs_code")
            if hs_code is None and isinstance(doc.get("metadata"), dict):
                hs_code = doc["metadata"].get("hs_code")

            heading = RetrievalService._hs_heading(hs_code)
            text = " ".join(
                str(doc.get(field) or "")
                for field in ("title", "description", "text", "content", "hs_code")
            ).lower()

            overlap = sum(1 for t in query_tokens if t in text)
            ratio = overlap / max(1, len(query_tokens))

            # --- Special-case bonuses -------------------------------------
            bonus = 0.0
            if heading == target_heading:
                bonus += 0.30
            if "same housing" in q and "same housing" in text:
                bonus += 0.35
            if "not exceeding" in q and "not exceeding" in text:
                bonus += 0.30
            if "spark" in q and "ignition" in q and "spark-ignition" in text:
                bonus += 0.30
            if "marine" in q and "marine" in text:
                bonus += 0.20
            if (
                "diesel-electric" in q
                and "diesel" in text
                and "electric" in text
            ):
                bonus += 0.25

            base = float(doc.get("score", 0.0) or 0.0)
            adjusted = min(1.0, max(base, 0.15 + (ratio * 0.6) + bonus))

            updated = dict(doc)
            updated["score"] = adjusted
            boosted.append(updated)

        boosted.sort(
            key=lambda d: float(d.get("score", 0.0) or 0.0), reverse=True
        )
        return boosted

    # ==================================================================
    # Health
    # ==================================================================

    async def health_check(self) -> Dict[str, Any]:
        """
        Lightweight health check.

        Returns a static "healthy" status — remote dependency pings are
        intentionally skipped here to keep this endpoint fast enough for
        frequent polling. Dependency health is checked at startup and
        reported in application logs.
        """
        return {
            "status": "healthy",
            "service": "Retrieval Service v2",
            "port": 8003,
            "components": {
                "vector_store": {"status": "not_checked"},
                "embeddings": {"status": "not_checked"},
            },
        }