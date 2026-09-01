import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml

from ..utils import extract_entity

logger = logging.getLogger(__name__)

MIN_SUGGESTIONS = 2
MAX_SUGGESTIONS = 3


class SuggestionService:
    """
    Suggestion Service for generating follow-up suggestion chips.
    Matches current intent to adjacent intents defined in YAML mapping,
    and hydrates them with the extracted product entity.
    Supports localized templates for English and Khmer.
    """

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent.parent / "prompts" / "config" / "intent_adjacency.yaml"
        self.config_path = config_path
        self.intent_adjacency: Dict[str, Any] = {}
        self.generic_fallbacks: Any = []
        self._load_config()

    def _load_config(self):
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        raw_adjacency = data.get("intent_adjacency", {})
                        # Normalize keys while preserving nested language structure
                        normalized_adj = {}
                        for k, v in raw_adjacency.items():
                            norm_k = self._normalize_intent(k)
                            if isinstance(v, dict):
                                normalized_adj[norm_k] = {
                                    lang: [
                                        {**item, "intent": self._normalize_intent(item.get("intent", ""))}
                                        for item in items
                                    ] if isinstance(items, list) else []
                                    for lang, items in v.items()
                                }
                            elif isinstance(v, list):
                                normalized_adj[norm_k] = [
                                    {**item, "intent": self._normalize_intent(item.get("intent", ""))}
                                    for item in v
                                ]
                        self.intent_adjacency = normalized_adj
                        self.generic_fallbacks = data.get("generic_fallbacks", [])
                logger.info(f"Loaded intent adjacency config from {self.config_path}")
            else:
                logger.warning(f"Adjacency config file not found at {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load intent adjacency config: {e}")

    def get_suggestions(
        self,
        current_intent: str,
        rewritten_query: str,
        session_context: Optional[Any] = None,
        language: str = "en",
        result_payload: Optional[Dict[str, Any]] = None,
        nlu_entity: Optional[str] = None,
        has_nlu_entity: bool = False,
    ) -> List[str]:
        """
        Generate a list of 2-3 structured suggestion strings.

        Args:
            current_intent: The NLU intent of the current query (e.g. 'hs_code_lookup').
            rewritten_query: The NLU-rewritten/cleaned query of the current turn.
            session_context: Optional active SessionContext to extract historic slots/entity.
            language: Resolved language code ('en' or 'km').
            result_payload: Optional execution payload from calculation/retrieval/trade services.

        Returns:
            List of hydrated and filtered suggestion strings in target language.
        """
        current_intent_norm = self._normalize_intent(current_intent)

        # 1. Resolve Entity: Try LLM-extracted entity first if available.
        # If the LLM successfully evaluated the query but found no entity (has_nlu_entity=True, nlu_entity=None),
        # we trust this decision and do NOT fall back to regex.
        # We only fall back to regex if has_nlu_entity is False (e.g. LLM failed, or Ollama fallback).
        if has_nlu_entity:
            entity = self._safe_str(nlu_entity)
            entity = self._clean_entity_noise(entity) if entity else ""
        else:
            entity = self._safe_str(extract_entity(rewritten_query))
            entity = self._clean_entity_noise(entity)

        if not entity and result_payload:
            entity = self._safe_str(self._extract_entity_from_result(result_payload))
            entity = self._clean_entity_noise(entity)

        if not entity and rewritten_query:
            hs_match = re.search(r"\b\d{4}\.\d{2}(?:\.\d{2})?\b", rewritten_query)
            if hs_match and not result_payload:
                entity = hs_match.group(0)

        if not entity and session_context:
            entity = self._safe_str(getattr(session_context, "last_entity", None))
            entity = self._clean_entity_noise(entity)

        # Sync resolved valid entity back to session memory if available
        if entity and session_context and hasattr(session_context, "last_entity"):
            session_context.last_entity = entity

        # 2. Resolve Language Templates
        target_lang = language.strip().lower() if language and isinstance(language, str) else "en"
        if target_lang not in ("en", "km"):
            target_lang = "en"

        raw_adj = self.intent_adjacency.get(current_intent_norm, {})
        if isinstance(raw_adj, dict):
            adjacencies = raw_adj.get(target_lang) or raw_adj.get("en") or []
        elif isinstance(raw_adj, list):
            adjacencies = raw_adj
        else:
            adjacencies = []

        if isinstance(self.generic_fallbacks, dict):
            fallbacks = self.generic_fallbacks.get(target_lang) or self.generic_fallbacks.get("en") or []
        elif isinstance(self.generic_fallbacks, list):
            fallbacks = self.generic_fallbacks
        else:
            fallbacks = []

        suggestions: List[str] = []
        normalized_query = self._normalize_text(rewritten_query)

        def is_similar_to_query_or_existing(text: str) -> bool:
            norm_text = self._normalize_text(text)
            if norm_text == normalized_query:
                return True
            return any(self._normalize_text(existing) == norm_text for existing in suggestions)

        if entity and adjacencies:
            styled_entity = entity.strip()
            for adj in adjacencies:
                if adj.get("intent") == current_intent_norm:
                    continue

                template = adj.get("text", "")
                if not template:
                    continue

                try:
                    hydrated = template.format(entity=styled_entity)
                except Exception as e:
                    logger.warning(f"Failed to format suggestion template '{template}' with entity '{styled_entity}': {e}")
                    continue

                if not is_similar_to_query_or_existing(hydrated) and self._is_valid_chip_for_lang(hydrated, target_lang):
                    suggestions.append(hydrated)

            if len(suggestions) < MIN_SUGGESTIONS:
                for fallback in fallbacks:
                    if len(suggestions) >= MIN_SUGGESTIONS:
                        break
                    if not is_similar_to_query_or_existing(fallback) and self._is_valid_chip_for_lang(fallback, target_lang):
                        suggestions.append(fallback)
        else:
            for fallback in fallbacks:
                if not is_similar_to_query_or_existing(fallback) and self._is_valid_chip_for_lang(fallback, target_lang):
                    suggestions.append(fallback)

        return suggestions[:MAX_SUGGESTIONS]

    def _extract_entity_from_result(self, result_payload: Dict[str, Any]) -> Optional[str]:
        """Extract product description or entity from service calculation/retrieval result payload."""
        if not isinstance(result_payload, dict):
            return None

        # Direct payload attributes
        for key in ("product_name", "commercial_description", "product_category", "entity"):
            val = result_payload.get(key)
            if isinstance(val, str) and val.strip():
                cleaned = self._clean_entity_noise(val)
                if cleaned:
                    return cleaned

        # Check formatted answer text fields for "PRODUCT INFORMATION: * HS Code: 8703.22.00 (General merchandise)"
        for ans_key in ("answer", "human_readable", "formatted_answer", "final_answer", "message"):
            ans_text = result_payload.get(ans_key)
            if isinstance(ans_text, str) and ans_text.strip():
                match = re.search(r"(?:HS|AHTN)\s*Code\s*:\s*[\d\.]+\s*\(([^)]+)\)", ans_text, re.IGNORECASE)
                if match:
                    extracted = match.group(1).strip()
                    cleaned = self._clean_entity_noise(extracted)
                    if cleaned:
                        return cleaned

        # Calculation assumptions list (e.g. "+ Product: General merchandise")
        assumptions = result_payload.get("assumptions")
        if isinstance(assumptions, list):
            for item in assumptions:
                if isinstance(item, str):
                    match = re.search(r"(?:^\s*\+?\s*)?product\s*:\s*(.+)", item, re.IGNORECASE)
                    if match:
                        extracted = match.group(1).strip().split("\n")[0].strip()
                        cleaned = self._clean_entity_noise(extracted)
                        if cleaned:
                            return cleaned

        # Check line items if available
        line_items = result_payload.get("line_items")
        if isinstance(line_items, list) and len(line_items) > 0:
            first = line_items[0]
            if isinstance(first, dict):
                desc = first.get("description") or first.get("name")
                if isinstance(desc, str) and desc.strip():
                    cleaned = self._clean_entity_noise(desc)
                    if cleaned:
                        return cleaned

        return None

    def _is_valid_chip_for_lang(self, chip: str, target_lang: str) -> bool:
        if not chip:
            return False
        # Reject chips with math operators or parameter key noise
        if "=" in chip or "cif=" in chip.lower() or "dv=" in chip.lower() or "pls —" in chip.lower():
            return False
        if target_lang == "km":
            has_khmer_script = bool(re.search(r"[\u1780-\u17FF]", chip))
            is_pure_alphanumeric_code = bool(re.match(r"^[0-9\.\s\$\#\-\:\,A-Za-z]+$", chip.strip()))
            return has_khmer_script or is_pure_alphanumeric_code
        return True

    @staticmethod
    def _safe_str(value: Any) -> str:
        """Coerce a resolved entity value to a plain string, or '' if unusable."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        logger.warning(f"Expected str entity value, got {type(value).__name__}: {value!r}")
        return ""

    @staticmethod
    def _normalize_intent(intent: str) -> str:
        if not intent or not isinstance(intent, str):
            return ""
        return intent.strip().lower()

    def _normalize_text(self, text: str) -> str:
        """Strip, lowercase, and collapse whitespace for normalized similarity check."""
        if not text:
            return ""
        return re.sub(r"\s+", " ", text.strip().lower())

    def _clean_entity_noise(self, entity: str) -> str:
        """Strip commercial value, country, assembly keywords, parameter math, and noise tokens from product entity."""
        if not entity:
            return ""
        
        raw_original = entity.strip()
        text = raw_original.lower()
        
        # 0. Strip structured key-value label prefixes from user-structured input.
        # e.g. "product name: bwm m8 competition; engine size: over 1600 cc, type: sport car"
        # Strip each semicolon-delimited field that starts with a label: the label + colon is removed,
        # leaving only the value portion. Then apply step-by-step noise removal to the remainder.
        # Handles both colon-delimited ("key: value") and semicolon-separated segments.
        # Step 0a: strip explicit key-label prefixes (product name:, engine size:, type:, etc.)
        text = re.sub(
            r"\b(?:product\s+name|engine\s+size|engine\s+type|body\s+type|vehicle\s+type|type|name|size|model|brand)\s*[:=]\s*",
            "", text, flags=re.IGNORECASE
        )
        # Step 0b: strip semicolon/comma-separated trailing specification segments
        # e.g. "; engine size: 1600cc" or ", type: sport car"
        text = re.sub(
            r"[;,]\s*(?:engine\s+size|engine|type|size|model|cc|cylinder|displacement)\b[^,;]*",
            "", text, flags=re.IGNORECASE
        )
        # Step 0c: strip specification suffixes that describe properties rather than the product name
        # e.g. "over 1600 cc", "below 3000 cc", "1600cc", "sport car" when standalone
        text = re.sub(r"\b(?:over|below|under|above|around|approximately|approx)\s+\d+\s*(?:cc|cm3)?\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+\s*(?:cc|cm3)\b", "", text, flags=re.IGNORECASE)

        # 1. Strip key-value parameters (e.g. "cif=40000usd", "dv=0", "dq 40%", "cif 5000", "cif $40,000")
        text = re.sub(r"\b(?:cif|fob|cif_value|dv|dq)\s*[:=]?\s*\$?\d[\d,.]*(?:\s*(?:usd|khr|dollars|eur|cif))?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:dq|dv|cif)\s+\d+(?:%|\s*usd|\s*khr)?\b", "", text, flags=re.IGNORECASE)

        # 2. Strip import value descriptions (e.g. "value 5000 usd", "valued at 5000 usd", "$5000", "$40,000.00")
        text = re.sub(r"\b(?:value|valued|worth)(?:\s+(?:at|of))?\s+\$?\d[\d,.]*(?:\s*(?:usd|khr|dollars|eur|cif))?\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:usd|khr|dollars|eur|cif)\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\$\d{1,3}(?:,\d{3})*(?:\.\d+)?\b", "", text)
        
        # 3. Strip origin/destination country patterns and standalone country names
        text = re.sub(r"\b(?:from|to|with|into|out\s+of|originating\s+from)\s+[a-z]+(?:\s+[a-z]+)?\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b(?:china|cambodia|vietnam|usa|us|thailand|japan|korea|laos|singapore|malaysia|germany|france|uk|india|indonesia|philippines|cn)\b", "", text, flags=re.IGNORECASE)
        
        # 4. Strip HS code prefix annotations (e.g. "hs 8703.24.00", "hs code 8703.24")
        text = re.sub(r"\bhs\s*(?:code\s*)?\d{4}\.\d{2}(?:\.\d{2})?\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bhs\b", "", text, flags=re.IGNORECASE)

        # 5. Strip assembly mode keywords, percentage rates (e.g. 0%), & specific query rewrite noise
        text = re.sub(r"\s*\d+%", "", text)
        noise_patterns = [
            r"\bcompletely\s+built\s+unit\b",
            r"\bcompletely\s+knocked\s+down\b",
            r"\bckd\b",
            r"\bcbu\b",
            r"\b(?:cif|fob|cif_value|acfta|atiga|rcep|duty\s+rate|duty|tax|rate|value|latest|dv|dq|pls|please|import|export|need|calc|calculate|calculator|can|could|you|u|compute)\b"
        ]
        for pattern in noise_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # 6. Strip symbols like em-dashes, equals signs, math operators
        text = re.sub(r"[—–=\+\*\#\:\,\;\/]", " ", text)

        # 7. Strip Khmer noise tokens with symmetric boundary checking using space-padded capture groups
        padded_text = f" {text} "
        km_noise_tokens = [
            "អំពី", "សម្រាប់", "ពន្ធ", "នាំចូល", "នាំចេញ", "អត្រា", "តម្លៃ", "កូដ", "គណនា", "ពី", "តាម", "គិត", "ទំនិញ", "ប៉ុន្មាន"
        ]
        for token in km_noise_tokens:
            km_pattern = r'(\s)' + re.escape(token) + r'(\s|[$#\d\(\)\[\]]|$)'
            padded_text = re.sub(km_pattern, r'\1\2', padded_text, flags=re.UNICODE)
        text = padded_text.strip()
            
        # 8. Strip year/time annotations (e.g. "in 2025", "for 2023")
        text = re.sub(r"\b(?:in|for|year|during)\s+\d{4}\b", "", text, flags=re.IGNORECASE)
        
        # Clean up dangling prepositions, symbols, and duplicate spaces
        text = re.sub(r"[\s,]+", " ", text).strip()
        text = re.sub(r"\b(?:for|on|of|at|about|and|with|to|in|under|pls|please)\b\s*$", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"^[?!.,;:\-—–=]+", "", text).strip()
        text = re.sub(r"[?!.,;:\-—–=]+$", "", text).strip()

        # 9. Strip common question/conversational noise words and digits
        conversational_words = {
            "what", "is", "are", "it", "its", "with", "engine", "around", "about", "how", "do", "does", "did",
            "tell", "me", "show", "find", "get", "look", "up", "code", "hs", "for", "on", "of", "to",
            "in", "under", "a", "an", "the", "some", "any", "which", "where", "who", "whom", "whose",
            "why", "can", "could", "would", "should", "will", "shall", "please", "pls", "thank", "thanks",
            "hello", "hi", "hey", "goodbye", "bye", "ok", "okay", "yes", "no", "not", "but", "or", "and",
            "if", "then", "else", "correct", "right", "wrong", "use", "using", "try", "look", "search",
            "give", "defined", "definition", "policy", "procedure", "cc",
            # Structured-query label residues (e.g. from "product name: X; size: Y; type: Z" inputs)
            "product", "name", "size", "type", "over", "below", "above", "sport", "car",
        }
        words = text.split()
        words = [w for w in words if w not in conversational_words and not w.isdigit()]
        text = " ".join(words).strip()

        # Reject entity if what remains contains no letters and is not an HS code, or is purely numeric/symbols/residual noise
        has_letters = bool(re.search(r"[a-zA-Z\u1780-\u17FF]", text))
        is_hs_code = bool(re.search(r"\d{4}\.\d{2}", text))
        if (not has_letters and not is_hs_code) or len(text) < 3 or text in {"pls", "please", "dv", "dq", "cif", "need", "calc"}:
            return ""

        # If the cleaned text matches the lowercased original entity (or cleaned version), preserve casing if original had title/mixed casing
        if text == raw_original.lower():
            return raw_original
        return text