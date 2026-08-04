from __future__ import annotations
from typing import Optional, Dict, Any, Tuple, List
import asyncio
import logging
import re

# Relative imports to support package execution in uvicorn
from .session_context import SessionContext, SessionManager, Topic
from ..utils import extract_entity

logger = logging.getLogger(__name__)

# Generic slot vocabulary — see extract_context_updates() for how these are
# used. No fixed sentence templates: entities are pulled from anywhere in
# the text, regardless of phrasing.

# These are lookup tables 

TRADE_PARTNER_COUNTRIES = [
    "thailand", "laos", "vietnam", "china", "myanmar", "singapore",
    "malaysia", "indonesia", "philippines", "japan", "korea", "cambodia",
]

PRODUCT_KEYWORDS = [
    "rice", "boat", "car", "laptop", "bus", "motor", "motorcycle",
    "textile", "rubber", "phone", "computer", "furniture", "garment",
]

CIF_PATTERN = re.compile(r"\$?\s?([\d,]+(?:\.\d+)?)\s*(usd|khr|thb|eur)?", re.IGNORECASE)
HS_CODE_PATTERN = re.compile(r"\b\d{4}\.\d{2}(?:\.\d{2})?\b")

TRACKED_FIELDS = [
    "import_export_mode", "product_category", "commercial_description",
    "origin_country", "destination_country", "hs_code", "cif_value",
    "currency", "year", "month", "trade_agreement",
]

# What each intent needs to be considered "complete." No entry / unknown
# intent means "always treat as resolved" — just build best-effort from
# whatever context exists.
REQUIRED_FIELDS_BY_INTENT: Dict[str, List[str]] = {
    "hs_code_lookup": ["product_category"],
    "calculation": ["product_category", "cif_value"],
    "trade_query": [],  # Trade parameters are dynamic (country, time period, mode, commodity, or overall trade stats)
}


def extract_context_updates(query: str) -> Dict[str, Any]:
    """Pulls whatever slot values are present in the raw text, independent of sentence structure, it reads text and returns facts"""
    q = query.lower()
    updates: Dict[str, Any] = {}

    # 1. Country Extraction (Origin vs Destination)
    countries_found = [c for c in TRADE_PARTNER_COUNTRIES if c in q]
    from_match = re.search(r"\bfrom\s+([a-zA-Z]+)\b", q)
    to_match = re.search(r"\bto\s+([a-zA-Z]+)\b", q)
    
    if from_match and from_match.group(1) in TRADE_PARTNER_COUNTRIES:
        updates["origin_country"] = from_match.group(1).title()
    if to_match and to_match.group(1) in TRADE_PARTNER_COUNTRIES:
        updates["destination_country"] = to_match.group(1).title()
        
    # Fallbacks if no explicit "from/to" prefix was used:
    for c in countries_found:
        c_title = c.title()
        if "origin_country" not in updates and c_title != updates.get("destination_country"):
            updates["origin_country"] = c_title
        elif "destination_country" not in updates and c_title != updates.get("origin_country"):
            updates["destination_country"] = c_title

    # 2. Product Category and Commercial Description
    product_found = [p for p in PRODUCT_KEYWORDS if p in q]
    if product_found:
        updates["product_category"] = product_found[0]
    
    entity = extract_entity(query)
    if entity:
        if "product_category" not in updates:
            updates["product_category"] = entity
        updates["commercial_description"] = entity

    # 3. HS Code
    hs_match = HS_CODE_PATTERN.search(query)
    if hs_match:
        updates["hs_code"] = hs_match.group()

    # 4. CIF Value & Currency
    cif_match = CIF_PATTERN.search(query)
    if cif_match and cif_match.group(1) and ("$" in query or "cif" in q or "cost" in q or "value" in q):
        try:
            updates["cif_value"] = float(cif_match.group(1).replace(",", ""))
        except ValueError:
            pass
        if cif_match.group(2):
            updates["currency"] = cif_match.group(2).upper()

    # 5. Import/Export Mode
    if re.search(r"\bexport(?:ing|ed)?\b", q):
        updates["import_export_mode"] = "export"
    elif re.search(r"\bimport(?:ing|ed)?\b", q):
        updates["import_export_mode"] = "import"

    # 6. Year
    year_match = re.search(r"\b(20\d{2})\b", q)
    if year_match:
        updates["year"] = year_match.group(1)

    # 7. Month
    months = [
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"
    ]
    found_month = [m for m in months if m in q]
    if found_month:
        updates["month"] = found_month[0].title()

    # 8. Trade Agreement
    trade_agreements = ["atiga", "rcep", "acfta", "ccfta", "ajcep", "aanzfta", "aifta", "akfta", "asean"]
    found_ta = [ta for ta in trade_agreements if ta in q]
    if found_ta:
        updates["trade_agreement"] = found_ta[0].upper()

    return updates


