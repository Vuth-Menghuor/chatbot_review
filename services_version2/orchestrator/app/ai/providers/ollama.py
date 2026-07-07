"""Ollama provider adapter for intent, rewrite, and summarization tasks."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .base import BaseLLMProvider, BaseFormatterProvider
from ..core.models import FormatterIntent, HSCodeInfo
from ...core.config import FormatterServiceConfig

logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    name = "ollama"

    def __init__(self, host: str, model: str, timeout: int = 30):
        from ..shims.rewriter_service import get_rewriter_service, RewriterServiceConfig
        from ..shims.intent_service import get_intent_service, IntentServiceConfig

        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

        intent_config = IntentServiceConfig(llm_host=self.host, llm_model=model, timeout=timeout)
        self.intent_detector = get_intent_service(intent_config)

        rewriter_config = RewriterServiceConfig(
            rewrite_provider="gemini",
        )
        self._rewriter_service = get_rewriter_service(rewriter_config)

        from prompts.dynamic_prompt_manager import DynamicPromptManager
        self.prompt_manager = DynamicPromptManager()

    def is_available(self) -> bool:
        return True

    def classify_intent(self, question: str) -> Tuple[Any, float, str]:
        # To avoid recursion when LLMFirstLayerService delegates to llm_service
        # which routes to OllamaProvider which delegates back to LLMFirstLayerService:
        # We can check if intent_detector is an instance of LLMFirstLayerService.
        # If it is, we fall back to keyword matching directly to prevent recursion.
        from ..analyzer import LLMFirstLayerService
        if isinstance(self.intent_detector, LLMFirstLayerService):
            from ...services.workflow import WorkflowExecutor
            executor = WorkflowExecutor(use_llm_intent=False)
            intent, confidence = executor.detect_intent_with_confidence(question)
            return self._map_intent(intent), confidence, "Ollama fallback to keyword"

        intent, confidence, reasoning = self.intent_detector.detect_intent(question)
        return self._map_intent(intent), confidence, reasoning

    def detect_currency(self, question: str) -> Tuple[Optional[str], float, str]:
        """Detect currency from user query using Intent Service."""
        return self.intent_detector.detect_currency(question)

    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        return await self._rewriter_service.rewrite_input(
            user_input,
            context=context,
            intent_hint=intent_hint,
        )

    async def summarize_text(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        prompt = self.prompt_manager.render("shared_summarize_text", text=text)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False, "temperature": 0.2},
                )
                response.raise_for_status()
                payload = response.json()
                return payload.get("response", "").strip() or text
        except Exception as e:
            logger.warning(f"Ollama summarization failed: {e}")
            return text

    async def select_best_hs_code(self, query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not candidates:
            return {
                "selected_code": None, 
                "confidence": 0.0, 
                "reason": "No candidates", 
                "index": -1,
                "top_3_candidates": []
            }
        best = max(candidates, key=lambda item: item.get("score", 0))
        return {
            "selected_code": best.get("hs_code"),
            "confidence": best.get("score", 0.0),
            "reason": "Ollama fallback selected by score ranking",
            "index": candidates.index(best),
            "top_3_candidates": candidates[:3]  # ← Return top 3 by score
        }

    async def rewrite_descriptions_batch(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return candidates

    def get_or_create_session(self, session_id: str):
        return self._rewriter_service.get_or_create_session(session_id)

    def update_session_context(self, session_id: str, **kwargs: Any) -> None:
        self._rewriter_service.update_session_context(session_id, **kwargs)

    @staticmethod
    def _map_intent(intent: Any) -> str:
        value = getattr(intent, "value", intent)
        return str(value)

    async def translate_to_english(self, text: str) -> str:
        prompt = self.prompt_manager.render("shared_translate_to_english", text=text)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False, "temperature": 0.1},
                )
                response.raise_for_status()
                payload = response.json()
                return payload.get("response", "").strip() or text
        except Exception as e:
            logger.warning(f"Ollama translation to English failed: {e}")
            return text

    async def translate_to_khmer(self, text: str) -> str:
        prompt = self.prompt_manager.render("shared_translate_to_khmer", text=text)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False, "temperature": 0.1},
                )
                response.raise_for_status()
                payload = response.json()
                return payload.get("response", "").strip() or text
        except Exception as e:
            logger.warning(f"Ollama translation to Khmer failed: {e}")
            return text


class OllamaFormatterProvider(BaseFormatterProvider):
    """Format service responses using local LLM."""
    
    def __init__(self, config: FormatterServiceConfig):
        self.config = config
        self.llm_url = config.ollama_host if config.ollama_host.startswith("http") else f"http://{config.ollama_host}:{config.ollama_port}"
        self.model = config.ollama_model
        
        from prompts.dynamic_prompt_manager import DynamicPromptManager
        self.prompt_manager = DynamicPromptManager()
        
    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        return self.config.enabled

    async def format_response(
        self,
        response_text: str,
        intent: FormatterIntent,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self.config.enabled:
            logger.debug("LLM formatting disabled - returning raw response")
            return response_text

        try:
            if intent == FormatterIntent.CALCULATION:
                return await self._format_calculation(response_text, original_question, context)
            elif intent in (FormatterIntent.RETRIEVAL, FormatterIntent.HS_CODE_LOOKUP):
                return await self._format_retrieval(response_text, original_question)
            elif intent == FormatterIntent.TRADE_QUERY:
                return await self._format_trade_query(response_text, original_question)
            elif intent == FormatterIntent.GENERAL:
                if any(kw in original_question.lower() for kw in ["define", "definition", "what is", "meaning", "explain"]):
                    return await self._format_definition(response_text, original_question)
                return await self._format_generic(response_text, original_question)
            else:
                return await self._format_generic(response_text, original_question)
        except Exception as e:
            logger.warning(f"LLM formatting failed: {e}. Returning raw response.")
            return response_text

    async def _format_calculation(
        self,
        response_text: str,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        context = context or {}
        hs_code_info = context.get('hs_code_info')
        
        # If no HS code info, return the beautifully formatted text from calculation_formatter.py
        if not hs_code_info:
            return response_text
            
        description = hs_code_info.get('description', 'N/A')
        if not description or description == 'N/A':
            return response_text
            
        # Format HS code description using LLM for better clarity
        try:
            llm_description = await self._format_hs_description(description)
        except Exception as e:
            logger.warning(f"Failed to enhance HS description: {e}")
            return response_text
            
        if not llm_description or llm_description == description:
            return response_text
            
        # Inject the LLM explanation into the PRODUCT INFORMATION block
        # Look for "PRODUCT INFORMATION:\n"
        parts = response_text.split("PRODUCT INFORMATION:\n")
        if len(parts) == 2:
            # Find the end of the PRODUCT INFORMATION block (usually marked by a blank line before INPUT PARAMETERS)
            end_of_block = parts[1].find("\n\n")
            if end_of_block != -1:
                # Format the LLM description with indentation so it looks nice in the block
                formatted_desc = "\n".join([f"  {line}" for line in llm_description.split("\n")])
                injected_block = f"{parts[1][:end_of_block]}\n* LLM Classification Explanation:\n{formatted_desc}{parts[1][end_of_block:]}"
                return f"{parts[0]}PRODUCT INFORMATION:\n{injected_block}"
        
        # If we couldn't parse the block structure, just return the original
        return response_text

    async def _format_retrieval(self, response_text: str, original_question: str) -> str:
        llm_prompt = self.prompt_manager.render(
            "ollama_format_retrieval",
            original_question=original_question,
            response_text=response_text
        )
        try:
            return await self._call_llm(llm_prompt)
        except:
            return response_text

    async def _format_trade_query(self, response_text: str, original_question: str) -> str:
        llm_prompt = self.prompt_manager.render(
            "ollama_format_trade_query",
            original_question=original_question,
            response_text=response_text
        )
        try:
            return await self._call_llm(llm_prompt)
        except:
            return response_text

    async def _format_policy(self, response_text: str, original_question: str) -> str:
        return response_text

    async def _format_hs_description(self, raw_description: str) -> str:
        """Format HS code description using LLM for clarity and explanation."""
        if not raw_description or len(raw_description.strip()) < 5:
            return raw_description
        
        formatting_prompt = self.prompt_manager.render(
            "ollama_format_hs_description",
            raw_description=raw_description
        )

        try:
            formatted_description = await self._call_llm(formatting_prompt)
            return formatted_description.strip()
        except Exception as e:
            logger.warning(f"Failed to format HS description: {e}. Returning original.")
            return raw_description

    async def _format_definition(self, response_text: str, original_question: str) -> str:
        """Extend and enhance definition responses using LLM for comprehensive understanding."""
        if not response_text or len(response_text.strip()) < 10:
            return response_text
        
        extension_prompt = self.prompt_manager.render(
            "ollama_format_definition",
            original_question=original_question,
            response_text=response_text
        )

        try:
            extended_definition = await self._call_llm(extension_prompt)
            return extended_definition.strip()
        except Exception as e:
            logger.warning(f"Failed to extend definition: {e}. Returning original.")
            return response_text

    async def _format_generic(self, response_text: str, original_question: str) -> str:
        return response_text

    def _build_dynamic_footer(
        self,
        original_question: str,
        context: Dict[str, Any],
        total_amount: str,
        hs_code: str,
        origin: str
    ) -> str:
        """Build a dynamic footer with summary, assumptions, and data sources."""
        import os
        from datetime import datetime
        
        cif_value = context.get('cif_value', 'N/A')
        cif_currency = context.get('cif_currency', 'USD')
        exchange_rate = context.get('exchange_rate', 4022)
        rates = context.get('rates', {})
        exchange_rate_date = context.get('exchange_rate_date', datetime.now().strftime('%Y-%m-%d'))
        
        # Determine tax type based on question (import vs export)
        tax_type_label = "import taxes" if "import" in original_question.lower() else "export taxes"
        
        # Build assumptions dynamically
        assumptions = f"""  + DV total: {cif_value:,} {cif_currency} (provided CIF value)
  + Exchange rate as of {exchange_rate_date}: 1 {cif_currency} = {exchange_rate:,.1f} KHR
  + HS Code confirmed from Qdrant database"""
        
        # Add dynamic rate information
        if rates.get('cd_rate'):
            assumptions += f"\n  + Customs Duty (CD) rate: {rates.get('cd_rate', 0):.2f}% - Applied per current regulations"
        if rates.get('st_rate'):
            assumptions += f"\n  + Special Tariff (ST) rate: {rates.get('st_rate', 0):.2f}% - Applied per current regulations"
        if rates.get('vat_rate'):
            vat_rate = rates.get('vat_rate', 0.10) * 100 if rates.get('vat_rate') < 1 else rates.get('vat_rate', 0)
            assumptions += f"\n  + VAT rate: {vat_rate:.2f}% - Applied per current regulations"
        if rates.get('et_rate'):
            assumptions += f"\n  + Export Tax rate: {rates.get('et_rate', 0):.2f}% - Applied per current regulations"
        
        assumptions += f"""\n  + Calculation assumes standard regime (unless specified otherwise)
  + All rates current as of {exchange_rate_date}"""
        
        # Dynamic data sources from environment variables
        qdrant_host = os.getenv("QDRANT_HOST", "172.25.3.243")
        qdrant_port = os.getenv("QDRANT_PORT", "6333")
        pg_host = os.getenv("POSTGRES_HOST") or os.getenv("PG_HOST", "172.25.3.243")
        pg_db = os.getenv("POSTGRES_DB", "gdce_rates")
        
        footer = f"""{'-' * 65}
