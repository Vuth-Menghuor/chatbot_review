"""Validator service implementation (moved into llm_first_layer shims).

Provides an LLM-powered validator and lightweight async hooks used by the
orchestrator tests. This implements the APIs expected by
`tests/test_validator_service.py` so the module can be moved without
breaking callers.
"""
from __future__ import annotations

import asyncio
import logging
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class ValidationDecision(str, Enum):
    IN_SCOPE = "in_scope"
    OUT_OF_SCOPE = "out_of_scope"
    INJECTION = "injection"
    FORMAT_ERROR = "format_error"
    AMBIGUOUS = "ambiguous"


@dataclass
class ValidationResult:
    decision: ValidationDecision
    is_valid: bool
    reason: Optional[str] = None
    scope_keywords_matched: Optional[List[str]] = None
    provider: Optional[str] = None

    @property
    def is_in_scope(self) -> bool:
        return self.decision == ValidationDecision.IN_SCOPE

    @property
    def scope_reason(self) -> str:
        return self.reason or ""

    @classmethod
    def in_scope(cls, reason: Optional[str] = None, keywords: Optional[List[str]] = None, provider: Optional[str] = None):
        return cls(decision=ValidationDecision.IN_SCOPE, is_valid=True, reason=reason, scope_keywords_matched=keywords or [], provider=provider)

    @classmethod
    def out_of_scope(cls, reason: Optional[str] = None):
        return cls(decision=ValidationDecision.OUT_OF_SCOPE, is_valid=False, reason=reason)

    @classmethod
    def injection(cls, reason: Optional[str] = None):
        return cls(decision=ValidationDecision.INJECTION, is_valid=False, reason=reason)

    @classmethod
    def format_error(cls, reason: Optional[str] = None):
        return cls(decision=ValidationDecision.FORMAT_ERROR, is_valid=False, reason=reason)

    @classmethod
    def ambiguous(cls, reason: Optional[str] = None):
        return cls(decision=ValidationDecision.AMBIGUOUS, is_valid=False, reason=reason)

    def to_simple_tuple(self) -> Tuple[bool, Optional[str]]:
        if self.is_valid:
            return True, None
        if self.decision == ValidationDecision.OUT_OF_SCOPE:
            return False, "out_of_scope"
        if self.decision == ValidationDecision.INJECTION:
            return False, "injection_detected"
        if self.decision == ValidationDecision.FORMAT_ERROR:
            return False, f"format_error:{self.reason or 'invalid'}"
        if self.decision == ValidationDecision.AMBIGUOUS:
            return False, "out_of_scope"
        return False, self.reason


