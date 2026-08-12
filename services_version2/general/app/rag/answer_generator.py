"""
LLM Answer Generation — General Retrieval Service.

Builds user-friendly final answers from retrieved documents using a
cascading strategy:

1. **Gemini** — primary; generates a natural-language summary grounded in
   the retrieved context. Result is cached in Redis when available.
2. **vLLM** — optional fallback; calls a self-hosted vLLM instance via its
   OpenAI-compatible chat completions API.
3. **Extractive fallback** — returns the top document's first ~320 chars
   verbatim with a prefix.

Answer caching is keyed on ``(query, doc_ids)`` so identical queries
against the same document set skip the LLM call entirely.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from urllib import request as urllib_request

from prompts import render_prompt

logger = logging.getLogger(__name__)


class AnswerGenerator:
    """
    Generate user-friendly answers from retrieval results.

    Implements a cascading strategy: Gemini → vLLM → extractive fallback.
    Results are cached in Redis (keyed on query + doc IDs) when available.

    Parameters
    ----------
    config : GeneralConfig
        Service configuration.
    gemini_client : Optional[GeminiClient]
        Gemini LLM client for primary answer generation.
    cache_client : Optional[CacheClient]
        Redis cache client for answer caching.
    """

    def __init__(self, config, gemini_client=None, cache_client=None):
        self.config = config
        self.gemini_client = gemini_client
        self.cache = cache_client

    async def generate(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        intent: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a final answer using the cascading strategy.

        Flow
        ----
        1. If ``status == "clarification_required"``, return the
           clarification prompt immediately.
        2. If no documents, return the "no results" prompt.
        3. Check Redis cache (keyed on query + first 5 doc IDs).
        4. Try Gemini → if successful, cache the result and return.
        5. Try vLLM → if enabled and successful, return.
        6. Fall back to extractive answer (top doc snippet).

        Returns
        -------
        Dict[str, Any]
            ``{"final_answer": str, "answer_source": str}``
        """
        if status == "clarification_required":
            return {
                "final_answer": render_prompt("clarification_required.txt"),
                "answer_source": "clarification_required",
            }

        if not documents:
            return {
                "final_answer": render_prompt("no_results.txt"),
                "answer_source": "no_results",
            }

        doc_ids = ",".join(str(doc.get("id") or doc.get("doc_id") or "") for doc in documents[:5])
        cache_key = None
        if self.cache and getattr(self.config, "redis_enabled", True):
            cache_key = self.cache.make_key("answer", query.strip().lower(), doc_ids)
            cached = await self.cache.get_json(cache_key)
            if cached:
                logger.info(f"[Answer Generation] Cache hit for query: {query[:60]}...")
                cached["answer_source"] = f"{cached.get('answer_source', '')}_cached"
                return cached

        # Try Gemini first when configured.
        if self.gemini_client and getattr(self.config, "gemini_enabled", True):
            logger.info(f"[Answer Generation] Calling Gemini LLM for final answer. Query: {query[:80]}... | Docs: {len(documents)}")
            try:
                gemini_answer = await self.gemini_client.generate_answer(
                    query=query,
                    documents=documents,
                    intent=intent,
                    status=status,
                )
                logger.info(f"[Answer Generation] Gemini LLM raw response: {repr(gemini_answer)}")
                if gemini_answer:
                    result = {
                        "final_answer": gemini_answer,
                        "answer_source": "gemini_llm",
                    }
                    if self.cache and cache_key and getattr(self.config, "redis_enabled", True):
                        await self.cache.set_json(cache_key, result, ttl=self.config.redis_answer_ttl)
                    return result
                logger.warning("[Answer Generation] Gemini LLM returned empty or None, trying vLLM/fallback")
            except Exception as e:
                logger.warning(f"[Answer Generation] Gemini LLM exception: {e}. Trying fallback.")

        # Fallback to vLLM if available
        if getattr(self.config, "vllm_enabled", False):
            logger.debug("Attempting to generate answer with vLLM...")
            llm_answer = await self._generate_with_vllm(query, documents)
            if llm_answer:
                return {
                    "final_answer": llm_answer,
                    "answer_source": "vllm",
                }

        # Final fallback: extractive answer from documents
        return {
            "final_answer": self._generate_extractive_answer(query, documents),
            "answer_source": "extractive_fallback",
        }

    async def _generate_with_vllm(self, query: str, documents: List[Dict[str, Any]]) -> Optional[str]:
        """Call vLLM OpenAI-compatible endpoint for natural-language answer generation."""
        try:
            context_blocks = []
            for idx, doc in enumerate(documents[:3], start=1):
                content = str(doc.get("content", "")).strip()
                if not content:
                    continue
                context_blocks.append(f"[{idx}] {content[:900]}")

            if not context_blocks:
                return None

            prompt = render_prompt(
                "vllm_user.txt",
                query=query,
                context="\n\n".join(context_blocks),
            )

            payload = {
                "model": self.config.vllm_model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": render_prompt("vllm_system.txt"),
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 240,
            }

            endpoint = f"http://{self.config.vllm_host}:{self.config.vllm_port}/v1/chat/completions"

            def _do_request() -> Optional[str]:
                req = urllib_request.Request(
                    endpoint,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib_request.urlopen(req, timeout=self.config.vllm_timeout) as resp:
                    body = resp.read().decode("utf-8")
                    parsed = json.loads(body)
                    choices = parsed.get("choices") or []
                    if not choices:
                        return None
                    message = choices[0].get("message") or {}
                    content = message.get("content")
                    return content.strip() if content else None

            return await asyncio.to_thread(_do_request)
        except Exception as exc:
            logger.warning(f"vLLM answer generation failed, using fallback: {exc}")
            return None

    def _generate_extractive_answer(self, query: str, documents: List[Dict[str, Any]]) -> str:
        """Simple fallback answer if LLM is unavailable."""
        best = documents[0]
        snippet = str(best.get("content", "")).strip()
        if not snippet:
            return render_prompt("no_results_extractive.txt")

        snippet = snippet.replace("\n", " ").strip()
        if len(snippet) > 320:
            snippet = snippet[:317].rstrip() + "..."

        return render_prompt("extractive_prefix.txt", snippet=snippet)