def build_rewrite_from_context(user_input: str, intent: Optional[str], context: SessionContext) -> str:
    """Builds a standalone rewritten query from the session's current tracked fields."""
    mode = context.import_export_mode or "import"
    product = context.product_category or ""
    origin = f" from {context.origin_country}" if context.origin_country else ""
    destination = f" to {context.destination_country}" if context.destination_country else ""
    cif = f" CIF {context.currency or 'USD'} {context.cif_value}" if context.cif_value else ""
    hs = f" (HS code {context.hs_code})" if context.hs_code else ""
    desc = f" ({context.commercial_description})" if context.commercial_description and context.commercial_description != product else ""
    ta = f" under {context.trade_agreement}" if context.trade_agreement else ""
    year = f" in {context.year}" if context.year else ""
    month = f" for {context.month}" if context.month else ""

    if intent == "hs_code_lookup":
        return f"HS code for {product}{desc}".strip()
    if intent == "calculation":
        return f"calculate {mode} duty for {product}{desc}{cif}{origin}{ta}".strip()
    if intent == "trade_query":
        return f"{mode} value for {product}{origin}{destination}{year}{month}".strip()

    enriched = f"{mode} {product}{desc}{origin}{destination}{cif}{hs}{ta}{year}{month}".strip()
    return enriched if product else user_input


