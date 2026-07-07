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

    def classify_intent(self, question: str) -> Tuple[str, float, str]:
        if not self.is_available(): #check provider availability.
            raise RuntimeError("Gemini provider is not available")

        prompt = self.prompt_manager.render("gemini_classify_intent", question=question)

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            ) #send request to Gemini
            content = (response.text or "").strip() #extract text
            
            # Better JSON extraction: find the first JSON object boundaries
            json_start = content.find("{")
            if json_start == -1:
                raise ValueError("No '{' found in Gemini response")
            
            # Find matching closing brace (simple but effective)
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
            
            if json_end == -1:
                raise ValueError("Unbalanced braces in Gemini response")
            
            json_str = content[json_start:json_end]
            #convert json string to python object (dict)
            payload = json.loads(json_str)
            
            # Validate and extract fields with defaults
            intent = str(payload.get("intent", "unclassified")).lower().strip()
            if not intent or intent == "none":
                intent = "unclassified"
            
            try:
                confidence = float(payload.get("confidence", 0.5))
                confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
            except (TypeError, ValueError):
                logger.warning(f"Invalid confidence value: {payload.get('confidence')}")
                confidence = 0.5
            
            reasoning = str(payload.get("reasoning", "Gemini classification")).strip()
            if not reasoning:
                reasoning = "Gemini classification"
            
            logger.debug(f"Intent classification: intent={intent}, confidence={confidence:.2f}")
            return intent, confidence, reasoning
            
        except json.JSONDecodeError as exc:
            logger.error(f"JSON parse error in Gemini response: {exc}")
            raise ValueError(f"Invalid JSON from Gemini: {exc}")
        except ValueError as exc:
            logger.error(f"Validation error: {exc}")
            raise
        except Exception as exc:
            logger.error(f"Unexpected error in Gemini intent classification: {exc}", exc_info=True)
            raise


    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")

        history_str = ""
        context_str = ""
        
        if context:
            # Build conversation history
            if hasattr(context, "turns") and context.turns:
                history_str = "\nConversation History:\n"
                for turn in context.turns[-3:]:  # Last 3 turns for context
                    user_val = turn.get("user") or turn.get("user_input", "")
                    bot_val = turn.get("bot") or turn.get("bot_response", "")
                    history_str += f"User: {user_val}\nAssistant: {bot_val}\n"
            
            # Build active session parameters context
            parts = []
            if getattr(context, "product_category", None):
                parts.append(f"- Product Category: {context.product_category}")
            if getattr(context, "import_export_mode", None):
                parts.append(f"- Import/Export Mode: {context.import_export_mode}")
            if getattr(context, "currency", None):
                parts.append(f"- Currency: {context.currency}")
            if parts:
                context_str = "\nActive Session Context:\n" + "\n".join(parts) + "\n"

        prompt = self.prompt_manager.render(
            "gemini_rewrite_input",
            history=history_str,
            context=context_str,
            rolling_summary=getattr(context, "rolling_summary", "") if context else "",
            user_input=user_input
        )

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt,
            )
            rewritten = (response.text or "").strip() or user_input
            was_rewritten = rewritten != user_input
            return rewritten, {
                "rewrite_reason": "gemini_rewrite",
                "confidence": 0.8,
                "intent_changed": was_rewritten,
                "topic_switch": False,
                "rewritten": was_rewritten,
            }
        except Exception as exc:
            logger.warning(f"Gemini rewrite failed: {exc}")
            raise

    async def summarize_text(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not self.is_available():
            return text
        prompt = self.prompt_manager.render("shared_summarize_text", text=text)
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt,
            )
            return (response.text or "").strip() or text
        except Exception as e:
            logger.warning(f"Gemini summarization failed: {e}")
            return text


    async def translate_to_english(self, text: str) -> str:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")
        
        prompt = self.prompt_manager.render("shared_translate_to_english", text=text)
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt,
            )
            return (response.text or "").strip()
        except Exception as e:
            logger.warning(f"Gemini translation to English failed: {e}")
            raise

    async def translate_to_khmer(self, text: str) -> str:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")
        
        prompt = self.prompt_manager.render("shared_translate_to_khmer", text=text)
        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt,
            )
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
                temperature=0.0
            )
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt,
                config=config
            )
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
            formatted = (response.text or "").strip()

            if not formatted:
                logger.warning("Gemini formatter returned empty response")
                return response_text

            return formatted

        except Exception as e:
            logger.error(f"Gemini formatting failed: {e}")
            return response_text

    def _build_formatting_prompt(
        self,
        response_text: str,
        intent: FormatterIntent,
        original_question: str,
        citations: Optional[list] = None,
    ) -> str:
        """Build the formatting prompt dynamically based on intent type."""
        base_guidelines = self.prompt_manager.get_system_prompt("base_formatting_guidelines")
        
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



