"""Gemini provider adapter for HS selection and summarization tasks."""

import asyncio
#for parse LLM JSON responses
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .base import BaseLLMProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    def __init__(self, api_key: Optional[str], model: str = "gemini-3.1-flash-lite", timeout: int = 30):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") #support both direct config and env var
        self.model_name = model
        self.timeout = timeout
        self.enabled = bool(self.api_key)
        self.gen_model = None

        if self.enabled:
            try:
                import google.generativeai as genai #dynamic gemini import 

                genai.configure(api_key=self.api_key)
                self.gen_model = genai.GenerativeModel(model)
                logger.info(f"Gemini provider initialized: {model}")
            except Exception as exc:
                logger.warning(f"Gemini provider initialization failed: {exc}")
                self.enabled = False

    def is_available(self) -> bool:
        return bool(self.enabled and self.gen_model)

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

        prompt = (
            "Classify the user's query into one of these intents: "
            "hs_code_lookup, calculation, trade_query, definition, policy_query, unclassified. "
            "Return JSON only with keys intent, confidence, reasoning.\n\n"
            f"Query: {question}"
        )

        try:
            response = self.gen_model.generate_content(prompt) #send request to Gemini
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

    def detect_currency(self, question: str) -> Tuple[Optional[str], float, str]:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")

        prompt = (
            "You are a currency detection assistant. "
            "Identify the currency referenced in the query. "
            "Prioritize explicit currency mentions/slang over country names. "
            "If query contains 'bucks' or 'greenback(s)' -> USD. "
            "If query contains 'quid' -> GBP. "
            "Return JSON only with keys: currency, confidence, reasoning. "
            "Supported currencies: USD, KHR, EUR, THB, CNY, VND, GBP, JPY, SGD, MYR. "
            "If unsure, set currency to null and confidence to 0.0.\n\n"
            f"Query: {question}"
        )

        
        """
        ("USD", 0.92, "Detected 'bucks' → USD")
        """
        try:
            response = self.gen_model.generate_content(prompt)
            content = (response.text or "").strip()
            
            # Better JSON extraction
            json_start = content.find("{")
            if json_start == -1:
                raise ValueError("No '{' found in Gemini currency response")
            
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
                raise ValueError("Unbalanced braces in Gemini currency response")
            
            json_str = content[json_start:json_end]
            payload = json.loads(json_str)
            
            # Validate currency
            currency = payload.get("currency")
            if currency is not None:
                currency = str(currency).upper().strip() #normalize to uppercase and remove whitespace
                if currency not in {"USD", "KHR", "EUR", "THB", "CNY", "VND", "GBP", "JPY", "SGD", "MYR"}:
                    logger.debug(f"Invalid currency returned: {currency}, setting to None")
                    currency = None
            
            # Validate confidence
            try:
                confidence = float(payload.get("confidence", 0.0))
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.0
            
            reasoning = str(payload.get("reasoning", "currency_detection")).strip()
            if not reasoning:
                reasoning = "currency_detection"
            
            return currency, confidence, reasoning
        except json.JSONDecodeError as exc:
            logger.error(f"JSON parse error in Gemini currency detection: {exc}")
            raise ValueError(f"Invalid JSON from Gemini: {exc}")
        except ValueError as exc:
            logger.error(f"Currency detection validation error: {exc}")
            raise

    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[Any] = None,
        intent_hint: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")

        prompt = (
            "Rewrite the user query with strict fidelity to the original meaning. "
            "Do not add new information. Do not change structured values. "
            "Preserve ambiguity when the original query is ambiguous. "
            "Do not infer missing product details, trade terms, quantities, classifications, or countries beyond what the user explicitly provided."
            "Keep the rewrite as close as possible to the original query. "
            "If the query is already clear, return it unchanged. "
            "Do not change HS codes, numbers, currencies, country names, dates, or product names. "
            "Return only the rewritten query.\n\n"
            f"Query: {user_input}"
        )
        try:
            response = self.gen_model.generate_content(prompt)
            rewritten = (response.text or "").strip() or user_input
            return rewritten, {
                "rewrite_reason": "gemini_rewrite",
                "confidence": 0.8,
                "intent_changed": False,
                "topic_switch": False,
            }
        except Exception as exc:
            logger.warning(f"Gemini rewrite failed: {exc}")
            raise

    async def summarize_text(self, text: str, context: Optional[Dict[str, Any]] = None) -> str:
        if not self.is_available():
            return text
        prompt = (
            "Summarize the following content in 3 concise bullet points. "
            "Do not add new information.\n\n"
            f"Content: {text}"
        )
        try:
            response = self.gen_model.generate_content(prompt)
            return (response.text or "").strip() or text
        except Exception as e:
            logger.warning(f"Gemini summarization failed: {e}")
            return text

    async def select_best_hs_code(self, query: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not candidates:
            return {
                "selected_code": None, 
                "confidence": 0.0, 
                "reason": "No candidates", 
                "index": -1,
                "top_3_candidates": []  # ← NEW: Return top 3 for rewriting
            }

        if not self.is_available():
            best = max(candidates, key=lambda item: item.get("score", 0))
            return {
                "selected_code": best.get("hs_code"),
                "confidence": best.get("score", 0.0),
                "reason": "Gemini unavailable, selected by score",
                "index": candidates.index(best),
                "top_3_candidates": candidates[:3]  # ← Fallback: return top 3 by score
            }

        candidates_text = "\n".join([
            f"{idx + 1}. {item.get('hs_code', '')} - {item.get('description', '')} (score: {item.get('score', 0):.2f})"
            for idx, item in enumerate(candidates[:5])
        ])
        
        prompt = (
            "Rank the top 3 HS code matches for the query.\n\n"
            "Rules:\n"
            "- Use only the provided candidates.\n"
            "- Do not invent missing product details.\n"
            "- Keep explanations short and user-friendly.\n\n"
            "Return ONLY valid JSON using this schema:\n"
            "{\n"
            '  "top_matches": [\n'
            "    {\n"
            '      "rank": 1,\n'
            '      "hs_code": "string",\n'
            '      "description": "string",\n'
            '      "confidence": 0.95,\n'
            '      "why_selected": "string"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            f"Query: {query}\n\n"
            f"Candidates:\n{candidates_text}"
        )

        try:
            response = self.gen_model.generate_content(prompt)
            content = (response.text or "").strip()
            
            # Better JSON extraction
            json_start = content.find("{")
            if json_start == -1:
                raise ValueError("No '{' found in Gemini response")
            
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
            payload = json.loads(json_str)

            # Handle new top_matches structure with validation
            top_matches = payload.get("top_matches", [])
            if not top_matches or not isinstance(top_matches, list) or len(top_matches) == 0:
                raise ValueError("Invalid response structure: missing or empty top_matches array")
            
            # ← NEW: Extract ALL top 3 matches (not just the first)
            top_3_codes = []
            best_match = top_matches[0]
            
            for rank, match in enumerate(top_matches[:3], start=1):
                if not isinstance(match, dict):
                    continue
                
                code = str(match.get("hs_code", "")).strip()
                if not code:
                    continue
                
                # Find this candidate in the original list
                for idx, candidate in enumerate(candidates):
                    if candidate.get("hs_code") == code:
                        top_3_codes.append({
                            "rank": rank,
                            "hs_code": code,
                            "index": idx,
                            "candidate": candidate
                        })
                        break
            
            # Validate best match
            if not isinstance(best_match, dict):
                raise ValueError("top_matches[0] is not a dictionary")
            
            selected_code = str(best_match.get("hs_code", "")).strip()
            if not selected_code:
                raise ValueError("top_matches[0] missing hs_code")
            
            try:
                confidence = float(best_match.get("confidence", 0.0))
                confidence = max(0.0, min(1.0, confidence))
            except (TypeError, ValueError):
                confidence = 0.0
            
            reason = str(best_match.get("why_selected", "Selected by Gemini")).strip()
            if not reason:
                reason = "Selected by Gemini"
                
            # Find the candidate index for best match
            selected_idx = -1
            for idx, candidate in enumerate(candidates):
                if candidate.get("hs_code") == selected_code:
                    selected_idx = idx
                    break
            
            return {
                "selected_code": selected_code,
                "confidence": confidence,
                "reason": reason,
                "index": selected_idx,
                "top_3_candidates": [item["candidate"] for item in top_3_codes]  # ← NEW: return the actual candidates
            }
        except json.JSONDecodeError as exc:
            logger.error(f"JSON parse error in Gemini HS selection: {exc}")
            best = max(candidates, key=lambda item: item.get("score", 0))
            return {
                "selected_code": best.get("hs_code"),
                "confidence": best.get("score", 0.0),
                "reason": f"JSON parse error, selected by score: {exc}",
                "index": candidates.index(best),
                "top_3_candidates": candidates[:3]
            }
        except ValueError as exc:
            logger.error(f"Validation error in Gemini HS selection: {exc}")
            best = max(candidates, key=lambda item: item.get("score", 0))
            return {
                "selected_code": best.get("hs_code"),
                "confidence": best.get("score", 0.0),
                "reason": f"Validation error, selected by score: {exc}",
                "index": candidates.index(best),
                "top_3_candidates": candidates[:3]
            }
        except Exception as exc:
            logger.error(f"Unexpected error in Gemini HS selection: {exc}", exc_info=True)
            best = max(candidates, key=lambda item: item.get("score", 0))
            return {
                "selected_code": best.get("hs_code"),
                "confidence": best.get("score", 0.0),
                "reason": "Gemini selection failed, selected by score",
                "index": candidates.index(best),
                "top_3_candidates": candidates[:3]
            }

    async def rewrite_descriptions_batch(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.is_available():
            return candidates

        # Limit concurrent requests to avoid overwhelming the API
        MAX_CONCURRENT = 5
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)

        async def rewrite_one(candidate: Dict[str, Any]) -> Dict[str, Any]:
            description = candidate.get("description", "")
            hs_code = candidate.get("hs_code", "")
            if not description:
                return candidate

            prompt = (
                f"Rewrite this technical HS description for code {hs_code} to be concise and user-friendly. "
                "Return only the rewritten text.\n\n"
                f"Description: {description}"
            )
            
            async with semaphore:
                try:
                    response = await asyncio.to_thread(self.gen_model.generate_content, prompt)
                    rewritten = (response.text or "").strip() or description
                    item = candidate.copy()
                    item["original_description"] = description
                    item["description"] = rewritten
                    logger.debug(f"Rewritten description for HS {hs_code}: {rewritten[:50]}...")
                    return item
                except Exception as exc:
                    logger.warning(f"Failed to rewrite description for HS {hs_code}: {exc}")
                    return candidate

        return await asyncio.gather(*(rewrite_one(candidate) for candidate in candidates))

    async def extract_trade_parameters(self, question: str) -> Dict[str, Any]:
        if not self.is_available():
            raise RuntimeError("Gemini provider is not available")

        # Get current year dynamically
        import datetime
        current_year = datetime.datetime.now().year

        from services_version2.trade_query_version2.core.llm_extractor import SYSTEM_INSTRUCTION, parse_and_resolve_parameters

        prompt = (
            f"{SYSTEM_INSTRUCTION}\n\n"
            f"Context Information:\n"
            f"- Current Year: {current_year}\n\n"
            f"IMPORTANT: Resolve relative year references (e.g. \"last year\" -> {current_year - 1}, "
            f"\"this year\" -> {current_year}, \"past 3 years\" -> start_period: {current_year - 2}, end_period: {current_year}) "
            f"accurately relative to the Current Year ({current_year}).\n\n"
            f"User Question: \"{question}\""
        )

        try:
            logger.info(f"Invoking Gemini model '{self.model_name}' for trade parameter extraction in Orchestrator...")
            # Run generate_content in a separate thread so it doesn't block the async event loop
            response = await asyncio.to_thread(self.gen_model.generate_content, prompt)
            content = (response.text or "").strip()

            # Better JSON extraction
            json_start = content.find("{")
            if json_start == -1:
                raise ValueError("No '{' found in Gemini trade extraction response")

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
            parsed_raw = json.loads(json_str)
            logger.info(f"Gemini trade extraction raw response parsed: {parsed_raw}")

            # Resolve parameters using the function from llm_extractor
            processed = parse_and_resolve_parameters(parsed_raw, question)
            return processed
        except Exception as exc:
            logger.error(f"Failed to extract trade parameters via Gemini: {exc}", exc_info=True)
            raise
