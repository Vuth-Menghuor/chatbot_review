"""
Gemini LLM Client for Retrieval Service.
Uses Google Generative AI API to generate HS-code prefix extractions and
ranked-candidate answers.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from prompts import render_prompt

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for interacting with the Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash"):
        self.api_key = (api_key or "").strip()
        self.model_name = model
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    async def generate_answer(
        self,
        query: str,
        documents: Optional[List[Dict[str, Any]]] = None,
        intent: Optional[str] = None,
        prompt_override: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate a Gemini response.

        - If `prompt_override` is given, it is used verbatim as the prompt.
        - Else if intent == "EXTRACT_SPECS", `query` is treated as the raw
          product description and wrapped in the HS-prefix extraction template.
        - Otherwise `query` is sent to Gemini as-is.
        """
        if not self.client:
            return None

        if prompt_override:
            prompt = prompt_override
        elif (intent or "").upper() == "EXTRACT_SPECS":
            prompt = render_prompt("gemini_extract_specs.txt", query=query)
        else:
            prompt = query

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
            return None

        def _do_generate(p: str) -> Optional[str]:
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=p,
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(thinking_level="low")
                    ),
                )
            except Exception as exc:
                logger.warning(f"Gemini answer generation failed: {exc}")
                return None

            text = _extract_text(response)
            if text:
                return text

            logger.warning(f"Gemini returned no text parts. Raw response: {repr(response)[:2000]}")

            # Retry once with the same prompt in case of a transient empty response.
            try:
                response2 = self.client.models.generate_content(
                    model=self.model_name,
                    contents=p,
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(thinking_level="low")
                    ),
                )
                text2 = _extract_text(response2)
                if text2:
                    return text2
                logger.warning(f"Gemini retry returned no text. Raw retry response: {repr(response2)[:2000]}")
            except Exception as exc:
                logger.warning(f"Gemini retry failed: {exc}")

            return None

        return await asyncio.to_thread(_do_generate, prompt)