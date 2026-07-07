import re
import os
import httpx
import logging
from typing import Optional
from ..ai import OrchestratorLLMService

logger = logging.getLogger(__name__)

class QueryTranslator:
    """Helper module to handle detection and bidirectional translation using the OpenRouter API / existing LLM service."""

    def __init__(self, llm_service: OrchestratorLLMService):
        self.llm_service = llm_service
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

    @staticmethod
    def is_khmer(text: str) -> bool:
        """Uses regex range check to detect Khmer Unicode characters."""
        if not text:
            return False
        # Khmer Unicode range: U+1780 to U+17FF and U+19E0 to U+19FF
        return bool(re.search(r"[\u1780-\u17FF\u19E0-\u19FF]", text))

    async def _translate_via_openrouter(self, prompt: str) -> str:
        """Helper to send request to OpenRouter API."""
        if not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is not set")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "google/gemini-3.1-flash-lite",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            translated = data["choices"][0]["message"]["content"]
            return translated.strip()

    async def translate_to_english(self, query: str) -> str:
        """Translates the Khmer query to standard English. Uses OpenRouter if key is present, falls back to LLM service."""
        if not query or not query.strip():
            return query

        prompt = (
            "You are a professional translator for Cambodia Customs and Trade.\n"
            "Translate the following Khmer query to clear, standard English.\n"
            "Guidelines:\n"
            "- Preserve any customs/tariff technical jargon, abbreviations, or numbers exactly.\n"
            "- Do not add explanations or conversational filler. Return ONLY the translated query.\n\n"
            f"Query: {query}"
        )

        if self.openrouter_api_key:
            try:
                result = await self._translate_via_openrouter(prompt)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"OpenRouter translation to English failed, falling back to standard LLM service: {e}")

        # Fallback
        try:
            return await self.llm_service.translate_to_english(query)
        except Exception as e:
            logger.error(f"Translation to English failed completely (all LLMs down): {e}")
            return query

    async def translate_to_khmer(self, text: str) -> str:
        """Translates the English answer back to Khmer. Uses OpenRouter if key is present, falls back to LLM service."""
        if not text or not text.strip():
            return text

        prompt = (
            "You are a professional translator for Cambodia Customs and Trade.\n"
            "Translate the following English text/response to natural, polite Khmer.\n"
            "Guidelines:\n"
            "- Preserve all markdown structures, tables, bullet points, list items, and spacing exactly.\n"
            "- Retain technical abbreviations or reference numbers in English if they don't have standard Khmer translations.\n"
            "- Do not add explanations or conversational filler. Return ONLY the translated text.\n\n"
            f"Text:\n{text}"
        )

        if self.openrouter_api_key:
            try:
                result = await self._translate_via_openrouter(prompt)
                if result:
                    return result
            except Exception as e:
                logger.warning(f"OpenRouter translation to Khmer failed, falling back to standard LLM service: {e}")

        # Fallback
        try:
            return await self.llm_service.translate_to_khmer(text)
        except Exception as e:
            logger.error(f"Translation to Khmer failed completely (all LLMs down): {e}")
            return text

