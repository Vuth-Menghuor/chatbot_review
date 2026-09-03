"""
Gemini LLM Client — Retrieval Service.

Wraps the Google Generative AI (Gemini) SDK for two distinct tasks:

1. **HS prefix extraction** — given a free-text product description, return
   a single 6-digit HS code prefix (or empty string if uncertain).
2. **Ranked answer generation** — given a list of HS code candidates,
   produce a structured JSON response with ranked codes, a natural-language
   summary, and (for generic queries) clarifying questions.

Design Notes
------------
- All Gemini calls run via ``asyncio.to_thread`` because the SDK is
  synchronous.
- A single automatic retry is performed for transient empty responses.
- The ``prompt_override`` parameter allows callers to bypass the default
  prompt templates for maximum flexibility.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

from prompts import render_prompt

logger = logging.getLogger(__name__)


class GeminiClient:
    """
    Async-compatible client for the Gemini generative AI API.

    Parameters
    ----------
    api_key : str
        Google AI Studio API key. If empty, the client is a no-op.
    model : str
        Gemini model identifier (e.g. ``"gemini-3.5-flash"``).
    """

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
        Generate a response from Gemini.

        Parameters
        ----------
        query : str
            The user query or prompt content (behaviour depends on other params).
        documents : Optional[List[Dict]]
            Candidate documents for context (currently informational).
        intent : Optional[str]
            - ``"EXTRACT_SPECS"`` — wraps ``query`` in the HS prefix extraction
              template (``gemini_extract_specs.txt``).
            - Anything else — sends ``query`` as-is.
        prompt_override : Optional[str]
            If provided, used verbatim as the prompt, ignoring ``intent``.

        Returns
        -------
        Optional[str]
            The raw text response from Gemini, or ``None`` on any failure
            (including empty responses after retry).
        """
        if not self.client:
            return None

        # --- Prompt resolution --------------------------------------------
        if prompt_override:
            prompt = prompt_override
        elif (intent or "").upper() == "EXTRACT_SPECS":
            prompt = render_prompt("gemini_extract_specs.txt", query=query)
        else:
            prompt = query

        # --- Response text extraction -------------------------------------
        # The Gemini SDK response object can vary; we try multiple access
        # patterns to be resilient across SDK versions.

        def _extract_text(response) -> Optional[str]:
            """Pull text content from a Gemini response object."""
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
            """
            Synchronous Gemini API call. Runs in a thread pool via
            ``asyncio.to_thread`` so it never blocks the event loop.
            """
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=p,
                    config=types.GenerateContentConfig(
                        thinking_config=types.ThinkingConfig(thinking_level="low")
                    ),
                )
            except Exception as exc:
                logger.warning("Gemini answer generation failed: %s", exc)
                return None

            text = _extract_text(response)
            if text:
                return text

            logger.warning(
                "Gemini returned no text parts. Raw response: %s",
                repr(response)[:2000],
            )

            # One automatic retry for transient empty responses.
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
                logger.warning(
                    "Gemini retry returned no text. Raw retry response: %s",
                    repr(response2)[:2000],
                )
            except Exception as exc:
                logger.warning("Gemini retry failed: %s", exc)

            return None

        # Offload the synchronous SDK call to a thread.
        return await asyncio.to_thread(_do_generate, prompt)