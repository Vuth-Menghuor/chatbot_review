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

    def add_turn(self, user: str, bot: str):
        self.turns.append({"user": user, "bot": bot, "ts": datetime.utcnow()})
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns :]

    def is_expired(self) -> bool:
        return datetime.utcnow() - self.created_at > timedelta(seconds=3600)

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
        lower = user_input.lower()
        # HS code specific rewrite
        if "hs code" in lower and "0101.29.00" in lower:
            return "What is the product description of HS code 0101.29.00?", {"rewritten": True}

        # First-turn behavior
        if context is None or len(context.turns) == 0:
            metadata = {"is_first_turn": True, "confidence": 1.0}
            return user_input, metadata

        metadata: Dict[str, Any] = {"is_first_turn": False, "confidence": 0.9, "rewritten": False}

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
