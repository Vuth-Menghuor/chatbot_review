from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
import asyncio


class Topic(str, Enum):
    UNKNOWN = "unknown"
    HS_LOOKUP = "hs_lookup"
    PRODUCT_CATEGORY = "product_category"


@dataclass
class SessionContext:
    session_id: str
    turns: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    max_turns: int = 5
    import_export_mode: Optional[str] = None
    product_category: Optional[str] = None
    product_category_km: Optional[str] = None
    currency: Optional[str] = None
    current_topic: Topic = Topic.UNKNOWN
    
    # Clarification/ask-back session state
    pending_clarification: bool = False
    clarification_intents: List[str] = field(default_factory=list)
    pending_rewritten_query: Optional[str] = None
    ask_back_count: int = 0

    # ------------------------------------------------------------------ #
    # Turn-to-turn state (required for two-turn rewriting / ask-back)     #
    # ------------------------------------------------------------------ #
    # Intent value string (e.g. "hs_code_lookup") from the previous turn
    last_intent: Optional[str] = None

    # Core subject entity extracted from the previous turn's query
    # (e.g. "car" from "what is the hs code of car?").
    # Populated via utils.extract_entity() – kept as a pure field, no logic here.
    last_entity: Optional[str] = None

    # The raw user text from the previous turn BEFORE HS-code standardization.
    # Kept for audit/logging purposes only.  Do NOT use for entity merging.
    last_raw_query: Optional[str] = None

    # The query text from the previous turn AFTER HS-code standardization.
    # This is what _merge_pending_with_clarification should read for entity
    # fallback, because it is the canonical form that was actually processed.
    last_normalized_query: Optional[str] = None

    def add_turn(self, user: str = "", bot: str = "", user_input: str = "", bot_response: str = ""):
        user_val = user or user_input
        bot_val = bot or bot_response
        self.turns.append({"user": user_val, "bot": bot_val, "ts": datetime.utcnow()})
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

    def is_expired(self) -> bool:
        return datetime.utcnow() - self.created_at > timedelta(seconds=3600)

    def is_awaiting_clarification(self) -> bool:
        return self.pending_clarification

    def set_pending_clarification(self, candidate_intents: List[str], rewritten_query: Optional[str]):
        self.pending_clarification = True
        self.clarification_intents = candidate_intents
        self.pending_rewritten_query = rewritten_query
        self.ask_back_count += 1

    def resolve_clarification(self, resolved_intent: str) -> Optional[str]:
        query = self.pending_rewritten_query
        self.pending_clarification = False
        self.clarification_intents = []
        self.pending_rewritten_query = None
        self.ask_back_count = 0
        return query

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "product_category": self.product_category,
            "import_export_mode": self.import_export_mode,
            "turns": self.turns,
        }


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, SessionContext] = {}

    def get_or_create_session(self, session_id: str) -> SessionContext:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionContext(session_id=session_id)
        return self._sessions[session_id]

    def update_session_context(self, session_id: str, **kwargs):
        session = self.get_or_create_session(session_id)
        for k, v in kwargs.items():
            if hasattr(session, k):
                setattr(session, k, v)


class InputRewriter:
    def __init__(self, ollama_host: str = "http://localhost:11434", model: str = "default"):
        self.ollama_host = ollama_host
        self.model = model
        self._closed = False

    async def close(self):
        self._closed = True
        await asyncio.sleep(0)

    async def rewrite_input(self, user_input: str, context: Optional[SessionContext] = None) -> Tuple[str, Dict[str, Any]]:
        import re
        lower = user_input.lower()
        metadata: Dict[str, Any] = {"is_first_turn": False, "confidence": 0.9, "rewritten": False}

        # Rule: HS code description lookup check (needs to run first, even without context)
        hs_match = re.search(r"\bhs\s*code\s*([\d\.]+)", lower)
        if hs_match and "refer" in lower:
            hs_code = hs_match.group(1)
            rewritten = f"What is the product description of HS code {hs_code}?"
            metadata["rewritten"] = True
            return rewritten, metadata

        # First-turn behavior
        if context is None or len(context.turns) == 0:
            metadata = {"is_first_turn": True, "confidence": 1.0}
            return user_input, metadata

        # Followup product switch: "how/what about X" where X is a product
        followup_match = re.match(r"^(?:how|what)\s+about\s+([\w\s]+)", lower)
        if followup_match and context and context.import_export_mode:
            product = followup_match.group(1).strip()
            product = re.sub(r"[^\w\s]", "", product).strip()
            if product and product not in ("export", "import"):
                rewritten = f"{context.import_export_mode} {product}"
                metadata["rewritten"] = True
                return rewritten, metadata

        # Import/export switch detection
        if "export" in lower and context.import_export_mode == "import":
            rewritten = f"export {context.product_category or ''} {user_input}"
            metadata["intent_changed"] = True
            metadata["rewritten"] = True
            return rewritten, metadata

        # Ambiguous followup expansion: include product_category or import
        if any(tok in lower for tok in ("value", "higher", "lower", "more")) and context.product_category:
            rewritten = f"import {context.product_category} {user_input}"
            metadata["rewritten"] = True
            return rewritten, metadata

        # Default: return input with minor metadata
        return user_input, metadata