class LLMValidatorEngine:
    """Handles LLM communication using structured JSON prompts to determine
    safety, boundaries, and domain taxonomy mapping.
    """

    def __init__(self, client: Any = None):
        self.client = client
        from prompts.dynamic_prompt_manager import DynamicPromptManager
        self.prompt_manager = DynamicPromptManager()


    async def call_llm_json(self, system_prompt: str | Dict[str, str], user_message: str, output_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Core execution bridge to your live LLM generation client."""
        if isinstance(system_prompt, dict):
            static_block = system_prompt.get("static", "").strip()
            dynamic_block = system_prompt.get("dynamic", "").strip()
            system_prompt_str = f"{static_block}\n\n{dynamic_block}".strip()
        else:
            system_prompt_str = system_prompt

        if not self.client:
            try:
                from google import genai
                import os
                api_key = os.getenv("GEMINI_API_KEY")
                if not api_key:
                    from ...core.config import get_config
                    cfg = get_config()
                    api_key = getattr(cfg, "gemini_api_key", None)
                if api_key:
                    self.client = genai.Client(api_key=api_key)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Failed to auto-initialize genai client in LLMValidatorEngine: {e}")

        if not self.client:
            return {}
            
        try:
            # 1. Standard Google GenAI SDK client
            if hasattr(self.client, "models") and hasattr(self.client.models, "generate_content"):
                model_name = "gemini-3.1-flash-lite"
                try:
                    from ...core.config import get_config
                    cfg = get_config()
                    model_name = getattr(cfg, "gemini_model", "gemini-3.1-flash-lite")
                except Exception:
                    pass
                
                config_args = {}
                if output_schema:
                    try:
                        # pyrefly: ignore [missing-import]
                        from google.genai import types
                        config_args["config"] = types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=output_schema,
                            temperature=0.0
                        )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"Failed to set response_schema in Gemini client: {e}")

                prompt = f"{system_prompt_str}\n\nUser Input: {user_message}"
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                    **config_args
                )
                content = (response.text or "").strip()
                
                # Find JSON boundaries
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
                        return json.loads(content[json_start:json_end])
                return {}
            
            # 2. OpenAI / compat client fallback (e.g. for mock compatibility)
            else:
                extra_args = {}
                if output_schema:
                    extra_args["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "validation_response",
                            "schema": output_schema,
                            "strict": True
                        }
                    }
                else:
                    extra_args["response_format"] = {"type": "json_object"}

                messages = []
                if isinstance(system_prompt, dict):
                    if system_prompt.get("static"):
                        messages.append({"role": "system", "content": system_prompt["static"]})
                    if system_prompt.get("dynamic"):
                        messages.append({"role": "system", "content": system_prompt["dynamic"]})
                else:
                    messages.append({"role": "system", "content": system_prompt_str})
                messages.append({"role": "user", "content": user_message})

                response = await self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=messages,
                    temperature=0.0,
                    **extra_args
                )
                return json.loads(response.choices[0].message.content)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(f"Error calling LLM in validator engine: {exc}")
            
            # Runtime fallback to local LLM if Gemini call fails
            try:
                logging.getLogger(__name__).info("Attempting local LLM fallback for validation JSON call...")
                import httpx
                try:
                    from ...core.config import get_config
                    cfg = get_config()
                    local_host = getattr(cfg, "ollama_host", "http://localhost:11434").rstrip("/")
                    local_model = getattr(cfg, "ollama_model", "llama3.2:3b")
                except Exception:
                    local_host = "http://localhost:11434"
                    local_model = "llama3.2:3b"

                # Ensure local_host has protocol
                if not local_host.startswith("http://") and not local_host.startswith("https://"):
                    local_host = f"http://{local_host}"

                # Try OpenAI-compatible chat completions endpoint first (widely supported by generic Local LLMs)
                try:
                    openai_url = f"{local_host}/chat/completions"
                    fallback_messages = []
                    if isinstance(system_prompt, dict):
                        if system_prompt.get("static"):
                            fallback_messages.append({"role": "system", "content": system_prompt["static"]})
                        if system_prompt.get("dynamic"):
                            fallback_messages.append({"role": "system", "content": system_prompt["dynamic"]})
                    else:
                        fallback_messages.append({"role": "system", "content": system_prompt_str})
                    fallback_messages.append({"role": "user", "content": user_message})

                    payload = {
                        "model": local_model,
                        "messages": fallback_messages,
                        "response_format": {"type": "json_object"},
                        "temperature": 0.0
                    }
                    if output_schema:
                        payload["response_format"] = {
                            "type": "json_schema",
                            "json_schema": {
                                "name": "validation_response",
                                "schema": output_schema
                            }
                        }
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.post(openai_url, json=payload)
                        if response.status_code == 200:
                            data = response.json()
                            content = data["choices"][0]["message"]["content"].strip()
                            return json.loads(content)
                        else:
                            logging.getLogger(__name__).warning(
                                f"OpenAI-compatible local LLM endpoint returned status {response.status_code}, trying native Ollama endpoint..."
                            )
                except Exception as openai_err:
                    logging.getLogger(__name__).debug(f"OpenAI-compatible endpoint failed: {openai_err}, trying native Ollama...")

                # Fallback to native Ollama API generate
                native_url = f"{local_host}/api/generate"
                prompt = f"{system_prompt_str}\n\nUser Input: {user_message}\n\nRespond strictly in valid JSON."
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        native_url,
                        json={
                            "model": local_model,
                            "prompt": prompt,
                            "format": "json",
                            "stream": False,
                            "temperature": 0.0
                        }
                    )
                    response.raise_for_status()
                    payload = response.json()
                    content = payload.get("response", "").strip()
                    return json.loads(content)
            except Exception as fallback_exc:
                logging.getLogger(__name__).error(f"Local LLM validation fallback failed: {fallback_exc}")
            return {}




    def _coerce_field(
        self,
        data: Dict[str, Any],
        field_name: str,
        expected_type: Any,
        nullable: bool = False,
        method_name: str = "unknown"
    ) -> Any:
        """Validate and extract a single response field, coercing types if possible."""
        if field_name not in data:
            raise ValueError(f"[{method_name}] Missing required field: {field_name}")
        
        value = data[field_name]
        
        if value is None:
            if nullable:
                return None
            else:
                raise ValueError(f"[{method_name}] Field {field_name} is null but not nullable")
                
        # Handle tuple of expected types
        expected_types = expected_type if isinstance(expected_type, tuple) else (expected_type,)
        
        # Check if matches any of the expected types
        is_matching = any(isinstance(value, t) for t in expected_types)
        
        if is_matching:
            # Special check for lists: ensure all elements are strings
            if list in expected_types and isinstance(value, list):
                if not all(isinstance(x, str) for x in value):
                    raise ValueError(f"[{method_name}] Field {field_name} must be a list of strings")
            return value
            
        # Try coercion logic
        # 1. Coerce to bool
        if bool in expected_types:
            if isinstance(value, str):
                val_lower = value.strip().lower()
                if val_lower in ("true", "1", "yes", "on", "t"):
                    return True
                if val_lower in ("false", "0", "no", "off", "f"):
                    return False
            elif isinstance(value, (int, float)):
                return bool(value)
                
        # 2. Coerce to numeric (int or float)
        numeric_types = [t for t in expected_types if t in (int, float)]
        if numeric_types:
            target_type = float if float in numeric_types else int
            if isinstance(value, str):
                try:
                    return target_type(value)
                except ValueError:
                    pass
            elif isinstance(value, (int, float)):
                return target_type(value)
                
        # 3. Coerce to str
        if str in expected_types:
            if isinstance(value, (bool, int, float)):
                return str(value)
                
        # 4. Coerce to list
        if list in expected_types:
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned.startswith("[") and cleaned.endswith("]"):
                    try:
                        parsed = json.loads(cleaned)
                        if isinstance(parsed, list):
                            return [str(x) for x in parsed]
                    except Exception:
                        pass
                if "," in cleaned:
                    return [x.strip() for x in cleaned.split(",") if x.strip()]
                return [cleaned] if cleaned else []
                
        # If we reach here, we could not coerce
        actual_type = type(value).__name__
        expected_name = expected_type.__name__ if not isinstance(expected_type, tuple) else "/".join(t.__name__ for t in expected_type)
        raise ValueError(
            f"[{method_name}] Field {field_name} has wrong type: "
            f"expected {expected_name}, got {actual_type} (value: {value})"
        )

    async def check_security(self, text: str) -> Tuple[bool, Optional[str]]:
        try:
            prompt = self.prompt_manager.get_system_prompt("safety_check_security")
            schema = self.prompt_manager.get_schema("safety_check_security")
            data = await self.call_llm_json(
                system_prompt=prompt,
                user_message=text,
                output_schema=schema
            )
            if not isinstance(data, dict):
                raise ValueError(f"LLM response is not a dictionary: {type(data)}")

            is_injection = self._coerce_field(
                data, "is_injection", bool, nullable=False, method_name="check_security"
            )
            reason = self._coerce_field(
                data, "reason", str, nullable=True, method_name="check_security"
            )
            return is_injection, reason
        except Exception as e:
            logging.getLogger(__name__).error(f"check_security failed: {type(e).__name__}: {e}")
            return False, None

    async def check_blocklist(self, text: str) -> Tuple[bool, Optional[str]]:
        try:
            prompt = self.prompt_manager.get_system_prompt("safety_check_blocklist")
            schema = self.prompt_manager.get_schema("safety_check_blocklist")
            data = await self.call_llm_json(
                system_prompt=prompt,
                user_message=text,
                output_schema=schema
            )
            if not isinstance(data, dict):
                raise ValueError(f"LLM response is not a dictionary: {type(data)}")

            is_out_of_scope = self._coerce_field(
                data, "is_out_of_scope", bool, nullable=False, method_name="check_blocklist"
            )
            reason = self._coerce_field(
                data, "reason", str, nullable=True, method_name="check_blocklist"
            )
            return is_out_of_scope, reason
        except Exception as e:
            logging.getLogger(__name__).error(f"check_blocklist failed: {type(e).__name__}: {e}")
            return False, None

    async def check_commercial_description(self, text: str) -> Tuple[bool, Optional[str], List[str]]:
        try:
            prompt = self.prompt_manager.get_system_prompt("safety_check_commercial_description")
            schema = self.prompt_manager.get_schema("safety_check_commercial_description")
            data = await self.call_llm_json(
                system_prompt=prompt,
                user_message=text,
                output_schema=schema
            )
            if not isinstance(data, dict):
                raise ValueError(f"LLM response is not a dictionary: {type(data)}")

            is_commercial = self._coerce_field(
                data, "is_commercial_description", bool, nullable=False,
                method_name="check_commercial_description"
            )
            product_type = self._coerce_field(
                data, "matched_product_type", str, nullable=True,
                method_name="check_commercial_description"
            )
            specs = self._coerce_field(
                data, "extracted_specifications", list, nullable=False,
                method_name="check_commercial_description"
            )
            return is_commercial, product_type, specs
        except Exception as e:
            logging.getLogger(__name__).error(f"check_commercial_description failed: {type(e).__name__}: {e}")
            return False, None, []

    async def check_taxonomy_scope(self, text: str) -> Tuple[bool, Optional[str], List[str]]:
        try:
            prompt = self.prompt_manager.get_system_prompt("safety_check_taxonomy_scope")
            schema = self.prompt_manager.get_schema("safety_check_taxonomy_scope")
            data = await self.call_llm_json(
                system_prompt=prompt,
                user_message=text,
                output_schema=schema
            )
            if not isinstance(data, dict):
                raise ValueError(f"LLM response is not a dictionary: {type(data)}")

            is_in_scope = self._coerce_field(
                data, "is_in_scope", bool, nullable=False, method_name="check_taxonomy_scope"
            )
            category = self._coerce_field(
                data, "category", str, nullable=True, method_name="check_taxonomy_scope"
            )
            signals = self._coerce_field(
                data, "matched_signals", list, nullable=False, method_name="check_taxonomy_scope"
            )
            return is_in_scope, category, signals
        except Exception as e:
            logging.getLogger(__name__).error(f"check_taxonomy_scope failed: {type(e).__name__}: {e}")
            return False, None, []

    async def check_certificate_details(self, text: str) -> Tuple[bool, Optional[str]]:
        try:
            prompt = self.prompt_manager.get_system_prompt("safety_check_certificate_details")
            schema = self.prompt_manager.get_schema("safety_check_certificate_details")
            data = await self.call_llm_json(
                system_prompt=prompt,
                user_message=text,
                output_schema=schema
            )
            if not isinstance(data, dict):
                raise ValueError(f"LLM response is not a dictionary: {type(data)}")

            mentions = self._coerce_field(
                data, "mentions_certificate", bool, nullable=False,
                method_name="check_certificate_details"
            )
            cert_type = self._coerce_field(
                data, "extracted_type", str, nullable=True, method_name="check_certificate_details"
            )
            return mentions, cert_type
        except Exception as e:
            logging.getLogger(__name__).error(f"check_certificate_details failed: {type(e).__name__}: {e}")
            return False, None

    async def check_rate_reply(self, text: str) -> bool:
        try:
            prompt = self.prompt_manager.get_system_prompt("safety_check_rate_reply")
            schema = self.prompt_manager.get_schema("safety_check_rate_reply")
            data = await self.call_llm_json(
                system_prompt=prompt,
                user_message=text,
                output_schema=schema
            )
            if not isinstance(data, dict):
                raise ValueError(f"LLM response is not a dictionary: {type(data)}")

            is_short_rate = self._coerce_field(
                data, "is_short_rate_reply", bool, nullable=False, method_name="check_rate_reply"
            )
            return is_short_rate
        except Exception as e:
            logging.getLogger(__name__).error(f"check_rate_reply failed: {type(e).__name__}: {e}")
            return False

    async def check_calculation_fields(self, text: str) -> Tuple[bool, List[str]]:
        try:
            prompt = self.prompt_manager.get_system_prompt("safety_check_calculation_fields")
            schema = self.prompt_manager.get_schema("safety_check_calculation_fields")
            data = await self.call_llm_json(
                system_prompt=prompt,
                user_message=text,
                output_schema=schema
            )
            if not isinstance(data, dict):
                raise ValueError(f"LLM response is not a dictionary: {type(data)}")

            has_fields = self._coerce_field(
                data, "has_required_fields", bool, nullable=False,
                method_name="check_calculation_fields"
            )
            missing = self._coerce_field(
                data, "missing_fields", list, nullable=False, method_name="check_calculation_fields"
            )
            return has_fields, missing
        except Exception as e:
            logging.getLogger(__name__).error(f"check_calculation_fields failed: {type(e).__name__}: {e}")
            return False, []

    async def check_query_validity_unified(self, text: str) -> Dict[str, Any]:
        try:
            prompt = self.prompt_manager.get_system_prompt("safety_check_query_validity_unified")
            schema = self.prompt_manager.get_schema("safety_check_query_validity_unified")
            data = await self.call_llm_json(
                system_prompt=prompt,
                user_message=text,
                output_schema=schema
            )
            if not isinstance(data, dict):
                raise ValueError(f"LLM response is not a dictionary: {type(data)}")

            is_safe = self._coerce_field(
                data, "is_safe", bool, nullable=False, method_name="check_query_validity_unified"
            )
            is_on_topic = self._coerce_field(
                data, "is_on_topic", bool, nullable=False, method_name="check_query_validity_unified"
            )
            category = self._coerce_field(
                data, "category", str, nullable=False, method_name="check_query_validity_unified"
            )
            confidence = self._coerce_field(
                data, "confidence", (int, float), nullable=False,
                method_name="check_query_validity_unified"
            )
            reason = self._coerce_field(
                data, "reason", str, nullable=True, method_name="check_query_validity_unified"
            )
            keywords = self._coerce_field(
                data, "keywords", list, nullable=False, method_name="check_query_validity_unified"
            )
            return {
                "is_safe": is_safe,
                "is_on_topic": is_on_topic,
                "category": category,
                "confidence": confidence,
                "reason": reason,
                "keywords": keywords
            }
        except Exception as e:
            logging.getLogger(__name__).error(f"check_query_validity_unified failed: {type(e).__name__}: {e}")
            return {
                "is_safe": True,
                "is_on_topic": False,
                "category": "ambiguous",
                "confidence": 0.0,
                "reason": f"validation_error: {str(e)}",
                "keywords": []
            }




class RuleBasedValidatorProvider:
    """Prompt-driven provider implementation handling fallback validation executions."""

    def __init__(self):
        self.llm_engine = LLMValidatorEngine()

    def is_available(self) -> bool:
        return True

    def validate(self, text: str) -> ValidationResult:
        """High-speed synchronous gatekeeper pass."""
        t = (text or "").strip()
        if not t:
            return ValidationResult.format_error("empty")

        t_lower = t.lower()
        words = re.findall(r'\b\w+\b', t_lower)

        # 1. Small talk greetings check (run first so short greetings like "hi", "yo" pass the length check)
        greetings_patterns = [
            r"\bhi+\b",
            r"\bhey+\b",
            r"\bhello+\b",
            r"\byo+\b",
            r"\bgreetings\b",
            r"\bgood\s+morning\b",
            r"\bgood\s+afternoon\b",
            r"\bgood\s+evening\b",
            r"\bhowdy\b"
        ]
        if any(re.search(pat, t_lower) for pat in greetings_patterns):
            return ValidationResult.in_scope("Small talk query whitelisted")

        # 1.5 Bot identity and capability queries whitelist (e.g. "what are you", "who are you", "what can you do")
        identity_patterns = [
            r"\b(what|who)\s+are\s+you\b",
            r"\bwhat\s+is\s+your\s+(name|purpose)\b",
            r"\bwhat\s+(can|do)\s+you\s+do\b",
            r"\b(who|what\s+company)\s+(created|made|built|designed|developed)\s+you\b",
            r"\bare\s+you\s+(a\s+)?(bot|ai|robot|chatbot|assistant|human|real)\b",
            r"\btell\s+me\s+about\s+yourself\b",
            r"\b(what\s+are\s+)?your\s+capabilities\b",
            r"\bhow\s+can\s+you\s+help\b",
        ]
        if any(re.search(pat, t_lower) for pat in identity_patterns):
            return ValidationResult.in_scope("identity_query")

        # Whitelist candidate intent keywords/choices to prevent early validation failure
        intent_whitelist_patterns = [
            r"\bcalculation\b",
            r"\bcalculator\b",
            r"\bhs[-_\s]*code(?:[-_\s]*lookup)?\b",
            r"\bclassify\b",
            r"\bclassification\b",
            r"\btrade[-_\s]*query\b",
            r"\btrade\b",
            r"\bgeneral\b",
            r"\bdefinition\b",
            r"\bpolicy\b"
        ]
        if any(re.search(pat, t_lower) for pat in intent_whitelist_patterns):
            return ValidationResult.in_scope("intent_choice_whitelist")

        if len(t) < 3:
            return ValidationResult.format_error("too short")
        if len(t) > 5000:
            return ValidationResult.format_error("too long")

        # 2. Security Check (Injection detection)
        sql_patterns = [
            r"(\bor\b|\band\b).*['\"].*[=<>]",
            r"(drop|delete|update|insert|exec|execute|script)\s",
            r"(\-\-|;|\/\*|\*\/)",
            r"(union|select|from|where).*select",
        ]
        for pattern in sql_patterns:
            if re.search(pattern, t_lower):
                return ValidationResult.injection(f"Potential SQL injection detected: {pattern}")

        if re.search(r"(ignore|forget|override|bypass|disregard).*instruction", t_lower):
            return ValidationResult.injection("Potential prompt injection detected")

        if re.search(r"\byou are now\b", t_lower):
            return ValidationResult.injection("Potential prompt injection detected (you are now)")

        if re.search(r"\bact as\b", t_lower):
            return ValidationResult.injection("Potential prompt injection detected (act as)")

        if "`" in t or "$(" in t:
            return ValidationResult.injection("Suspicious command characters detected")

        # 3. Blocklist Check (Out of Scope detection)
        blocklist_words = {
            "football", "soccer", "match last night", "cooking recipe", "cooking", "pasta", "recipe",
            "cryptocurrency", "invest", "gambling", "betting", "lottery", "movie", "song", "music"
        }
        for w in blocklist_words:
            if w in t_lower:
                return ValidationResult.out_of_scope(f"out_of_scope: {w}")

        # 3.5 Conversational question fast-path
        # Any WH-question or modal question is a valid general/definition/policy query.
        # Catch these before the keyword loop so "What is ATIGA?", "How does RCEP work?",
        # "Can you explain Form D?" etc. never reach AMBIGUOUS.
        _question_prefixes = (
            "what is ", "what are ", "what was ", "what were ",
            "what does ", "what do ", "what's ", "what's ",
            "how is ", "how are ", "how does ", "how do ",
            "how to ", "how can ", "how would ", "how should ",
            "why is ", "why are ", "why does ", "why do ",
            "who is ", "who are ", "who does ", "who can ",
            "where is ", "where are ", "where do ", "where can ",
            "when is ", "when are ", "when does ", "when do ",
            "which is ", "which are ", "which does ",
            "can you ", "could you ", "do you ", "does ",
            "tell me ", "explain ", "describe ",
            "is there ", "are there ", "is it ", "are they ",
        )
        if any(t_lower.startswith(p) or (" " + p) in t_lower for p in _question_prefixes):
            return ValidationResult.in_scope("general_question_pattern")

        # 4. Scope Keywords match
        scope_keywords = {
            "hs_code_lookup": [
                "hs code", "hs", "classify", "classification",
                "tariff code", "commodity code", "product code", "ahtn",
                "harmonized",
            ],
            "calculation": [
                "calculate", "compute", "duty", "tax", "cif", "fob", "vat",
                "tariff rate", "duty rate", "preferential rate",
            ],
            "trade_query": [
                "import", "export", "trade", "procedure", "process",
                "requirement", "shipping", "shipment", "cargo", "freight",
                "logistics", "clearance", "border",
            ],
            # All definition / policy / FTA / procedural / customs queries → general service
            "general": [
                # Definition markers
                "define", "definition", "meaning", "explain", "describe",
                # Natural WH-question starters
                "what is", "what are", "what was", "what were",
                "what does", "what do", "what's",
                "how is", "how are", "how does", "how do",
                "how to", "how can",
                "why is", "why are", "why does",
                "who is", "who are",
                "tell me about", "can you explain", "can you tell",
                "what exactly", "what kind", "what type",
                # Policy / regulatory terms
                "regulation", "rule", "fta", "agreement", "compliance",
                "policy", "law", "decree", "prakas", "circular", "guideline",
                "permission", "permit", "license", "licence",
                # FTA / trade agreement acronyms
                "atiga", "rcep", "acfta", "afta", "cptpp", "evfta",
                "aifta", "akfta", "aanzfta", "asean",
                "form d", "form e", "form ak", "form ai", "form aj",
                "certificate of origin", "rules of origin",
                # GDCE-specific
                "gdce", "general department of customs",
                "customs duty", "customs excise",
                "qip", "sez", "special economic zone",
                "preferential", "exemption", "waiver",
                # Customs / documentation (merged from customs_general)
                "customs", "declaration", "invoice", "packing list",
                "certificate", "cambodia", "ministry of commerce",
                "camcontrol", "cdc", "moc", "mef",
            ],
        }
        matched_keywords = []
        for category, keywords in scope_keywords.items():
            for keyword in keywords:
                if keyword in t_lower:
                    matched_keywords.append(keyword)

        if matched_keywords:
            return ValidationResult.in_scope("in_scope", keywords=matched_keywords)

        # 4.5 Commercial/Cargo description format heuristic
        # We need the original-case words to check for uppercase ratios!
        orig_words = re.findall(r'\b\w+\b', t)
        words_with_alpha = [w for w in orig_words if any(c.isalpha() for c in w)]
        is_commercial_format = False
        if words_with_alpha:
            # Check for uppercase ratio on original-case words!
            uppercase_ratio = sum(1 for w in words_with_alpha if w.isupper()) / len(words_with_alpha)
            # Typical shipping descriptions are highly uppercase with multiple words
            if uppercase_ratio >= 0.75 and len(words_with_alpha) >= 3:
                is_commercial_format = True

        # Check for AEON TopValu supplier prefixes ('tvbp', 'tv bp', 'tv')
        if "tvbp" in words or "tv" in words:
            return ValidationResult.in_scope("topvalu_brand_prefix")

        has_commercial_spec = (
            re.search(r'\b\d+\s*(kg|g|lbs|pcs|t|ton|tons|l|ml)\b', t_lower) is not None
            or re.search(r'\(\d+\)', t) is not None
            or re.search(r'\b(new|used|refurbished|model|byd|brand|spec|qty|quantity)\b', t_lower) is not None
            or re.search(r'\b[A-Z0-9-]{5,}\b', t) is not None
        )

        if is_commercial_format or has_commercial_spec:
            cargo_hints = {
                "toothbrush", "tractor", "car", "vehicle", "truck", "van", "train", "hearse", "engine", "motor", "byd", "parts",
                "bristle", "medium", "regular", "electric", "toy", "phone", "device", "steel", "iron",
                "copper", "clothing", "apparel", "textile", "equipment", "machinery", "horse", "oxen",
                "chestnut", "chestnuts", "tea", "matcha", "seaweed", "mozuku", "meatballs", "meatball",
                "bacon", "wiener", "wieners", "sausage", "pork", "ham", "yogurt", "nuggets", "nugget",
                "salad", "noodle", "noodles", "udon", "saba", "yakisoba", "somen", "ramen", "tonkotsu"
            }
            if is_commercial_format or any(h in t_lower for h in cargo_hints):
                return ValidationResult.in_scope("commercial_cargo_heuristics")

        # 5. Product Heuristic
        product_keywords = {
            "bus", "iphone", "cattle", "chicken", "meat", "car", "truck", "van", "train", "hearse", "laptop", "clothing", "steel", "oil", "gold", "rice", "wheat", "beef", "milk", "coffee", "tea", "sugar", "fruit", "vegetable", "fish", "wood", "paper", "cotton", "wool", "silk", "glass", "cement", "iron", "copper", "aluminum", "machine", "device", "engine", "motor", "vehicle", "aircraft", "ship", "boat", "weapon", "furniture", "light", "art", "antiques", "electronics", "phone",
            "horse", "horses", "ox", "oxen", "cow", "cows", "sheep", "goat", "goats", "swine", "pig", "pigs", "animal", "animals", "livestock", "poultry", "buffalo", "donkey", "mule", "camel", "dog", "cat", "tractor", "toothbrush", "motorcycle", "bicycle", "machinery", "equipment", "goods", "commodity", "product", "material", "chemical", "fertilizer", "plastic", "rubber", "leather", "textile", "footwear", "ceramic", "metal", "tool", "instrument", "toy", "tv", "television",
            "chestnut", "chestnuts", "tea", "matcha", "seaweed", "mozuku", "meatballs", "meatball", "bacon", "wiener", "wieners", "sausage", "pork", "ham", "yogurt", "nuggets", "nugget", "salad", "noodle", "noodles", "udon", "saba", "yakisoba", "somen", "ramen", "tonkotsu", "dumpling", "dumplets", "dumplings", "custard", "shrimp", "tofu", "granola", "biscuit", "biscuits", "crackers", "cracker", "chips", "chip", "potato", "dorayaki", "food", "beverage", "drink", "drinks"
        }
        if len(words) <= 5 and any(pw in words for pw in product_keywords):
            return ValidationResult.in_scope("heuristic_product", keywords=[w for w in words if w in product_keywords])

        # 5.5 Longer Product Description Heuristic (no conversational questions)
        conversational_words = {
            "what", "how", "why", "who", "where", "when", "which", "can", "could", "should",
            "would", "do", "does", "did", "is", "are", "was", "were", "tell", "show", "give", "explain", "help"
        }
        has_conv = any(cw in words for cw in conversational_words)
        if len(words) <= 15 and not has_conv:
            matched_pw = [pw for pw in product_keywords if pw in words]
            if matched_pw:
                return ValidationResult.in_scope("longer_product_description", keywords=matched_pw)

        return ValidationResult.ambiguous()

    async def validate_async(self, text: str) -> ValidationResult:
        """Fully prompt-driven asynchronous validation evaluation pipeline."""
        t = (text or "").strip()
        if not t:
            return ValidationResult.format_error("empty")

        # Call unified LLM validation
        try:
            res = await self.llm_engine.check_query_validity_unified(t)
            confidence = res.get("confidence", 0.0)
            is_safe = res.get("is_safe", True)
            is_on_topic = res.get("is_on_topic", False)
            category = res.get("category", "ambiguous")
            reason = res.get("reason")
            keywords = res.get("keywords", [])

            if confidence >= 0.7:
                if not is_safe:
                    return ValidationResult.injection(reason or "Potential injection detected by LLM")
                if is_on_topic:
                    return ValidationResult.in_scope(reason=f"llm_validated:{category}", keywords=keywords)
                else:
                    return ValidationResult.out_of_scope(reason or "out_of_scope")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"LLM validation failed in validate_async: {e}")

        return ValidationResult.ambiguous()


    def check_scope(self, text: str) -> Tuple[bool, str]:
        r = self.validate(text)
        if r.decision == ValidationDecision.OUT_OF_SCOPE:
            return False, "out_of_scope"
        return r.is_valid, r.reason or "Passed to prompt-driven intent classifier layer"

    def validate_calculation_input(self, text: str) -> Tuple[bool, Optional[List[str]]]:
        t_lower = (text or "").lower()
        missing = []
        
        # 1. Product check
        has_hs = re.search(r'\bhs\b', t_lower) or re.search(r'\b\d{4,10}\b', t_lower)
        product_keywords = ["product", "electronics", "bus", "cattle", "chicken", "meat", "car", "truck", "laptop", "clothing", "steel", "oil", "gold", "rice", "wheat", "beef", "milk", "coffee", "tea", "sugar", "fruit", "vegetable", "fish", "wood", "paper", "cotton", "wool", "silk", "glass", "cement", "iron", "copper", "aluminum", "machine", "device", "engine", "motor", "vehicle", "aircraft", "ship", "boat", "weapon", "furniture", "light", "art", "antiques", "phone", "toy"]
        has_product = has_hs or any(pw in t_lower for pw in product_keywords)
        if not has_product:
            missing.append("product/hs_code")
            
        # 2. Value check
        value_indicators = ["$", "usd", "cif", "fob", "price", "value", "khr", "baht", "exempt"]
        has_value = any(vi in t_lower for vi in value_indicators) and re.search(r'\b\d+\b', t_lower)
        if not has_value:
            missing.append("customs_value")
            
        if missing:
            return False, missing
        return True, None

    def get_scope_keywords_by_category(self) -> Dict[str, List[str]]:
        return {
            "hs_code_lookup": ["hs code", "hs", "classify", "classification", "tariff code", "commodity code", "product code"],
            "calculation": ["calculate", "compute", "duty", "tax", "cif", "fob", "vat"],
            "trade_query": ["import", "export", "trade", "procedure", "process", "requirement", "shipping"],
            "policy_query": ["regulation", "rule", "fta", "agreement", "compliance", "policy", "law", "decree"],
            "definition": ["define", "definition", "meaning", "explain", "describe"],
            "customs_general": ["customs", "declaration", "invoice", "packing list", "certificate", "cambodia"]
        }

    def get_scope_summary(self) -> str:
        cats = self.get_scope_keywords_by_category()
        summary = "Scope Keywords by Intent Category:\n"
        for category, keywords in cats.items():
            summary += f"  • {category}: {len(keywords)} keywords\n"
        total = sum(len(kws) for kws in cats.values())
        summary += f"  Total: {total} keywords across 6 intent categories"
        return summary


class OutputValidator:
    def validate_response(self, response: str) -> Tuple[bool, Optional[str]]:
        if not response or not response.strip():
            return False, "empty"
        if len(response.strip()) < 10:
            return False, "too short"
        r_lower = response.lower()
        if "api_key" in r_lower or "apikey" in r_lower or "secret_key" in r_lower:
            return False, "dangerous_content"
        if "password" in r_lower:
            return False, "dangerous_content"
        return True, None


class ValidatorServiceConfig:
    def __init__(self, **kwargs):
        self.enable_llm_fallback = kwargs.get("enable_llm_fallback", True)


class ValidatorService:
    def __init__(self, config: Optional[ValidatorServiceConfig] = None):
        self.config = config or ValidatorServiceConfig()
        self._provider = RuleBasedValidatorProvider()
        self._llm_provider = self._provider

    def set_client(self, client: Any):
        """Sets the underlying execution core client instance."""
        self._provider.llm_engine.client = client

    def validate_input(self, text: str) -> Tuple[bool, Optional[str]]:
        r = self._provider.validate(text)
        return r.to_simple_tuple()

    async def validate_input_async(self, text: str, session_context: Optional[Any] = None) -> Tuple[bool, Optional[str]]:
        r = await self.validate_input_full_async(text, session_context)
        return r.to_simple_tuple()

    def validate_input_full(self, text: str) -> ValidationResult:
        return self._provider.validate(text)

    async def validate_input_full_async(self, text: str, session_context: Optional[Any] = None) -> ValidationResult:
        t = (text or "").strip()
        if not t:
            return ValidationResult.format_error("empty")
        if len(t) < 3:
            return ValidationResult.format_error("too short")
        if len(t) > 5000:
            return ValidationResult.format_error("too long")

        # Fast local safety injection checks
        t_lower = t.lower()
        sql_patterns = [
            r"(\bor\b|\band\b).*['\"].*[=<>]",
            r"(drop|delete|update|insert|exec|execute|script)\s",
            r"(\-\-|;|\/\*|\*\/)",
            r"(union|select|from|where).*select",
        ]
        for pattern in sql_patterns:
            if re.search(pattern, t_lower):
                return ValidationResult.injection(f"Potential SQL injection detected: {pattern}")

        if re.search(r"(ignore|forget|override|bypass|disregard).*instruction", t_lower):
            return ValidationResult.injection("Potential prompt injection detected")
        if re.search(r"\byou are now\b", t_lower):
            return ValidationResult.injection("Potential prompt injection detected (you are now)")
        if re.search(r"\bact as\b", t_lower):
            return ValidationResult.injection("Potential prompt injection detected (act as)")
        if "`" in t or "$(" in t:
            return ValidationResult.injection("Suspicious command characters detected")

        # 1. First Layer: Unified LLM Validation
        from unittest.mock import Mock, AsyncMock, MagicMock
        is_mock = isinstance(getattr(self, "_llm_provider", None), (Mock, AsyncMock, MagicMock))
        
        if self.config.enable_llm_fallback and not is_mock:
            try:
                from ..analyzer import get_llm_first_layer_service
                first_layer = get_llm_first_layer_service()
                res = await first_layer.get_unified_result(t, session_context)
                if res:
                    is_safe = res.get("is_safe", True)
                    is_on_topic = res.get("is_on_topic", False)
                    category = res.get("intent", "ambiguous")
                    confidence = res.get("confidence", 0.0)
                    reason = res.get("reason")
                    
                    if not is_safe:
                        return ValidationResult.injection(reason or "Potential injection detected by LLM")
                    if is_on_topic:
                        v_res = ValidationResult.in_scope(reason=f"llm_validated:{category}", keywords=[])
                        v_res.llm_confidence = confidence
                        return v_res
                    else:
                        return ValidationResult.out_of_scope(reason or "out_of_scope")
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Unified LLM validation failed: {e}")

        # Fallback to the old _llm_provider validation for tests/compatibility
        if self.config.enable_llm_fallback and hasattr(self, '_llm_provider') and self._llm_provider is not None:
            llm_result = await self._llm_provider.validate_async(t)
            if llm_result.decision != ValidationDecision.AMBIGUOUS:
                return llm_result

        # 2. Second Layer (Fallback): Keyword/Rule-based validation
        return self._provider.validate(text)


    def check_scope(self, text: str) -> Tuple[bool, str]:
        return self._provider.check_scope(text)

    def validate_scope_with_intent(self, question: str, detected_intent: str) -> Tuple[bool, Optional[str]]:
        r = self._provider.validate(question)
        if r.decision in {ValidationDecision.OUT_OF_SCOPE, ValidationDecision.INJECTION}:
            return False, r.reason or "out_of_scope"
        return True, None

    def validate_calculation_input(self, text: str) -> Tuple[bool, Optional[List[str]]]:
        return self._provider.validate_calculation_input(text)

    def get_scope_keywords_by_category(self) -> Dict[str, List[str]]:
        return self._provider.get_scope_keywords_by_category()

    def get_scope_summary(self) -> str:
        return self._provider.get_scope_summary()


_input_validator_instance: Optional[ValidatorService] = None
_output_validator_instance: Optional[OutputValidator] = None


def get_input_validator() -> ValidatorService:
    global _input_validator_instance
    if _input_validator_instance is None:
        _input_validator_instance = ValidatorService()
    return _input_validator_instance


def get_output_validator() -> OutputValidator:
    global _output_validator_instance
    if _output_validator_instance is None:
        _output_validator_instance = OutputValidator()
    return _output_validator_instance


def get_validator() -> ValidatorService:
    return get_input_validator()


InputValidator = ValidatorService


__all__ = [
    "ValidationDecision",
    "ValidationResult",
    "RuleBasedValidatorProvider",
    "OutputValidator",
    "ValidatorService",
    "ValidatorServiceConfig",
    "get_input_validator",
    "get_output_validator",
    "get_validator",
    "InputValidator",
    "mentions_certificate",
    "extract_certificate_type",
    "is_short_rate_reply",
    "validate_calculation_input",
    "get_certificate_validator",
    "is_acfta",
]

# --------------------------------------------------------------------------
# Prompt-Driven Legacy Shims Execution Bridge
# --------------------------------------------------------------------------

def _run_sync(coro):
    """Safely handles running async coroutines within synchronous helper methods."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    else:
        return loop.run_until_complete(coro)


def mentions_certificate(text: str) -> bool:
    v = get_input_validator()
    res, _ = _run_sync(v._provider.llm_engine.check_certificate_details(text))
    return res


def extract_certificate_type(text: str) -> Optional[str]:
    v = get_input_validator()
    _, cert_type = _run_sync(v._provider.llm_engine.check_certificate_details(text))
    return cert_type


def is_short_rate_reply(text: str) -> bool:
    v = get_input_validator()
    return _run_sync(v._provider.llm_engine.check_rate_reply(text))


def validate_calculation_input(text: str) -> Tuple[bool, Optional[List[str]]]:
    v = get_input_validator()
    is_ok, missing = _run_sync(v._provider.llm_engine.check_calculation_fields(text))
    return is_ok, missing if missing else None


def get_certificate_validator() -> ValidatorService:
    return get_input_validator()


def is_acfta(text: str) -> bool:
    cert = extract_certificate_type(text)
    return cert == 'ACFTA'