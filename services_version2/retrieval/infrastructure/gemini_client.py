"""
Gemini LLM Client for Retrieval Service.
Uses Google Generative AI API to generate final answers from retrieval context.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any

import google.generativeai as genai 

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for interacting with Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = (api_key or "").strip()
        self.model_name = model
        self._model = None

        if self.api_key:
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model_name)

    async def generate_answer(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        intent: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[str]:
        """Generate a grounded answer from retrieval documents."""
        if not self._model:
            return None


        context_blocks = []
        for idx, doc in enumerate(documents[:15], start=1):
            hs_code = doc.get("metadata", {}).get("hs_code", "N/A")
            content = str(doc.get("content", "")).strip()
            if not content:
                continue
            context_blocks.append(
                f"[Document {idx}]\nHS Code: {hs_code}\nDescription: {content[:400]}"
            )

        # Build prompts for intents. Do NOT refuse to run just because context is missing;
        # HS endpoints must accept any user query. If context is empty we include a
        # short note so the model knows context is absent.
        intent_upper = (intent or "").upper()
        context_section = "Context Documents:\n" + "\n\n".join(context_blocks) if context_blocks else "Context Documents: (none provided)"

        if intent_upper == "HS_CODE_CANDIDATES_EXPLAIN_ALL":
            prompt = (
                "You are a customs HS code assistant. Use ONLY the provided context when present.\n\n"
                f"User Question: {query}\n\n"
                f"{context_section}\n\n"
                "Instructions:\n"
                "- For each candidate, output a bullet in this exact format: HS Code: <value> – Product Name: <short name>. Then, provide a 1-2 sentence explanation.\n"
                "- Do not omit the HS Code value. Always start each bullet with 'HS Code: <value>'.\n"
                "- After all candidates, select and rank the best HS code(s) for the query, and explicitly list their HS code values and short product names in your answer.\n"
                "- Keep each explanation concise and do not just repeat the description.\n"
                "- If multiple codes are equally relevant, explain why.\n"
                "- Do not invent HS codes not present in context."
            )
        elif intent_upper == "HS_LOOKUP":
            prompt = (
                "You are a customs HS assistant. Use ONLY the provided context when present.\n\n"
                f"User Question: {query}\n"
                f"Status: {status or 'success'}\n\n"
                f"{context_section}\n\n"
                "Write the final answer using this exact structure:\n"
                "1) Best Match: include HS code and short product name.\n"
                "2) What it Covers: 1-3 plain-language bullet points.\n"
                "3) Practical Note: one short caution about final tariff treatment depending on product specs.\n"
                "Do not invent HS codes not present in context."
            )
        elif intent_upper == "EXTRACT_SPECS":
            # For spec extraction, enforce a strict single-prefix response.
            prompt = (
                "You are an HS code prefix extractor. Return exactly one 6-digit HS code "
                "for the product described by the user. Return digits only. Do not "
                "return multiple codes, do not explain, and do not output anything "
                "other than the 6 digits. If you are unsure, return an empty string.\n\n"
                f"Input: {query}\n"
                "6-digit HS code:"
            )
        else:
            prompt = (
                "You are a helpful customs and trade assistant. Use ONLY the provided context when present. "
                "If the answer is missing from context, say so clearly.\n\n"
                f"User Question: {query}\n\n"
                f"{context_section}\n\n"
                "Write a complete, well-structured, user-friendly answer. "
                "Synthesize useful details from multiple documents when available."
            )

        def _extract_text(response) -> Optional[str]:
            # Try multiple places where text might appear in different SDK versions
            try:
                if hasattr(response, "text") and getattr(response, "text"):
                    return getattr(response, "text").strip()
            except Exception:
                pass
            try:
                # Some responses expose candidates or output parts
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
            try:
                # Last resort: check any 'output' or 'results' attribute
                for key in ("output", "results", "response"):
                    val = getattr(response, key, None)
                    if val:
                        s = repr(val)
                        if s:
                            return s[:4096]
            except Exception:
                pass
            return None

        def _do_generate() -> Optional[str]:
            try:
                response = self._model.generate_content(prompt)
            except Exception as exc:
                logger.warning(f"Gemini answer generation failed: {exc}")
                return None

            text = _extract_text(response)
            if text:
                return text

            # If no usable text returned, log the raw response for debugging
            logger.warning(f"Gemini returned no text parts. Raw response: {repr(response)[:2000]}")

            # Retry once with reduced context (if we had many docs), to handle size/safety issues
            try:
                small_context = []
                for idx, doc in enumerate(documents[:5], start=1):
                    hs_code = doc.get("metadata", {}).get("hs_code", "N/A")
                    content = str(doc.get("content", "")).strip()
                    if content:
                        small_context.append(f"[{idx}] HS {hs_code}: {content[:300]}")

                retry_section = "Context Documents:\n" + "\n\n".join(small_context) if small_context else "Context Documents: (none provided)"
                retry_prompt = (
                    "You are a customs HS assistant. The previous attempt returned no text. Retry using only the essential context.\n\n"
                    f"User Question: {query}\n\n"
                    f"{retry_section}\n\n"
                    "If you cannot answer confidently, say so."
                )
                response2 = self._model.generate_content(retry_prompt)
                text2 = _extract_text(response2)
                if text2:
                    return text2
                logger.warning(f"Gemini retry returned no text. Raw retry response: {repr(response2)[:2000]}")
            except Exception as exc:
                logger.warning(f"Gemini retry failed: {exc}")

            return None

        return await asyncio.to_thread(_do_generate)
