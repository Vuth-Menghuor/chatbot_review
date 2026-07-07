"""
Gemini LLM Client for General Retrieval Service.
Uses Google Generative AI API to generate final answers from retrieval context.

This is a trimmed-down version of the HS-code retrieval service's Gemini
client: it only needs the generic context-grounded answer prompt, since
this service never handles HS_LOOKUP / EXTRACT_SPECS / HS code candidate
explanation flows.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any

from google import genai

from prompts import render_prompt

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for interacting with Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite"):
        self.api_key = (api_key or "").strip()
        self.model_name = model
        self.client = None

        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    async def generate_answer(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        intent: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a grounded answer from retrieval documents."""
        if not self.client:
            return None

        context_blocks = []
        for idx, doc in enumerate(documents[:15], start=1):
            content = str(doc.get("content", "")).strip()
            if not content:
                continue
            context_blocks.append(f"[Document {idx}]\n{content[:600]}")

        context_section = render_prompt(
            "context_documents.txt",
            context="\n\n".join(context_blocks),
        ) if context_blocks else render_prompt("context_documents_empty.txt")

        prompt = render_prompt(
            "gemini_user.txt",
            query=query,
            context_section=context_section,
        )

        def _extract_text(response) -> Optional[str]:
            try:
                if hasattr(response, "text") and getattr(response, "text"):
                    return getattr(response, "text").strip()
            except Exception:
                pass
            try:
                if hasattr(response, "candidates"):
                    candidates = getattr(response, "candidates") or []
                    for c in candidates:
                        if isinstance(c, dict):
                            for key in ("content", "text", "message"):
                                if c.get(key):
                                    return str(c.get(key)).strip()
                        else:
                            for key in ("content", "text"):
                                val = getattr(c, key, None)
                                if val:
                                    return str(val).strip()
            except Exception:
                pass
            try:
                for key in ("output", "results", "response"):
                    val = getattr(response, key, None)
                    if val:
                        s = repr(val)
                        if s:
                            return s[:4096]
            except Exception:
                pass
            return None

        def _do_generate() -> Optional[str]:
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=render_prompt("gemini_system.txt") + "\n\n" + prompt,
                )
            except Exception as exc:
                logger.warning(f"Gemini answer generation failed: {exc}")
                return None

            text = _extract_text(response)
            if text:
                return text

            logger.warning(f"Gemini returned no text parts. Raw response: {repr(response)[:2000]}")

            # Retry once with reduced context to handle size/safety issues.
            try:
                small_context = []
                for idx, doc in enumerate(documents[:5], start=1):
                    content = str(doc.get("content", "")).strip()
                    if content:
                        small_context.append(f"[{idx}] {content[:300]}")

                retry_section = render_prompt(
                    "context_documents.txt",
                    context="\n\n".join(small_context),
                ) if small_context else render_prompt("context_documents_empty.txt")
                retry_prompt = render_prompt(
                    "gemini_retry_user.txt",
                    query=query,
                    retry_section=retry_section,
                )
                response2 = self.client.models.generate_content(
                    model=self.model_name,
                    contents=render_prompt("gemini_retry_system.txt") + "\n\n" + retry_prompt,
                )
                text2 = _extract_text(response2)
                if text2:
                    return text2
                logger.warning(f"Gemini retry returned no text. Raw retry response: {repr(response2)[:2000]}")
            except Exception as exc:
                logger.warning(f"Gemini retry failed: {exc}")

            return None

        return await asyncio.to_thread(_do_generate)
