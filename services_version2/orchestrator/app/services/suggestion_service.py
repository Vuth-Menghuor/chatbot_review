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
    """

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent.parent / "prompts" / "config" / "intent_adjacency.yaml"
        self.config_path = config_path
        self.intent_adjacency: Dict[str, List[Dict[str, str]]] = {}
        self.generic_fallbacks: List[str] = []
        self._load_config()

    def _load_config(self):
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if data:
                        raw_adjacency = data.get("intent_adjacency", {})
                        # Normalize keys and per-item "intent" values to lowercase/stripped
                        # so a case mismatch against the NLU classifier's output doesn't
                        # silently drop the whole lookup.
                        self.intent_adjacency = {
                            self._normalize_intent(k): [
                                {**item, "intent": self._normalize_intent(item.get("intent", ""))}
                                for item in v
                            ]
                            for k, v in raw_adjacency.items()
                        }
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
        session_context: Optional[Any] = None
    ) -> List[str]:
        """
        Generate a list of 2-3 structured suggestion strings.

        Args:
            current_intent: The NLU intent of the current query (e.g. 'hs_code_lookup').
            rewritten_query: The NLU-rewritten/cleaned query of the current turn.
            session_context: Optional active SessionContext to extract historic slots/entity.

        Returns:
            List of hydrated and filtered suggestion strings.
        """
        current_intent_norm = self._normalize_intent(current_intent)

        # 1. Resolve Entity: Extract from rewritten query, fallback to session memory.
        # Guard against non-string values from either source so a type mismatch
        # degrades gracefully instead of throwing inside .strip()/.format().
        entity = self._safe_str(extract_entity(rewritten_query))
        if not entity and session_context:
            entity = self._safe_str(getattr(session_context, "last_entity", None))

        # Strip commercial/price/country/assembly noise from the product name
        entity = self._clean_entity_noise(entity)

        # 2. Extract configuration mapping for current intent (already normalized at load time)
        adjacencies = self.intent_adjacency.get(current_intent_norm, [])

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

                if not is_similar_to_query_or_existing(hydrated):
                    suggestions.append(hydrated)

            # Top up from generic fallbacks if template filtering left us thin.
            # Ensures the user never sees a single lonely chip (or none) just
            # because filtering happened to strip most candidates this turn.
            if len(suggestions) < MIN_SUGGESTIONS:
                for fallback in self.generic_fallbacks:
                    if len(suggestions) >= MIN_SUGGESTIONS:
                        break
                    if not is_similar_to_query_or_existing(fallback):
                        suggestions.append(fallback)
        else:
            for fallback in self.generic_fallbacks:
                if not is_similar_to_query_or_existing(fallback):
                    suggestions.append(fallback)

        return suggestions[:MAX_SUGGESTIONS]

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
        """Strip commercial value, country, assembly keywords, and time expressions from product entity."""
        if not entity:
            return ""
        
        text = entity.strip().lower()
        
        # 1. Strip import value descriptions (e.g. "value 5000 usd", "valued at 5000 usd", "$5000")
        text = re.sub(r"\b(?:value|valued|worth)(?:\s+(?:at|of))?\s+\$?\d+(?:\s*(?:usd|khr|dollars|eur|cif))?\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+\s*(?:usd|khr|dollars|eur|cif)\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\$\d+\b", "", text)
        
        # 2. Strip origin/destination country patterns (e.g. "from China", "to Cambodia", "with Vietnam")
        text = re.sub(r"\b(?:from|to|with|into|out\s+of|originating\s+from)\s+[a-z]+(?:\s+[a-z]+)?\b", "", text, flags=re.IGNORECASE)
        
        # 3. Strip assembly mode keywords (e.g. "completely built unit", "completely knocked down", "ckd", "cbu")
        assembly_keywords = [
            r"\bcompletely\s+built\s+unit\b",
            r"\bcompletely\s+knocked\s+down\b",
            r"\bckd\b",
            r"\bcbu\b"
        ]
        for kw in assembly_keywords:
            text = re.sub(kw, "", text, flags=re.IGNORECASE)
            
        # 4. Strip year/time annotations (e.g. "in 2025", "for 2023")
        text = re.sub(r"\b(?:in|for|year|during)\s+\d{4}\b", "", text, flags=re.IGNORECASE)
        
        # Clean up trailing prepositions and duplicate spaces
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\b(?:for|on|of|at|about|and|with|to)\b\s*$", "", text).strip()
        text = re.sub(r"^[?!.,;:]+", "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        
        return text