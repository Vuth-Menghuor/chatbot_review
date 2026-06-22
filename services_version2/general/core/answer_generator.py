"""
LLM answer generation for General Retrieval Service.
Builds a user-friendly final answer from retrieved documents.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from urllib import request as urllib_request

logger = logging.getLogger(__name__)


class AnswerGenerator:
    """Generate user-friendly answers from retrieval results."""

    def __init__(self, config, gemini_client=None):
        self.config = config
        self.gemini_client = gemini_client

    async def generate(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        intent: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a final answer from retrieved documents.

        Returns a dictionary with keys:
        - final_answer: str
        - answer_source: str (gemini_llm|vllm|extractive_fallback|no_results)
        """
        if status == "clarification_required":
            return {
                "final_answer": (
                    "I need one more detail before giving a final answer. "
                    "Please follow the clarification request."
                ),
                "answer_source": "clarification_required",
            }

        if not documents:
            return {
                "final_answer": (
                    "I could not find relevant information for your question. "
                    "Please try rephrasing it with more detail."
                ),
                "answer_source": "no_results",
            }

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
                    return {
                        "final_answer": gemini_answer,
                        "answer_source": "gemini_llm",
                    }
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

            prompt = (
                "Answer the user's customs/trade question using only the provided context. "
                "Use a clear, friendly tone for non-technical users. "
                "If the answer is not in context, say that clearly and suggest rephrasing.\n\n"
                f"User question: {query}\n\n"
                "Context:\n"
                + "\n\n".join(context_blocks)
            )

            payload = {
                "model": self.config.vllm_model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a GDCE customs assistant. "
                            "Provide concise and user-friendly answers based only on provided context."
                        ),
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
            return (
                "I found related documents, but I could not extract a clear summary. "
                "Please try a more specific question."
            )

        snippet = snippet.replace("\n", " ").strip()
        if len(snippet) > 320:
            snippet = snippet[:317].rstrip() + "..."

        return f"Here is what I found: {snippet}"
