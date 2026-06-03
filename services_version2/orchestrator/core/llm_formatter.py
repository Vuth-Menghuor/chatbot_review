"""
LLM Formatter Module - Response Formatting & Enhancement
=========================================================

Uses Gemini LLM to format responses in clear, user-friendly way.
Special handling for CALCULATION intents with step-by-step formulas.

Usage:
    formatter = LLMFormatter()
    formatted = await formatter.format_response(
        response, intent, context, hs_code_info
    )
"""

import logging
import re
import os
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import httpx

logger = logging.getLogger(__name__)


@dataclass
class CalculatorResponse:
    """Response from Calculator Service."""
    total: float  # Total tax in KHR
    breakdown: Dict[str, float]  # CD, ST, VAT, ET breakdown
    assumptions: list = None
    rates_applied: Dict[str, float] = None
    
    def __post_init__(self):
        if self.assumptions is None:
            self.assumptions = []
        if self.rates_applied is None:
            self.rates_applied = {}


@dataclass
class HSCodeInfo:
    """HS Code information from Retrieval Service."""
    hs_code: str
    description: str
    category: str = ""


class FormatterIntent(str, Enum):
    """Which type of response to format."""
    CALCULATION = "calculation"
    RETRIEVAL = "retrieval"
    TRADE_QUERY = "trade_query"
    POLICY = "policy"
    DEFINITION = "definition"
    GENERAL = "general"


