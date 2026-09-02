"""
Service Layer - Retrieval service

High-level service supplying HS-code corpus loading (with in-process +
Redis caching), 6-digit prefix lookup, and lexical candidate scoring used
by the /hs-code-candidates and /hs-code-ranked endpoints.
"""

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RetrievalService:
    """
    High-level retrieval service for HS code classification.

    Responsibilities:
    - Maintain a cached, in-memory scan of the gdce_hs_code Qdrant collection
      (with optional Redis-backed cross-process caching) so 6-digit HS
      prefix lookups don't require a full collection scroll per request.
    - Score HS candidates against a free-text query using simple lexical
      heading/token matching.
    - Report service health.
    """

    def __init__(
        self,
        retrieval_orchestrator,
        config=None,
        gemini_client=None,
        cache_client=None,
    ):
        """
        Args:
            retrieval_orchestrator: RetrievalOrchestrator instance (semantic search)
            config: Configuration object
            gemini_client: Optional Gemini LLM client for answer generation
            cache_client: Optional Redis cache client for HS corpus caching
        """
        self.orchestrator = retrieval_orchestrator
        self.config = config
        self.gemini_client = gemini_client
        self.cache = cache_client
        self._hs_corpus_cache: Dict[str, List[dict]] = {}

    async def prewarm(self) -> None:
        """Pre-warm the HS corpus cache at startup so the first request is fast."""
        collection = getattr(self.config, "qdrant_hs_code_collection", "gdce_hs_code")
        logger.info(f"Pre-warming HS corpus for collection: {collection}")
        corpus = await self._load_hs_corpus_async(collection)
        logger.info(f"Pre-warm complete — {len(corpus)} HS entries cached")

    # ---- HS corpus loading (in-memory + Redis) ----

    @staticmethod
    def _tokenize_text(value: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", (value or "").lower())

    def _load_hs_corpus(self, collection_name: str) -> List[dict]:
        """
        Synchronous full scroll of the HS collection.
        Always call via `_load_hs_corpus_async` from async contexts.
        """
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
        page_size = 1024

        try:
            while True:
                points, offset = client.scroll(
                    collection_name=collection_name,
                    offset=offset,
                    limit=page_size,
                    with_payload=True,
                    with_vectors=False,
                )
                if not points:
                    break

                for point in points:
                    payload = point.payload or {}
                    hs_code = payload.get("hs_code")
                    if not hs_code:
                        continue
                    text = " ".join(
                        str(payload.get(field) or "")
                        for field in ("description", "title", "text", "content", "hs_code")
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
            logger.debug(f"HS corpus scan failed: {exc}")
            corpus = []

        self._hs_corpus_cache[collection_name] = corpus
        logger.info(f"HS corpus loaded: {len(corpus)} entries for '{collection_name}'")
        return corpus

    async def _load_hs_corpus_async(self, collection_name: str) -> List[dict]:
        """
        Async wrapper — checks in-process cache, then Redis, then falls back
        to a full blocking scroll run in a thread pool.
        """
        cached = self._hs_corpus_cache.get(collection_name)
        if cached is not None:
            return cached

        if self.cache:
            redis_key = self.cache.make_key("hs_corpus", collection_name)
            cached_remote = await self.cache.get_json(redis_key)
            if cached_remote is not None:
                # tokens were sets; JSON round-trips them as lists — restore
                for entry in cached_remote:
                    entry["tokens"] = set(entry.get("tokens", []))
                self._hs_corpus_cache[collection_name] = cached_remote
                logger.info(f"HS corpus loaded from Redis: {len(cached_remote)} entries")
                return cached_remote

        import asyncio
        corpus = await asyncio.to_thread(self._load_hs_corpus, collection_name)

        if self.cache and corpus:
            serializable = [{**e, "tokens": list(e["tokens"])} for e in corpus]
            redis_key = self.cache.make_key("hs_corpus", collection_name)
            ttl = getattr(self.config, "redis_corpus_ttl", 21600)
            await self.cache.set_json(redis_key, serializable, ttl=ttl)

        return corpus

    # ---- HS prefix lookup ----

    def fetch_hs_documents_by_prefix(self, prefix: str, collection_name: str, limit: int = 300) -> List[dict]:
        """Fetch HS documents whose HS code starts with the given 6-digit prefix."""
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
                "score": 0.95,
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
        """Non-blocking version of fetch_hs_documents_by_prefix."""
        import asyncio
        await self._load_hs_corpus_async(collection_name)
        return await asyncio.to_thread(
            self.fetch_hs_documents_by_prefix, prefix, collection_name, limit
        )

    # ---- Candidate scoring ----

    @staticmethod
    def _hs_heading(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        digits = re.sub(r"\D", "", str(raw))
        return digits[:4] if len(digits) >= 4 else None

    @staticmethod
    def _score_hs_candidates_by_query(query: str, documents: List[dict], target_heading: str) -> List[dict]:
        """Apply light lexical scoring over candidates to improve subheading precision."""
        q = (query or "").lower()
        stop_words = {
            "what", "is", "the", "hs", "code", "for", "of", "to", "a", "an", "and", "or", "with", "in", "on",
            "applies", "covers", "use", "should", "i", "other", "type",
        }
        query_tokens = [t for t in re.findall(r"[a-z0-9\.\-]+", q) if t not in stop_words and len(t) > 1]

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
            ratio = (overlap / max(1, len(query_tokens)))

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
            if "diesel-electric" in q and "diesel" in text and "electric" in text:
                bonus += 0.25

            base = float(doc.get("score", 0.0) or 0.0)
            adjusted = min(1.0, max(base, 0.15 + (ratio * 0.6) + bonus))

            updated = dict(doc)
            updated["score"] = adjusted
            boosted.append(updated)

        boosted.sort(key=lambda d: float(d.get("score", 0.0) or 0.0), reverse=True)
        return boosted

    # ---- Health ----

    async def health_check(self) -> Dict[str, Any]:
        """Lightweight health check (remote service pings skipped to avoid timeouts)."""
        return {
            "status": "healthy",
            "service": "Retrieval Service v2",
            "port": 8003,
            "components": {
                "vector_store": {"status": "not_checked"},
                "embeddings": {"status": "not_checked"},
            },
        }