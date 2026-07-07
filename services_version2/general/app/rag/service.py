"""
Service Layer - General Retrieval Service
High-level service implementing business rules for general (non-HS) queries.

This is a deliberately slimmed-down sibling of services_version2/retrieval's
RetrievalService: it keeps the trade-period clarification guard and the
lexical-overlap reranking step (both useful for FAQ/definition/policy
documents), but drops every HS-code-specific concern — ambiguity detection,
GIR reasoning, rule-based HS lookups, hs_mode/select/compare — since this
service never touches the gdce_hs_code collection.
"""

import logging
from typing import Optional, Dict, Any, List
import re

from .query import QueryProcessor

logger = logging.getLogger(__name__)


class GeneralRetrievalService:
    """
    High-level retrieval service for general queries (FAQ, definitions,
    policy questions, and other non-HS document lookups).
    """

    def __init__(
        self,
        query_processor: QueryProcessor,
        retrieval_orchestrator,
        config=None,
        gemini_client=None,
        cache_client=None,
    ):
        """
        Initialize general retrieval service.

        Args:
            query_processor: Query processing component
            retrieval_orchestrator: Retrieval orchestrator
            config: Configuration object
            gemini_client: Optional Gemini LLM client for answer generation
        """
        self.query_processor = query_processor
        self.orchestrator = retrieval_orchestrator
        self.config = config
        self.gemini_client = gemini_client
        self.cache_client = cache_client

    async def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        session_id: Optional[str] = None,
        collection: Optional[str] = None,
        require_period_for_trade: bool = True,
    ) -> Dict[str, Any]:
        """
        Main retrieval endpoint business logic for general queries.

        Args:
            query: User query
            top_k: Number of results (uses config default if None)
            session_id: Optional session identifier
            collection: Optional collection name override. Uses config default (gdce_docs) if None.
            require_period_for_trade: Whether to require time period for trade-data-style queries

        Returns:
            Retrieval results
        """
        logger.info(f"General retrieve request: {query[:100]}... (session: {session_id}, collection: {collection})")

        try:
            # Use config defaults if not specified
            if top_k is None:
                top_k = self.config.top_k_default if self.config else 10

            # Validate top_k limits
            top_k = min(
                top_k,
                self.config.top_k_max if self.config else 50
            )

            # Prompt for time period when request looks like trade-data analytics.
            if require_period_for_trade and self._is_trade_data_query(query) and not self._has_time_period(query):
                return {
                    "query": query,
                    "documents": [],
                    "status": "clarification_required",
                    "session_id": session_id,
                    "missing_parameters": ["period"],
                    "clarification": "Please provide a time period (month, quarter, or year) for trade data queries.",
                    "api_visibility": {
                        "api_called": "/retrieval/retrieve",
                        "collection_used": collection or (self.orchestrator.vector_store.collection_name if self.orchestrator and self.orchestrator.vector_store else "gdce_docs"),
                        "processing_path": "period_guard",
                    },
                }

            # Process query
            processed = self.query_processor.process(query)
            if not processed:
                return {
                    "query": query,
                    "documents": [],
                    "error": "Query processing failed",
                    "status": "invalid_query",
                    "api_visibility": {
                        "api_called": "/retrieval/retrieve",
                        "collection_used": collection or "gdce_docs",
                        "processing_path": "query_validation",
                    },
                }

            # Retrieve documents with optional collection override.
            result = await self.orchestrator.retrieve(
                processed,
                top_k=top_k,
                use_semantic=True,
                use_structured=True,
                collection_name=collection,
            )

            collection_used = collection or (self.orchestrator.vector_store.collection_name if self.orchestrator and self.orchestrator.vector_store else "gdce_docs")

            # Apply lexical reranking to keep exact FAQ/definition/policy matches on top.
            reranked_docs = self._rerank_general_documents_by_query(query=query, documents=result.get("documents", []))
            result["documents"] = reranked_docs[:top_k]
            result["total_count"] = len(result.get("documents", []))

            # Add metadata
            result["status"] = result.get("status", "success")
            result["session_id"] = session_id
            result["language"] = processed.language
            result["api_visibility"] = {
                "api_called": "/retrieval/retrieve",
                "collection_used": collection_used,
                "processing_path": "semantic+structured",
            }
            result["keywords"] = processed.tokens

            logger.info(
                f"Retrieved {len(result.get('documents', []))} documents "
                f"for query: {query[:50]}... from collection: {collection or 'default'}"
            )

            return result

        except Exception as e:
            logger.error(f"Retrieval error: {e}")
            return {
                "query": query,
                "documents": [],
                "error": str(e),
                "status": "error",
                "session_id": session_id,
                "api_visibility": {
                    "api_called": "/retrieval/retrieve",
                    "collection_used": collection or "gdce_docs",
                    "processing_path": "exception",
                },
            }

    @staticmethod
    def _is_trade_data_query(query: str) -> bool:
        q = (query or "").lower()
        flow_terms = ["trade", "import", "export"]
        analytics_terms = ["statistics", "trend", "volume", "value", "data", "compare", "comparison"]
        has_flow = any(term in q for term in flow_terms)
        has_analytics = any(term in q for term in analytics_terms)
        # Require both dimensions to avoid false positives for procedural import questions.
        return has_flow and has_analytics

    @staticmethod
    def _has_time_period(query: str) -> bool:
        q = (query or "").lower()
        patterns = [
            r"\b(19|20)\d{2}\b",
            r"\bq[1-4]\b",
            r"\bquarter\s+[1-4]\b",
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
            r"\b(last|this|next)\s+(month|quarter|year)\b",
            r"\b\d{4}\s*[-/]\s*\d{1,2}\b",
        ]
        return any(re.search(pattern, q) for pattern in patterns)

    @staticmethod
    def _doc_text_blob(doc: dict) -> str:
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        parts = [
            str(doc.get("title") or ""),
            str(doc.get("description") or ""),
            str(doc.get("content") or ""),
            str(doc.get("text") or ""),
            str(metadata.get("title") or ""),
            str(metadata.get("description") or ""),
            str(metadata.get("section") or ""),
            str(metadata.get("heading") or ""),
            str(metadata.get("doc_id") or ""),
            str(metadata.get("filename") or ""),
        ]
        return " ".join(parts).lower()

    @staticmethod
    def _query_keywords(query: str) -> list:
        tokens = re.findall(r"[a-z0-9]+", (query or "").lower())
        stop_words = {
            "what", "is", "the", "how", "to", "a", "an", "for", "of", "in", "on", "and", "or", "with", "against",
            "i", "we", "you", "my", "our", "please", "can", "could", "should", "would", "do", "does", "did",
        }
        return [t for t in tokens if t not in stop_words and len(t) > 1]

    @staticmethod
    def _normalize_phrase(text: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _is_metadata_heavy_chunk(doc: dict, text_blob: str) -> bool:
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        chunk_idx = doc.get("chunk_idx", metadata.get("chunk_idx"))
        text = (text_blob or "").strip().lower()
        return bool(
            (chunk_idx == 0 and "doc_id" in text and "title" in text and "effective_date" in text)
            or text.startswith("--- doc_id:")
            or text.startswith("doc_id:")
        )

    def _rerank_general_documents_by_query(self, query: str, documents: list) -> list:
        if not documents:
            return []

        q = (query or "").strip().lower()
        keywords = self._query_keywords(query)
        query_phrase = " ".join(keywords)
        normalized_query = self._normalize_phrase(query)

        ranked: list = []
        for doc in documents:
            text = self._doc_text_blob(doc)
            if not text:
                ranked.append(dict(doc))
                continue

            base = float(doc.get("score", 0.0) or 0.0)
            overlap = sum(1 for k in keywords if k in text)
            overlap_ratio = overlap / max(1, len(keywords))

            # Strong boost when the cleaned phrase appears directly in the document/FAQ heading.
            exact_phrase_boost = 0.0
            if query_phrase and query_phrase in text:
                exact_phrase_boost += 0.45

            # Very strong boost for exact FAQ-style question heading match.
            normalized_text = self._normalize_phrase(text)
            exact_question_boost = 0.0
            if normalized_query and normalized_query in normalized_text:
                exact_question_boost += 0.40

            # Special boost for complaint/confiscation-like dispute questions.
            dispute_boost = 0.0
            if "complaint" in q and "complaint" in text:
                dispute_boost += 0.18
            if "confiscation" in q and "confiscation" in text:
                dispute_boost += 0.22

            # Penalize frontmatter/metadata chunks that frequently pollute top results.
            metadata_penalty = 0.0
            if self._is_metadata_heavy_chunk(doc, text):
                metadata_penalty = 0.30

            adjusted = base + (overlap_ratio * 0.35) + exact_phrase_boost + exact_question_boost + dispute_boost - metadata_penalty
            adjusted = max(0.0, min(1.0, adjusted))

            updated = dict(doc)
            updated["score"] = adjusted
            ranked.append(updated)

        ranked.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
        return ranked

    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of all components.

        Returns:
            Health status
        """
        status = {
            "status": "healthy",
            "service": "General Retrieval Service",
            "port": 8005,
            "components": {
                "vector_store": {"status": "not_checked"},
                "embeddings": {"status": "not_checked"},
                "repository": {"status": "not_checked"}
            }
        }

        return status
