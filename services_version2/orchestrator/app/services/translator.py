import re
import os
import httpx
import logging
from typing import Optional
from ..ai import OrchestratorLLMService

from prompts.dynamic_prompt_manager import DynamicPromptManager

# Module-level prompt manager — loads from prompts/ directory on import
_prompt_manager = DynamicPromptManager()

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

    def _parse_translation_tags(self, text: str) -> str:
        """Helper to extract translated content from XML tags if present, otherwise returns stripped text."""
        if not text:
            return ""
        stripped = text.strip()
        if "<translation>" in stripped:
            match = re.search(r"<translation>(.*?)</translation>", stripped, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
            # If tags are present but unbalanced or broken
            stripped = re.sub(r"<\/?translation>", "", stripped, flags=re.IGNORECASE).strip()
        return stripped

    async def translate_to_english(self, query: str) -> str:
        """Translates the Khmer query to standard English. Uses OpenRouter if key is present, falls back to LLM service."""
        if not query or not query.strip():
            return query

        prompt = _prompt_manager.render("shared_translate_to_english", text=query)

        result = None
        if self.openrouter_api_key:
            try:
                result = await self._translate_via_openrouter(prompt)
            except Exception as e:
                logger.warning(f"OpenRouter translation to English failed, falling back to standard LLM service: {e}")

        if not result:
            # Fallback
            try:
                result = await self.llm_service.translate_to_english(query)
            except Exception as e:
                logger.error(f"Translation to English failed completely (all LLMs down): {e}")
                return query

        return self._parse_translation_tags(result)

    def _contains_thai(self, text: str) -> bool:
        """Checks if the text contains any characters in the Thai Unicode block (U+0E00-U+0E7F)."""
        if not text:
            return False
        return bool(re.search(r"[\u0e00-\u0e7f]", text))

    async def translate_to_khmer(self, text: str) -> str:
        """Translates the English answer back to Khmer. Uses OpenRouter if key is present, falls back to LLM service."""
        if not text or not text.strip():
            return text

        prompt = _prompt_manager.render("shared_translate_to_khmer", text=text)

        result = None
        if self.openrouter_api_key:
            try:
                result = await self._translate_via_openrouter(prompt)
            except Exception as e:
                logger.warning(f"OpenRouter translation to Khmer failed, falling back to standard LLM service: {e}")

        if not result:
            # Fallback
            try:
                result = await self.llm_service.translate_to_khmer(text)
            except Exception as e:
                logger.error(f"Translation to Khmer failed completely (all LLMs down): {e}")
                return text

        cleaned = self._parse_translation_tags(result)

        # Check for Thai characters script leakage
        if self._contains_thai(cleaned):
            logger.warning(
                f"Thai character leakage detected in Khmer translation. Triggering auto-retry. "
                f"Leaked text snippet: {cleaned[:100]}"
            )
            # Re-prompt with a correction note
            correction_note = _prompt_manager.render("shared_translate_to_khmer_correction")
            prompt_with_correction = f"{prompt}\n\n{correction_note}"
            try:
                retry_result = None
                if self.openrouter_api_key:
                    retry_result = await self._translate_via_openrouter(prompt_with_correction)
                else:
                    provider = self.llm_service.router.providers.get("gemini")
                    if provider and provider.is_available():
                        import asyncio
                        response = await asyncio.to_thread(
                            provider.client.models.generate_content,
                            model=provider.model_name,
                            contents=prompt_with_correction,
                        )
                        retry_result = (response.text or "").strip()
                
                if retry_result:
                    cleaned_retry = self._parse_translation_tags(retry_result)
                    if not self._contains_thai(cleaned_retry):
                        logger.info("Auto-retry translation successfully resolved Thai script leakage.")
                        return cleaned_retry
                    else:
                        logger.error("Auto-retry translation still contained Thai script leakage. Falling back to the cleaned result.")
            except Exception as retry_err:
                logger.error(f"Translation retry failed: {retry_err}")

        return cleaned