class InputRewriter:
    """
    Single-tier, deterministic rewriter — no LLM ask-back.

    1. Extract slots from the current raw input, merge onto session state
       (works regardless of phrasing — see extract_context_updates).
    2. If that's enough to satisfy the intent's required fields, build the
       rewrite from context and clear the fragment buffer.
    3. If not, append the raw input to `context.pending_fragments`, re-run
       extraction over the *merged* fragment text (catches cases like a CIF
       value split across turns: "the cost is" / "$2000"), and check again.
    4. If still incomplete after the merge, return the merged raw fragments
       as the best-effort rewrite — no clarifying question is asked, no LLM
       call is made. The next turn's fragment gets appended on top of this
       same buffer until something resolves.
    """

    def __init__(
        self,
        request_timeout_seconds: float = 8.0,
        ollama_host: Optional[str] = None,
        model: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        gemini_model: Optional[str] = None,
    ):
        import os
        self.request_timeout_seconds = request_timeout_seconds
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST")
        self.model = model or os.getenv("OLLAMA_MODEL")
        self.gemini_api_key = gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.gemini_model = gemini_model or os.getenv("GEMINI_MODEL")
        self._closed = False

        # Initialize Gemini provider (primary rewriter)
        self._gemini: Optional[Any] = None
        try:
            from ..ai.providers.gemini import GeminiProvider
            self._gemini = GeminiProvider(
                api_key=self.gemini_api_key,
                model=self.gemini_model,
                timeout=int(request_timeout_seconds),
            )
            if not self._gemini.is_available():
                self._gemini = None
                logger.info("Gemini provider not available — will fall back to Ollama for rewriting.")
        except Exception as e:
            logger.warning(f"Could not initialize Gemini provider: {e}")
            self._gemini = None

        from prompts.dynamic_prompt_manager import DynamicPromptManager
        self.prompt_manager = DynamicPromptManager()

    async def close(self):
        self._closed = True
        await asyncio.sleep(0)

    async def rewrite_input(
        self,
        user_input: str,
        context: Optional[SessionContext] = None,
        intent: Optional[str] = None,
        intent_hint: Optional[str] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        # Handle keyword argument alias compatibility
        active_intent = intent or intent_hint
        lower = user_input.lower()
        metadata: Dict[str, Any] = {
            "is_first_turn": False,
            "confidence": 0.9,
            "rewritten": False,
            "tier": "slot",
            "intent_changed": False,
        }

        # Deterministic parse, not phrasing-dependent — kept as-is.
        hs_match = re.search(r"\bhs\s*code\s*([\d\.]+)", lower)
        if hs_match and "refer" in lower:
            hs_code = hs_match.group(1)
            rewritten = f"What is the product description of HS code {hs_code}?"
            metadata["rewritten"] = True
            return rewritten, metadata

        if context is None or len(context.turns) == 0:
            metadata = {"is_first_turn": True, "confidence": 1.0, "tier": "slot", "intent_changed": False}
            return user_input, metadata

        # --- Fast-path gate: skip LLM if deterministic resolution is sufficient ---
        fast_updates = extract_context_updates(user_input)

        # Capture previous values BEFORE applying updates (needed for intent_changed detection)
        prev_mode = context.import_export_mode

        for field, value in fast_updates.items():
            setattr(context, field, value)

        fast_missing = self._missing_fields(active_intent, context)
        if not fast_missing:
            # Detect mode/intent switch
            if prev_mode and "import_export_mode" in fast_updates:
                if fast_updates["import_export_mode"] != prev_mode:
                    metadata["intent_changed"] = True
            if active_intent and context.last_intent and active_intent != context.last_intent:
                metadata["intent_changed"] = True

            # All slots satisfied — build deterministically (0ms)
            rewritten = build_rewrite_from_context(user_input, active_intent, context)
            if rewritten.strip() != user_input.strip():
                metadata["rewritten"] = True
            metadata["confidence"] = 0.9
            metadata["slots_updated"] = list(fast_updates.keys())
            if fast_updates:
                context._trigger_change()
            context.pending_fragments = []
            return rewritten, metadata

        # LLM is needed when regex extracted nothing from the current input —
        # meaning the query is a contextual reference ("the old one", "same thing",
        # "what about it") that only the LLM can resolve using rolling_summary + history.
        # If regex did find slots (product, country, year, etc.) the deterministic
        # path below handles it without an LLM call.
        needs_llm = len(fast_updates) == 0

        # Try LLM Rewrite: Gemini (primary) → Ollama (fallback)
        if needs_llm and not self._closed:
            import json
            # Build shared prompt inputs
            history_lines = []
            for turn in (context.turns or [])[-5:]:
                user_val = turn.get("user", "")
                bot_val = turn.get("bot", "")
                history_lines.append(f"User: {user_val}\nAssistant: {bot_val}")
            history_str = "\n".join(history_lines)

            slots_dict = {
                "import_export_mode": context.import_export_mode,
                "product_category": context.product_category,
                "origin_country": context.origin_country,
                "destination_country": context.destination_country,
                "hs_code": context.hs_code,
                "cif_value": context.cif_value,
                "currency": context.currency,
                "year": context.year,
                "month": context.month,
                "trade_agreement": context.trade_agreement,
            }
            slots_str = json.dumps({k: v for k, v in slots_dict.items() if v is not None})

            rewritten_text: Optional[str] = None
            provider_used: str = "none"

            # --- Primary: Gemini ---
            if self._gemini and self._gemini.is_available():
                try:
                    rewritten_text, _ = await self._gemini.rewrite_input(
                        user_input,
                        context=context,
                        intent_hint=active_intent,
                    )
                    provider_used = "gemini"
                    logger.debug("Rewrite via Gemini.")
                except Exception as e:
                    logger.warning(f"Gemini rewrite failed, falling back to Ollama: {e}")

            # --- Fallback: Ollama ---
            if rewritten_text is None and self.ollama_host:
                try:
                    import httpx
                    system_prompt = self.prompt_manager.render(
                        "gemini_rewrite_input",
                        history=history_str,
                        rolling_summary=context.rolling_summary,
                        context=slots_str,
                        user_input=user_input,
                    )
                    async with httpx.AsyncClient(timeout=self.request_timeout_seconds) as client:
                        response = await client.post(
                            f"{self.ollama_host}/api/generate",
                            json={"model": self.model or "llama3.2:3b", "prompt": system_prompt, "stream": False},
                        )
                        if response.status_code == 200:
                            raw = response.json().get("response", "").strip()
                            # Strip surrounding quotes if LLM added them
                            if len(raw) > 1 and raw[0] in ('"', "'") and raw[0] == raw[-1]:
                                raw = raw[1:-1].strip()
                            rewritten_text = raw or None
                            provider_used = "ollama"
                            logger.debug("Rewrite via Ollama fallback.")
                except Exception as e:
                    logger.warning(f"Ollama rewrite failed: {e}")

            if rewritten_text:
                # Sync any newly mentioned slots from the LLM-handled turn
                slot_updates = extract_context_updates(user_input)
                for field, value in slot_updates.items():
                    setattr(context, field, value)
                if slot_updates:
                    context._trigger_change()

                metadata["rewritten"] = rewritten_text.lower() != user_input.lower()
                metadata["tier"] = f"llm_{provider_used}"
                metadata["confidence"] = 0.95
                return rewritten_text, metadata

        # --- Step 1: extract + merge from the current turn alone ---
        updates = extract_context_updates(user_input)

        # Detect switch in mode or intent (required by test suite)
        if context.import_export_mode and "import_export_mode" in updates:
            if updates["import_export_mode"] != context.import_export_mode:
                metadata["intent_changed"] = True
        if active_intent and context.last_intent and active_intent != context.last_intent:
            metadata["intent_changed"] = True

        for field, value in updates.items():
            setattr(context, field, value)
        metadata["slots_updated"] = list(updates.keys())
        if updates:
            context._trigger_change()

        missing = self._missing_fields(active_intent, context)

        if not missing:
            rewritten = build_rewrite_from_context(user_input, active_intent, context)
            if rewritten.strip() != user_input.strip():
                metadata["rewritten"] = True
            metadata["confidence"] = 0.9 if updates else 0.6
            context.pending_fragments = []  # resolved — clear any prior unresolved fragments
            return rewritten, metadata

        # --- Step 2: still missing something — merge with accumulated
        # fragments instead of asking the user to clarify ---
        context.pending_fragments.append(user_input)
        merged_text = " ".join(context.pending_fragments)

        merged_updates = extract_context_updates(merged_text)
        for field, value in merged_updates.items():
            setattr(context, field, value)
        if merged_updates:
            metadata["slots_updated"] = list(set(metadata["slots_updated"] + list(merged_updates.keys())))
        
        # Save updates to slot states and pending fragment buffer
        context._trigger_change()

        missing_after_merge = self._missing_fields(active_intent, context)
        metadata["fragment_buffer"] = list(context.pending_fragments)

        if not missing_after_merge:
            rewritten = build_rewrite_from_context(user_input, active_intent, context)
            metadata["rewritten"] = True
            metadata["tier"] = "merged"
            metadata["confidence"] = 0.85
            context.pending_fragments = []  # resolved — clear buffer for the next sequence
            return rewritten, metadata

        # Still incomplete — return the merged fragments as the best-effort
        # query. No clarifying question, no LLM call. The buffer stays for
        # the next turn to build on.
        metadata["tier"] = "merged_partial"
        metadata["confidence"] = 0.4
        metadata["missing_fields"] = missing_after_merge
        return merged_text, metadata

    def _missing_fields(self, intent: Optional[str], context: SessionContext) -> List[str]:
        if not intent or intent not in REQUIRED_FIELDS_BY_INTENT:
            return []
        return [f for f in REQUIRED_FIELDS_BY_INTENT[intent] if not getattr(context, f, None)]