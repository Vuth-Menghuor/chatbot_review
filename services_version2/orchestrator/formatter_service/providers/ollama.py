"""Ollama provider for response formatting."""
import logging
import re
import httpx
from typing import Optional, Dict, Any
from .base import BaseFormatterProvider
from ..core.models import FormatterIntent, HSCodeInfo
from ..config import FormatterServiceConfig

logger = logging.getLogger(__name__)

class OllamaFormatterProvider(BaseFormatterProvider):
    """Format service responses using local LLM."""
    
    def __init__(self, config: FormatterServiceConfig):
        self.config = config
        self.llm_url = config.ollama_host if config.ollama_host.startswith("http") else f"http://{config.ollama_host}:{config.ollama_port}"
        self.model = config.ollama_model
        
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
        
    """
    The workflow of how the formatter receives and processes data is as follows:
    1. Retrieval Service (Qdrant)
       ↓  returns raw rates (cd_rate, st_rate, vat_rate)
       ↓  via db.get_duty_rates() → _get_rates()

    2. Calculator Service
        ↓  uses those rates to compute cop_amount, sop_amount, vop_amount
        ↓  packages everything into TaxLineItem objects → line_items[]
        ↓  returns the full CalculationResult including line_items

    3. Formatter (ollama.py)
        ↓  receives line_items as part of context
        ↓  reads both rate AND amount from each item
    """

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
        llm_prompt = f"""Format this HS code lookup result clearly:

Question: {original_question}
Result: {response_text}

Include:
- HS Code and full description
- Product classification
- Any relevant notes
- Sources if available

Format with clear structure."""
        try:
            return await self._call_llm(llm_prompt)
        except:
            return response_text

    async def _format_trade_query(self, response_text: str, original_question: str) -> str:
        llm_prompt = f"""Format this trade data result clearly:

Question: {original_question}
Data: {response_text}

Include statistics in readable format with explanations."""
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
        
        formatting_prompt = f"""You are a trade and customs expert. The following is a product classification description from the HS (Harmonized System) code database:

Raw Description: {raw_description}

Please provide a clear, professional explanation of this product classification. The explanation should:
1. **Simplify**: Make the hierarchical classification clear and easy to understand
2. **Explain**: Break down what each level of the hierarchy means
3. **Clarify**: Remove redundancy and improve readability
4. **Add Context**: Explain what types of products fall under this classification

Provide the response in a clean, professional format suitable for a customs/trade document."""

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
        
        # Use LLM to extend and provide more detailed explanation
        extension_prompt = f"""You are a trade and customs expert. A user asked: "{original_question}"

The system provided this initial definition:
{response_text}

Please extend this definition to make it more comprehensive and educational. Include:
1. **Clear Definition**: A concise explanation of the term
2. **Context**: When and where this term is used in trade/customs
3. **Key Components**: Main elements or parts if applicable
4. **Examples**: Real-world examples if relevant
5. **Related Terms**: Similar or related concepts
6. **Practical Application**: How this applies in practice

Make sure the explanation is detailed enough for someone to fully understand the concept."""

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