SUMMARY:
To import {cif_value} {cif_currency} CIF from {origin}, HS Code {hs_code},
you must pay {total_amount} KHR in {tax_type_label}.

ASSUMPTIONS & NOTES:
{assumptions}

DATA SOURCES:
* HS Code Database: Qdrant ({qdrant_host}:{qdrant_port}/collections/gdce_hs_code)
* Exchange Rates: PostgreSQL ({pg_host}/{pg_db})
* Duty Rates: Qdrant ({qdrant_host}:{qdrant_port}/collections/gdce_hs_code)
{'-' * 65}
"""
        return footer

    async def _call_llm(self, prompt: str) -> str:
        # Try OpenAI-compatible chat completions endpoint first (widely supported by generic Local LLMs)
        try:
            openai_url = f"{self.llm_url}/chat/completions"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
            }
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(openai_url, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"].strip()
                else:
                    logger.debug(f"OpenAI endpoint returned {response.status_code}, falling back to Ollama api/generate")
        except Exception as e:
            logger.debug(f"OpenAI endpoint failed: {e}, falling back to Ollama api/generate")

        # Fallback to native Ollama api/generate
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.post(
                    f"{self.llm_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "temperature": 0.3,
                    }
                )
                response.raise_for_status()
                result = response.json()
                return result.get("response", "").strip()
        except Exception as e:
            logger.warning(f"LLM API call failed: {e}")
            raise


