"""Gemini provider adapter for HS selection and summarization tasks."""

import asyncio
#for parse LLM JSON responses
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseLLMProvider, BaseFormatterProvider
from ..core.models import FormatterIntent
from ...core.config import FormatterServiceConfig

logger = logging.getLogger(__name__)


def _log_gemini_usage(model_name: str, response: Any):
    """Helper function to log Gemini token usage dynamically via ContextVars."""
    try:
        if response and hasattr(response, 'usage_metadata') and response.usage_metadata:
            meta = response.usage_metadata
            prompt_tokens = meta.prompt_token_count
            completion_tokens = meta.candidates_token_count
            total_tokens = meta.total_token_count

            from app.infrastructure import session_id_var, message_id_var, get_db_context
            from app.services.db_service import sync_save_model_usage
            
            session_id = session_id_var.get()
            message_id = message_id_var.get()
            
            if session_id:
                with get_db_context() as db:
                    sync_save_model_usage(
                        db=db,
                        session_id=session_id,
                        model_name=model_name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        message_id=message_id
                    )
    except Exception as e:
        logger.error(f"Error logging Gemini token usage to DB: {e}")



class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def __init__(self, api_key: Optional[str], model: str = "gemini-3.1-flash-lite", timeout: int = 30):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") #support both direct config and env var
        self.model_name = model
        self.timeout = timeout
        self.enabled = bool(self.api_key)
        self.client = None

        if self.enabled:
            try:
                from google import genai

                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Gemini provider initialized: {model}")
            except Exception as exc:
                logger.warning(f"Gemini provider initialization failed: {exc}")
                self.enabled = False
        
        from prompts.dynamic_prompt_manager import DynamicPromptManager
        self.prompt_manager = DynamicPromptManager()

    def is_available(self) -> bool:
        return bool(self.enabled and self.client)

    @staticmethod
    #this ensure confidence score is [0,1].
    def _clamp_confidence(value: Any, default: float = 0.0) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = default
        return max(0.0, min(1.0, confidence))

    def detect_currency(self, question: str) -> Tuple[Optional[str], float, str]:
        # Currency is handled as part of get_unified_result's single LLM call.
        # Returning low-confidence fallback here lets workflow.py use fast regex.
        return None, 0.0, "unsupported_on_gemini_provider"

    def classify_intent(self, question: str) -> Tuple[str, float, str]:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")

        # Reuse unified prompt with empty dialog context fields
        prompt = self.prompt_manager.render(
            "gemini_unified_first_layer",
            history="",
            rolling_summary="",
            context="",
            user_input=question
        )

        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=150
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            _log_gemini_usage(self.model_name, response)
            content = (response.text or "").strip()
            
            # Find matching closing brace for JSON extraction
            json_start = content.find("{")
            if json_start != -1:
                brace_count = 0
                json_end = -1
                for i in range(json_start, len(content)):
                    if content[i] == "{":
                        brace_count += 1
                    elif content[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break
                if json_end != -1:
                    json_str = content[json_start:json_end]
                    payload = json.loads(json_str)
                    
                    intent = str(payload.get("intent", "unclassified")).lower().strip()
                    confidence = self._clamp_confidence(payload.get("confidence", 0.5))
                    reasoning = str(payload.get("reason", "Gemini classification")).strip()
                    return intent, confidence, reasoning
                    
            raise ValueError(f"No JSON found in response: {content}")
        except Exception as exc:
            logger.error(f"Fallback intent classification failed: {exc}", exc_info=True)
            raise


    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
        prompt_name: str = "gemini_unified_first_layer",
    ) -> Tuple[str, Dict[str, Any]]:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")

        history_str = ""
        context_str = ""
        
        if context:
            if hasattr(context, "turns") and context.turns:
                history_str = "\nConversation History:\n"
                for turn in context.turns[-3:]:
                    user_val = turn.get("user") or turn.get("user_input", "")
                    bot_val = turn.get("bot") or turn.get("bot_response", "")
                    history_str += f"User: {user_val}\nAssistant: {bot_val}\n"
            
            parts = []
            for field in [
                "product_category", "commercial_description", "last_entity", 
                "import_export_mode", "origin_country", "destination_country", 
                "hs_code", "cif_value", "currency", "year", "month", "trade_agreement"
            ]:
                val = getattr(context, field, None)
                if val:
                    label = field.replace("_", " ").title()
                    parts.append(f"- {label}: {val}")
            if parts:
                context_str = "\nActive Session Context:\n" + "\n".join(parts) + "\n"

        prompt = self.prompt_manager.render(
            prompt_name,
            history=history_str,
            rolling_summary=getattr(context, "rolling_summary", "") if context else "",
            context=context_str,
            user_input=user_input
        )

        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=250
            )
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            _log_gemini_usage(self.model_name, response)
            content = (response.text or "").strip()
            
            # Parse JSON out of response
            json_start = content.find("{")
            if json_start != -1:
                brace_count = 0
                json_end = -1
                for i in range(json_start, len(content)):
                    if content[i] == "{":
                        brace_count += 1
                    elif content[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break
                if json_end != -1:
                    json_str = content[json_start:json_end]
                    payload = json.loads(json_str)
                    
                    rewritten = payload.get("rewritten_query", user_input)
                    was_rewritten = rewritten != user_input
                    return rewritten, {
                        "rewrite_reason": "lightweight_rewrite" if prompt_name == "gemini_rewrite_input" else "unified_rewrite_fallback",
                        "confidence": self._clamp_confidence(payload.get("confidence", 0.8)),
                        "intent_changed": was_rewritten,
                        "topic_switch": False,
                        "rewritten": was_rewritten,
                    }
                    
            raise ValueError(f"No JSON found in response: {content}")
        except Exception as exc:
            logger.warning(f"Fallback query rewrite failed: {exc}", exc_info=True)
            raise

    async def summarize_text(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not self.is_available():
            return text
        prompt = self.prompt_manager.render("shared_summarize_text", text=text)
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            _log_gemini_usage(self.model_name, response)
            return (response.text or "").strip() or text
        except Exception as e:
            logger.warning(f"Gemini summarization failed: {e}")
            return text


    async def translate_to_english(self, text: str) -> str:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")
        
        prompt = self.prompt_manager.render("shared_translate_to_english", text=text)
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            _log_gemini_usage(self.model_name, response)
            return (response.text or "").strip()
        except Exception as e:
            logger.warning(f"Gemini translation to English failed: {e}")
            raise

    async def translate_to_khmer(self, text: str) -> str:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")
        
        prompt = self.prompt_manager.render("shared_translate_to_khmer", text=text)
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            _log_gemini_usage(self.model_name, response)
            return (response.text or "").strip()
        except Exception as e:
            logger.warning(f"Gemini translation to Khmer failed: {e}")
            raise

    async def unified_first_layer_call(
        self,
        query: str,
        history: str = "",
        rolling_summary: str = "",
        context_str: str = ""
    ) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")

        prompt = self.prompt_manager.render(
            "gemini_unified_first_layer",
            history=history,
            rolling_summary=rolling_summary,
            context=context_str,
            user_input=query
        )

        try:
            # pyrefly: ignore [missing-import]
            from google.genai import types
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=500
            )
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            _log_gemini_usage(self.model_name, response)
            content = (response.text or "").strip()
            
            # Find the JSON block
            json_start = content.find("{")
            if json_start != -1:
                brace_count = 0
                json_end = -1
                for i in range(json_start, len(content)):
                    if content[i] == "{":
                        brace_count += 1
                    elif content[i] == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break
                if json_end != -1:
                    json_str = content[json_start:json_end]
                    return json.loads(json_str)
            raise ValueError(f"No JSON found in response: {content}")
        except Exception as exc:
            logger.warning(f"Unified first layer call failed: {exc}")
            raise


class GeminiFormatterProvider(BaseFormatterProvider):
    """
    Gemini-based formatter for polishing responses.
    
    Uses Google's Generative AI API to format raw responses
    into user-friendly output based on intent type.
    """

    @property
    def name(self) -> str:
        return "gemini"

    def __init__(self, config: FormatterServiceConfig):
        self.config = config
        self.api_key = config.gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = config.gemini_model or "gemini-3.1-flash-lite"
        self.timeout = config.timeout
        self.enabled = bool(self.api_key)
        self.client = None

        if self.enabled:
            try:
                from google import genai

                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Gemini Formatter Provider initialized: {self.model_name}")
            except Exception as e:
                logger.warning(f"Gemini Formatter Provider initialization failed: {e}")
                self.enabled = False

        from prompts.dynamic_prompt_manager import DynamicPromptManager
        self.prompt_manager = DynamicPromptManager()

    def is_available(self) -> bool:
        """Check if Gemini provider is available."""
        return bool(self.enabled and self.client)

    async def format_response(
        self,
        response_text: str,
        intent: FormatterIntent,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format response using Gemini based on intent type.
        
        Args:
            response_text: Raw response from service
            intent: Type of response (calculation, retrieval, etc.)
            original_question: User's original question
            context: Additional context (citations, etc.)
            
        Returns:
            Formatted response
        """
        if not self.is_available():
            logger.warning("Gemini formatter not available, returning raw response")
            return response_text

        # Extract citations if available
        citations = []
        if context and isinstance(context, dict):
            citations = context.get("citations", [])

        # Build formatting prompt based on intent
        prompt = self._build_formatting_prompt(
            response_text=response_text,
            intent=intent,
            original_question=original_question,
            citations=citations,
        )

        try:
            logger.debug(f"Formatting response for intent: {intent.value}")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            _log_gemini_usage(self.model_name, response)
            formatted = (response.text or "").strip()

            if not formatted:
                logger.warning("Gemini formatter returned empty response")
                return response_text

            return formatted

        except Exception as e:
            logger.error(f"Gemini formatting failed: {e}")
            return response_text

    async def format_response_stream(
        self,
        response_text: str,
        intent: FormatterIntent,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        """
        Stream the formatted response using Gemini.

        Raises the exception on failure so the caller (summarizer.py)
        can decide whether to fall back or emit an error event.
        """
        if not self.is_available():
            logger.warning("Gemini formatter not available, yielding raw response")
            yield response_text
            return

        citations = []
        if context and isinstance(context, dict):
            citations = context.get("citations", [])

        prompt = self._build_formatting_prompt(
            response_text=response_text,
            intent=intent,
            original_question=original_question,
            citations=citations,
        )

        try:
            logger.debug(f"Streaming formatting response for intent: {intent.value}")
            response_stream = await self.client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
            )
            prompt_tokens = None
            completion_tokens = None
            total_tokens = None

            async for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
                if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
                    meta = chunk.usage_metadata
                    prompt_tokens = meta.prompt_token_count
                    completion_tokens = meta.candidates_token_count
                    total_tokens = meta.total_token_count

            # Log after stream completes
            if prompt_tokens is not None:
                try:
                    from app.infrastructure import session_id_var, message_id_var, get_db_context
                    from app.services.db_service import sync_save_model_usage
                    session_id = session_id_var.get()
                    message_id = message_id_var.get()
                    if session_id:
                        with get_db_context() as db:
                            sync_save_model_usage(
                                db=db,
                                session_id=session_id,
                                model_name=self.model_name,
                                prompt_tokens=prompt_tokens,
                                completion_tokens=completion_tokens,
                                total_tokens=total_tokens,
                                message_id=message_id
                            )
                except Exception as db_err:
                    logger.error(f"Error logging streaming token usage: {db_err}")
        except Exception as e:
            logger.error(f"Gemini streaming formatting failed: {e}")
            raise

    def _build_formatting_prompt(
        self,
        response_text: str,
        intent: FormatterIntent,
        original_question: str,
        citations: Optional[list] = None,
    ) -> str:
        """Build the formatting prompt dynamically based on intent type."""
        base_guidelines = self.prompt_manager.render("base_formatting_guidelines")
        
        intent_mapping = {
            FormatterIntent.CALCULATION: "gemini_format_calculation",
            FormatterIntent.HS_CODE_LOOKUP: "gemini_format_hs_code",
            FormatterIntent.RETRIEVAL: "gemini_format_retrieval",
            FormatterIntent.TRADE_QUERY: "gemini_format_trade",
            FormatterIntent.GENERAL: "gemini_format_general",
        }
        
        prompt_name = intent_mapping.get(intent, "gemini_format_general")
        
        # Build citations block format matching original f-string logic
        citations_text = ""
        if citations:
            citations_joined = "\n".join(citations)
            if prompt_name == "gemini_format_trade":
                citations_text = f"Data sources: {citations_joined}"
            elif prompt_name == "gemini_format_retrieval":
                citations_text = f"Sources: {citations_joined}"
            elif prompt_name in ("gemini_format_policy", "gemini_format_definition"):
                citations_text = f"References: {citations_joined}"
            else:
                citations_text = f"Citations: {citations_joined}"
        
        intent_prompt = self.prompt_manager.render(
            prompt_name,
            question=original_question,
            response_text=response_text,
            citations_block=citations_text
        )
        
        return f"{base_guidelines}\n\n{intent_prompt}"

    async def unified_first_layer_call(
        self,
        query: str,
        history: str = "",
        rolling_summary: str = "",
        context_str: str = ""
    ) -> Dict[str, Any]:
        """
        Runs LLM validation, intent detection, and translation/rewriting in a single call
        using DynamicPromptManager ("gemini_unified_first_layer").
        Works across all languages (Khmer, English, Chinese, etc.).
        """
        if not self.is_available():
            return {}

        import datetime
        now = datetime.datetime.now()
        current_year = now.year

        try:
            prompt = self.prompt_manager.render(
                "gemini_unified_first_layer",
                current_datetime=now.strftime("%Y-%m-%d %H:%M:%S"),
                current_year=str(current_year),
                previous_year=str(current_year - 1),
                two_years_ago=str(current_year - 2),
                history=history or "None",
                rolling_summary=rolling_summary or "None",
                context=context_str or "None",
                user_input=query,
                question=query
            )
        except Exception as e:
            logger.warning(f"Failed to render gemini_unified_first_layer prompt from DynamicPromptManager: {e}")
            prompt = f"User Query: {query}\n{context_str}\n{history}"

        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=500
            )
            res = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            _log_gemini_usage(self.model_name, res)
            text = (res.text or "").strip()
            if text:
                return json.loads(text)
        except Exception as e:
            logger.warning(f"Gemini unified_first_layer_call failed: {e}")

        return {}



