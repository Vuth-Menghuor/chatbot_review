"""Gemini-based formatter provider."""

import json
import logging
import os
from typing import Dict, Any, Optional

from .base import BaseFormatterProvider
from ..config import FormatterServiceConfig
from ..core.models import FormatterIntent

logger = logging.getLogger(__name__)


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
        """Build the formatting prompt based on intent type."""

        intent_prompts = {
            FormatterIntent.CALCULATION: self._prompt_calculation,
            FormatterIntent.HS_CODE_LOOKUP: self._prompt_hs_code,
            FormatterIntent.RETRIEVAL: self._prompt_retrieval,
            FormatterIntent.TRADE_QUERY: self._prompt_trade,
            FormatterIntent.GENERAL: self._prompt_general,
        }

        prompt_builder = intent_prompts.get(intent, self._prompt_general)
        citations_text = "\n".join(citations) if citations else ""

        return prompt_builder(
            response_text=response_text,
            question=original_question,
            citations=citations_text,
        )

    @staticmethod
    def _prompt_calculation(response_text: str, question: str, citations: str) -> str:
        """Formatting prompt for calculation responses."""
        return f"""You are a customs duty calculation expert. 
        
Format this tariff calculation into a clear, structured response:

Original Question: {question}

Raw Calculation:
{response_text}

{f"Citations: {citations}" if citations else ""}

Please format this as:
1. Clear summary of what was calculated
2. Step-by-step breakdown of duties and taxes
3. Total import costs
4. Any applicable exemptions or preferential rates

Keep calculations explicit and easy to follow. Use currency symbols and percentages clearly."""

    @staticmethod
    def _prompt_hs_code(response_text: str, question: str, citations: str) -> str:
        """Formatting prompt for HS code lookup responses."""
        return f"""You are an HS code classification expert.

Format this HS code lookup into a clear, structured response:

Original Question: {question}

Raw HS Code Data:
{response_text}

{f"Citations: {citations}" if citations else ""}

Please format this as:
1. Most likely HS code(s) with descriptions
2. Product category and classification logic
3. Alternative HS codes if applicable
4. Key characteristics that determine this classification

Use technical terms but explain them for business users."""

    @staticmethod
    def _prompt_retrieval(response_text: str, question: str, citations: str) -> str:
        """Formatting prompt for retrieval responses."""
        return f"""You are a customs information retrieval specialist.

Format this retrieved information into a clear, structured response:

Original Question: {question}

Raw Information:
{response_text}

{f"Sources: {citations}" if citations else ""}

Please format this as:
1. Direct answer to the question
2. Supporting details and context
3. Related information that may be helpful
4. Any limitations or caveats

Be concise but comprehensive."""

    @staticmethod
    def _prompt_trade(response_text: str, question: str, citations: str) -> str:
        """Formatting prompt for trade query responses."""
        return f"""You are a trade statistics expert.

Format this trade data into a clear, structured response:

Original Question: {question}

Raw Trade Data:
{response_text}

{f"Data sources: {citations}" if citations else ""}

Please format this as:
1. Summary of key findings
2. Data visualization suggestions (if applicable)
3. Year-over-year or bilateral comparisons
4. Trends and insights

Use numbers and percentages clearly. Include units."""

    @staticmethod
    def _prompt_policy(response_text: str, question: str, citations: str) -> str:
        """Formatting prompt for policy query responses."""
        return f"""You are a customs policy expert.

Format this policy information into a clear, structured response:

Original Question: {question}

Raw Policy Information:
{response_text}

{f"References: {citations}" if citations else ""}

Please format this as:
1. Concise answer to the question
2. Step-by-step procedure or requirements
3. Documents needed or forms to file
4. Who to contact or where to find more info
5. Any exceptions or special cases

Be actionable and specific."""

    @staticmethod
    def _prompt_definition(response_text: str, question: str, citations: str) -> str:
        """Formatting prompt for definition responses."""
        return f"""You are a customs terminology expert.

Format this definition into a clear, structured response:

Original Question: {question}

Raw Definition:
{response_text}

{f"References: {citations}" if citations else ""}

Please format this as:
1. Clear, concise definition in simple language
2. Technical explanation (if needed)
3. Examples of usage or application
4. Related terms that may be relevant
5. When/where this term is used in customs

Make it accessible to non-specialists."""

    @staticmethod
    def _prompt_general(response_text: str, question: str, citations: str) -> str:
        """Formatting prompt for general responses."""
        return f"""You are a customs and trade information specialist.

Format this response into a clear, structured answer:

Original Question: {question}

Raw Response:
{response_text}

{f"Sources: {citations}" if citations else ""}

Please organize this into:
1. Direct answer
2. Supporting details
3. Related information
4. Next steps or recommendations

Be clear and well-organized."""