class LLMFormatter:
    """
    Format service responses using Gemini LLM for improved readability.
    
    Special handling for CALCULATION intents:
    - Shows step-by-step calculations with formulas
    - Explains each tax component
    - Includes assumptions and data sources
    """

    def __init__(self, gemini_api_key: Optional[str] = None):
        """
        Initialize formatter with Gemini API key.
        
        Args:
            gemini_api_key: Gemini API key (defaults to env var GEMINI_API_KEY)
        """
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        self.gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
        self.model = "gemini-pro"
        self.enabled = bool(self.gemini_api_key)
        
        if not self.enabled:
            logger.warning("Gemini API key not configured - formatter disabled")
        else:
            logger.info(f"✓ LLMFormatter initialized with Gemini API")

    async def format_response(
        self,
        response_text: str,
        intent: FormatterIntent,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format response based on intent type using Gemini.
        
        Args:
            response_text: Raw response from service
            intent: Type of response (calculation, retrieval, etc.)
            original_question: User's original question
            context: Additional context (exchange_rate, hs_code_info, etc.)
            
        Returns:
            Formatted, user-friendly response
        """
        if not self.enabled:
            logger.debug("LLM formatting disabled (no Gemini API key) - returning raw response")
            return response_text

        try:
            if intent == FormatterIntent.CALCULATION:
                return await self._format_calculation(
                    response_text, original_question, context
                )
            elif intent == FormatterIntent.RETRIEVAL:
                return await self._format_retrieval(
                    response_text, original_question
                )
            elif intent == FormatterIntent.TRADE_QUERY:
                return await self._format_trade_query(
                    response_text, original_question
                )
            elif intent == FormatterIntent.POLICY:
                return await self._format_policy(
                    response_text, original_question
                )
            else:
                # Generic formatting for other intents
                return await self._format_generic(
                    response_text, original_question
                )
        except Exception as e:
            logger.warning(f"LLM formatting failed: {e}. Returning raw response.")
            return response_text

    async def _format_calculation(
        self,
        response_text: str,
        original_question: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Format calculation response with step-by-step formulas using Gemini.
        
        Args:
            response_text: "Total: 321800 KHR. Breakdown: CD=0, ST=0, VAT=321760, ET=0"
            original_question: "Calculate tax for HS 0102.29.11 CIF $800 from China"
            context: {
                'exchange_rate': 4022,
                'hs_code_info': HSCodeInfo(...),
                'cif_value': 800,
                'cif_currency': 'USD',
                'origin_country': 'China',
                'rates': {'cd_rate': 0, 'st_rate': 0, 'vat_rate': 0.10, 'et_rate': 0}
            }
            
        Returns:
            Formatted response with step-by-step calculations
        """
        context = context or {}
        
        # Build detailed calculation breakdown
        breakdown = self._build_calculation_breakdown(
            response_text,
            original_question,
            context
        )
        
        # Create Gemini prompt for formatting
        gemini_prompt = f"""You are a Cambodia customs and trade expert. Format this import tax calculation showing step-by-step formulas and clear breakdown.

User Question: {original_question}
Calculator Result: {response_text}

{breakdown}

IMPORTANT - Format the response with:
1. Product information and HS code details (if available)
2. Input parameters (CIF value, currency, origin country)
3. Exchange rate conversion (if currencies differ)
4. STEP-BY-STEP calculation with FORMULAS for each tax component:
   - Step 1: Currency Conversion (if needed): Show formula
   - Step 2: Customs Duty (CD): Show calculation formula
   - Step 3: Special Tax (ST): Show calculation formula
   - Step 4: Value Added Tax (VAT): Show calculation formula
   - Step 5: Excise Tax (ET): Show calculation formula
5. Final breakdown table with all components and amounts
6. TOTAL TAX prominently displayed with currency (KHR)
7. Assumptions applied and data sources

Format requirements:
- Use clear section headers with dividing lines
- Show all formulas explicitly
- All values must include units (KHR, USD, %, etc.)
- Be concise but informative
- Use professional tone

Response should be 150-300 words."""

        try:
            formatted = await self._call_gemini(gemini_prompt)
            logger.debug(f"Calculation response formatted by Gemini")
            return formatted
        except Exception as e:
            logger.warning(f"Gemini formatting for calculation failed: {e}")
            # Fallback to structured format
            return self._fallback_calculation_format(response_text, context)

    def _build_calculation_breakdown(
        self,
        response_text: str,
        original_question: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Build detailed calculation breakdown for Gemini formatting.
        
        Returns string describing the calculation steps.
        """
        hs_code_info = context.get('hs_code_info')
        exchange_rate = context.get('exchange_rate', 4022)
        cif_value = context.get('cif_value', 'N/A')
        cif_currency = context.get('cif_currency', 'USD')
        origin = context.get('origin_country', 'Unknown')
        rates = context.get('rates', {})
        
        # Parse breakdown from response
        breakdown_match = re.search(
            r'CD=(\d+), ST=(\d+), VAT=(\d+), ET=(\d+)',
            response_text
        )
        
        if breakdown_match:
            cd, st, vat, et = breakdown_match.groups()
        else:
            cd = st = vat = et = 0
        
        # Build detailed description
        breakdown = f"""
CALCULATION CONTEXT:
• HS Code: {hs_code_info.hs_code if hs_code_info else 'Unknown'}
• Description: {hs_code_info.description if hs_code_info else 'Unknown'}
• CIF Value: {cif_value} {cif_currency}
• Origin Country: {origin}
• Exchange Rate: 1 {cif_currency} = {exchange_rate} KHR

TAX COMPONENTS TO CALCULATE:
1. Customs Duty (CD): {rates.get('cd_rate', 0)}% rate = {cd} KHR
2. Special Tax (ST): {rates.get('st_rate', 0)}% rate = {st} KHR
3. Value Added Tax (VAT): {rates.get('vat_rate', 0.10) * 100}% rate = {vat} KHR
4. Excise Tax (ET): {rates.get('et_rate', 0)}% rate = {et} KHR

TOTAL TAX: {int(cd) + int(st) + int(vat) + int(et)} KHR
"""
        return breakdown

    def _fallback_calculation_format(
        self,
        response_text: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Fallback formatting if Gemini is unavailable.
        
        Still shows step-by-step but in simpler format.
        """
        hs_code_info = context.get('hs_code_info')
        exchange_rate = context.get('exchange_rate', 4022)
        
        # Parse the response
        total_match = re.search(r'Total: (\d+)', response_text)
        total = total_match.group(1) if total_match else "Unknown"
        
        formatted = f"""
IMPORT TAX CALCULATION RESULT
{'─' * 50}

Product: {hs_code_info.description if hs_code_info else 'N/A'}
HS Code: {hs_code_info.hs_code if hs_code_info else 'N/A'}

Exchange Rate: 1 USD = {exchange_rate} KHR

{response_text}

TOTAL: {total} KHR
{'─' * 50}
"""
        return formatted

    async def _format_retrieval(
        self,
        response_text: str,
        original_question: str
    ) -> str:
        """Format retrieval/HS code lookup response using Gemini."""
        gemini_prompt = f"""You are a customs expert. Format this HS code lookup result clearly and concisely.

Question: {original_question}
Result: {response_text}

Please format with:
- HS Code and full description
- Product classification category
- Key characteristics or notes
- Be concise (100-200 words)"""

        try:
            return await self._call_gemini(gemini_prompt)
        except:
            return response_text

    async def _format_trade_query(
        self,
        response_text: str,
        original_question: str
    ) -> str:
        """Format trade data query response using Gemini."""
        gemini_prompt = f"""You are a trade data analyst. Format this trade information clearly.

Question: {original_question}
Data: {response_text}

Please format with clear structure, statistics in readable format with explanations (100-200 words)."""

        try:
            return await self._call_gemini(gemini_prompt)
        except:
            return response_text

    async def _format_policy(
        self,
        response_text: str,
        original_question: str
    ) -> str:
        """Format policy/regulation response."""
        return response_text  # Usually already well-formatted from retrieval

    async def _format_generic(
        self,
        response_text: str,
        original_question: str
    ) -> str:
        """Generic formatting for other response types."""
        return response_text

    async def _call_gemini(self, prompt: str) -> str:
        """
        Call Gemini API for formatting.
        
        Args:
            prompt: Formatting prompt
            
        Returns:
            Formatted response from Gemini
        """
        if not self.gemini_api_key:
            raise Exception("Gemini API key not configured")
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.gemini_url}?key={self.gemini_api_key}",
                    json={
                        "contents": [
                            {
                                "parts": [
                                    {
                                        "text": prompt
                                    }
                                ]
                            }
                        ],
                        "generationConfig": {
                            "temperature": 0.3,  # Low temp for consistent formatting
                            "topK": 40,
                            "topP": 0.95,
                            "maxOutputTokens": 1024,
                        },
                        "safetySettings": [
                            {
                                "category": "HARM_CATEGORY_UNSPECIFIED",
                                "threshold": "BLOCK_NONE",
                            }
                        ]
                    }
                )
                response.raise_for_status()
                result = response.json()
                
                # Extract text from Gemini response
                try:
                    text = result['candidates'][0]['content']['parts'][0]['text'].strip()
                    return text
                except (KeyError, IndexError, TypeError) as e:
                    logger.error(f"Failed to parse Gemini response: {result}")
                    raise Exception(f"Invalid Gemini response format: {e}")
                    
        except httpx.HTTPError as e:
            logger.warning(f"Gemini API HTTP error: {e}")
            raise
        except Exception as e:
            logger.warning(f"Gemini API call failed: {e}")
            raise

    def disable(self):
        """Disable LLM formatting (use raw responses)."""
        self.enabled = False
        logger.info("LLM formatting disabled")

    def enable(self):
        """Enable LLM formatting."""
        if self.gemini_api_key:
            self.enabled = True
            logger.info("LLM formatting enabled")
        else:
            logger.warning("Cannot enable formatting - no Gemini API key")

    def is_available(self) -> bool:
        """Check if LLM formatter is operational."""
        return self.enabled


# ============================================================================
# Backward Compatibility Layer
# ============================================================================

@dataclass
class LLMFormatterConfig:
    """Configuration for LLM formatter (backward compatible)."""
    gemini_api_key: Optional[str] = None
    timeout: int = 30


class LLMResponseFormatter:
    """
    Backward-compatible wrapper around LLMFormatter.
    
    This allows existing code (like app.py) to use the old API while
    the actual implementation is in the LLMFormatter class above.
    """
    
    def __init__(self, config: Optional[LLMFormatterConfig] = None):
        """
        Initialize formatter.
        
        Args:
            config: LLMFormatterConfig instance
        """
        self.config = config or LLMFormatterConfig()
        self.formatter = LLMFormatter(
            gemini_api_key=self.config.gemini_api_key
        )
    
    async def format_response(
        self,
        base_answer: str,
        question: str,
        intent: str,
        context: Optional[str] = None,
        citations: Optional[list] = None
    ) -> str:
        """Format response using Gemini formatter."""
        try:
            # Map to FormatterIntent if possible
            intent_map = {
                'calculation': FormatterIntent.CALCULATION,
                'retrieval': FormatterIntent.RETRIEVAL,
                'trade_query': FormatterIntent.TRADE_QUERY,
                'policy': FormatterIntent.POLICY,
            }
            formatter_intent = intent_map.get(intent.lower(), FormatterIntent.GENERAL)
            
            return await self.formatter.format_response(
                response_text=base_answer,
                intent=formatter_intent,
                original_question=question,
                context={'citations': citations} if citations else None
            )
        except Exception as e:
            logger.warning(f"Error formatting response: {e}")
            return base_answer
    
    def is_available(self) -> bool:
        """Check if formatter is available."""
        return self.formatter.is_available()


# Singleton instance factory
_formatter_instance: Optional[LLMFormatter] = None
_response_formatter_instance: Optional[LLMResponseFormatter] = None


def get_formatter() -> LLMFormatter:
    """
    Get or create singleton formatter instance.
    
    Returns:
        LLMFormatter instance
    """
    global _formatter_instance
    if _formatter_instance is None:
        _formatter_instance = LLMFormatter()
        logger.info("Initialized LLMFormatter singleton with Gemini")
    return _formatter_instance


def get_response_formatter(config: Optional[LLMFormatterConfig] = None) -> LLMResponseFormatter:
    """
    Get or create singleton LLMResponseFormatter instance.
    
    This is the backward-compatible factory function for app.py.
    
    Args:
        config: Optional LLMFormatterConfig
        
    Returns:
        LLMResponseFormatter instance
    """
    global _response_formatter_instance
    if _response_formatter_instance is None:
        _response_formatter_instance = LLMResponseFormatter(config or LLMFormatterConfig())
        logger.info("Initialized LLMResponseFormatter singleton with Gemini")
    return _response_formatter_instance


if __name__ == "__main__":
    # Test the formatter
    logging.basicConfig(level=logging.DEBUG)
    
    print("\nGemini LLM Formatter Configuration")
    print("=" * 50)
    print("API Key required: GEMINI_API_KEY environment variable")
    print("Model: gemini-pro")
    print("\nFormatter is ready to format responses with Gemini API")
