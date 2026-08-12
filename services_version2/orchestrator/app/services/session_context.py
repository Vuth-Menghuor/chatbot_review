from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Callable
import logging
import json
import asyncio

# Try importing redis defensively to support offline environments without dependencies
try:
    # pyrefly: ignore [missing-import]
    import redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)


class Topic(str, Enum):
    UNKNOWN = "unknown"
    HS_LOOKUP = "hs_lookup"
    PRODUCT_CATEGORY = "product_category"


@dataclass
class SessionContext:
    session_id: str
    user_id: str = "default_user"  # stable user identity across sessions
    turns: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    max_turns: int = 8
    import_export_mode: Optional[str] = None
    product_category: Optional[str] = None
    product_category_km: Optional[str] = None
    currency: Optional[str] = None
    current_topic: Topic = Topic.UNKNOWN

    # --- Extended slots (were missing — needed for calculation/trade_query
    #     intents beyond just import/export switching) ---
    origin_country: Optional[str] = None
    destination_country: Optional[str] = None
    hs_code: Optional[str] = None
    cif_value: Optional[float] = None
    commercial_description: Optional[str] = None
    year: Optional[str] = None
    month: Optional[str] = None
    trade_agreement: Optional[str] = None

    # --- Rolling summary of turns evicted past max_turns ---
    rolling_summary: str = ""

    # --- Unresolved fragment buffer ---
    pending_fragments: List[str] = field(default_factory=list)

    # Clarification/ask-back session state (intent ambiguity)
    pending_clarification: bool = False
    clarification_intents: List[str] = field(default_factory=list)
    pending_rewritten_query: Optional[str] = None
    ask_back_count: int = 0

    # Product-spec clarification state machine                            
    # Tracks mid-conversation spec follow-up (e.g. "BMW m8" → "sports")  
    # Mutually exclusive with pending_clarification (intent ask-back)     
    product_clarification_needed: bool = False
    clarification_entity: Optional[str] = None        # Saved product entity from turn 1
    clarification_last_query: Optional[str] = None    # Original turn-1 raw input
    product_ask_back_count: int = 0                   # Number of spec follow-ups so far
    clarification_expected_terms: List[str] = field(default_factory=list)  # Dynamic vocab from retrieval questions
    clarification_candidate_codes: List[str] = field(default_factory=list)  # Top HS candidates from unresolved lookup

    # Sequential slot-collection state for calculation intent.
    # Stores {"missing": ["hs_code"|"cif_value"], "original_query": str}
    # while the bot is asking the user for mandatory fields one at a time.
    calc_slot_collection: Optional[Dict[str, Any]] = None

    # Turn-to-turn state (required for two-turn rewriting / ask-back)     
    last_intent: Optional[str] = None
    last_entity: Optional[str] = None
    last_raw_query: Optional[str] = None
    last_normalized_query: Optional[str] = None

    # Multi-turn language state machine
    target_language: str = "en"
    is_language_pinned: bool = False

    # Track total turns count for exact database summary index referencing
    total_turns_count: int = 0

    # Private callbacks (not serialized)
    _on_change: Optional[Callable[[], None]] = field(default=None, repr=False, compare=False)
    _on_turns_evicted: Optional[Callable[[List[Dict[str, Any]]], None]] = field(
        default=None, repr=False, compare=False
    )

    def _trigger_change(self):
        if self._on_change is not None:
            self._on_change()

    def add_turn(self, user: str = "", bot: str = "", user_input: str = "", bot_response: str = ""):
        user_val = user or user_input
        bot_val = bot or bot_response
        self.turns.append({"user": user_val, "bot": bot_val, "ts": datetime.utcnow()})
        self.total_turns_count += 1

        if len(self.turns) > self.max_turns:
            overflow_count = len(self.turns) - self.max_turns
            evicted = self.turns[:overflow_count]
            self.turns = self.turns[overflow_count:]

            if self._on_turns_evicted is not None:
                self._on_turns_evicted(evicted)
            else:
                fallback_text = " | ".join(
                    f"U:{t.get('user', '')} B:{t.get('bot', '')}" for t in evicted
                )
                self.rolling_summary = (self.rolling_summary + " " + fallback_text).strip()[-1600:]

        self._trigger_change()

    def clear_context_slots(self):
        """Clears all short-term conversation slots to prevent topic pollution."""
        self.import_export_mode = None
        self.product_category = None
        self.product_category_km = None
        self.currency = None
        self.origin_country = None
        self.destination_country = None
        self.hs_code = None
        self.cif_value = None
        self.commercial_description = None
        self.year = None
        self.month = None
        self.trade_agreement = None
        self.last_entity = None  # Clear specific entity on topic switch
        self.clarification_candidate_codes = []
        self._trigger_change()

    def is_expired(self) -> bool:
        return datetime.utcnow() - self.created_at > timedelta(seconds=3600)

    def is_awaiting_clarification(self) -> bool:
        return self.pending_clarification

    def set_pending_clarification(self, candidate_intents: List[str], rewritten_query: Optional[str]):
        self.pending_clarification = True
        self.clarification_intents = candidate_intents
        self.pending_rewritten_query = rewritten_query
        self.ask_back_count += 1
        self._trigger_change()

    def resolve_clarification(self, resolved_intent: str) -> Optional[str]:
        query = self.pending_rewritten_query
        self.last_intent = resolved_intent
        self.pending_clarification = False
        self.clarification_intents = []
        self.pending_rewritten_query = None
        self.ask_back_count = 0
        self._trigger_change()
        return query

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "turns": [
                {
                    "user": turn.get("user", ""),
                    "bot": turn.get("bot", ""),
                    "ts": turn["ts"].isoformat() if isinstance(turn.get("ts"), datetime) else turn.get("ts"),
                }
                for turn in self.turns
            ],
            "created_at": self.created_at.isoformat(),
            "max_turns": self.max_turns,
            "import_export_mode": self.import_export_mode,
            "product_category": self.product_category,
            "product_category_km": self.product_category_km,
            "currency": self.currency,
            "current_topic": self.current_topic.value,
            "origin_country": self.origin_country,
            "destination_country": self.destination_country,
            "hs_code": self.hs_code,
            "cif_value": self.cif_value,
            "commercial_description": self.commercial_description,
            "year": self.year,
            "month": self.month,
            "trade_agreement": self.trade_agreement,
            "rolling_summary": self.rolling_summary,
            "pending_fragments": self.pending_fragments,
            "pending_clarification": self.pending_clarification,
            "clarification_intents": self.clarification_intents,
            "pending_rewritten_query": self.pending_rewritten_query,
            "ask_back_count": self.ask_back_count,
            # Product-spec clarification state
            "product_clarification_needed": self.product_clarification_needed,
            "clarification_entity": self.clarification_entity,
            "clarification_last_query": self.clarification_last_query,
            "product_ask_back_count": self.product_ask_back_count,
            "clarification_expected_terms": self.clarification_expected_terms,
            "clarification_candidate_codes": self.clarification_candidate_codes,
            "last_intent": self.last_intent,
            "last_entity": self.last_entity,
            "last_raw_query": self.last_raw_query,
            "last_normalized_query": self.last_normalized_query,
            "target_language": self.target_language,
            "is_language_pinned": self.is_language_pinned,
            "total_turns_count": self.total_turns_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContext":
        created_at = datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow()
        turns = []
        for turn in data.get("turns", []):
            ts_val = turn.get("ts")
            if ts_val:
                try:
                    ts_val = datetime.fromisoformat(ts_val)
                except ValueError:
                    ts_val = datetime.utcnow()
            else:
                ts_val = datetime.utcnow()
            turns.append({
                "user": turn.get("user", ""),
                "bot": turn.get("bot", ""),
                "ts": ts_val
            })

        try:
            current_topic = Topic(data.get("current_topic", "unknown"))
        except ValueError:
            current_topic = Topic.UNKNOWN

        return cls(
            session_id=data["session_id"],
            user_id=data.get("user_id", "default_user"),
            turns=turns,
            created_at=created_at,
            max_turns=data.get("max_turns", 5),
            import_export_mode=data.get("import_export_mode"),
            product_category=data.get("product_category"),
            product_category_km=data.get("product_category_km"),
            currency=data.get("currency"),
            current_topic=current_topic,
            origin_country=data.get("origin_country"),
            destination_country=data.get("destination_country"),
            hs_code=data.get("hs_code"),
            cif_value=data.get("cif_value"),
            commercial_description=data.get("commercial_description"),
            year=data.get("year"),
            month=data.get("month"),
            trade_agreement=data.get("trade_agreement"),
            rolling_summary=data.get("rolling_summary", ""),
            pending_fragments=data.get("pending_fragments", []),
            pending_clarification=data.get("pending_clarification", False),
            clarification_intents=data.get("clarification_intents", []),
            pending_rewritten_query=data.get("pending_rewritten_query"),
            ask_back_count=data.get("ask_back_count", 0),
            # Product-spec clarification state
            product_clarification_needed=data.get("product_clarification_needed", False),
            clarification_entity=data.get("clarification_entity"),
            clarification_last_query=data.get("clarification_last_query"),
            product_ask_back_count=data.get("product_ask_back_count", 0),
            clarification_expected_terms=data.get("clarification_expected_terms", []),
            clarification_candidate_codes=data.get("clarification_candidate_codes", []),
            last_intent=data.get("last_intent"),
            last_entity=data.get("last_entity"),
            last_raw_query=data.get("last_raw_query"),
            last_normalized_query=data.get("last_normalized_query"),
            target_language=data.get("target_language", "en"),
            is_language_pinned=data.get("is_language_pinned", False),
            total_turns_count=data.get("total_turns_count", 0),
        )


class SessionManager:
    def __init__(self):
        import os
        import time
        from pathlib import Path
        self._sessions: Dict[str, SessionContext] = {}
        self._store_dir = Path(__file__).resolve().parent.parent / "session_store"
        self._store_dir.mkdir(parents=True, exist_ok=True)

        # Optional Redis Client initialization
        self.redis_client = None
        self._redis_online = False
        self._last_redis_check = time.time()
        if redis is not None:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_password = os.getenv("REDIS_PASSWORD")
            if redis_password == "":
                redis_password = None
            try:
                self.redis_client = redis.Redis(
                    host=redis_host, 
                    port=redis_port, 
                    password=redis_password,
                    decode_responses=True,
                    # Short connection/socket timeouts to prevent blocking request threads
                    socket_timeout=1.0,
                    socket_connect_timeout=1.0
                )
                self.redis_client.ping()
                self._redis_online = True
                logger.info(f"SessionManager connected to Redis (host: {redis_host}:{redis_port})")
            except Exception as e:
                self._redis_online = False
                logger.warning(f"Initial Redis connection check failed, keeping client active for subsequent retries: {e}")

    def _check_redis_online(self) -> bool:
        import time
        if self.redis_client is None:
            return False
        if self._redis_online:
            return True
            
        # Only retry connection check after a 30 seconds cooldown to prevent blocking request threads
        now = time.time()
        if now - self._last_redis_check > 30:
            self._last_redis_check = now
            try:
                self.redis_client.ping()
                self._redis_online = True
                logger.info("Redis has re-connected successfully.")
                return True
            except Exception:
                self._redis_online = False
        return False

    def _get_file_path(self, session_id: str):
        import re
        from pathlib import Path
        safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", session_id)
        return self._store_dir / f"{safe_id}.json"

    def _schedule_summarization(self, session: SessionContext, evicted_turns: List[Dict[str, Any]]):
        """Schedules asynchronous LLM rolling summarization task on the active event loop."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(async_summarize_evicted_turns(session, evicted_turns))
        except RuntimeError:
            # Fallback if no event loop is running (e.g. in synchronous tests)
            logger.warning("No running event loop found to run async_summarize_evicted_turns, executing synchronously")
            try:
                # Create a temporary loop to run the async task
                loop = asyncio.new_event_loop()
                loop.run_until_complete(async_summarize_evicted_turns(session, evicted_turns))
                loop.close()
            except Exception as ex:
                logger.error(f"Failed to execute summarization synchronously: {ex}")
                fallback_summary(session, evicted_turns)

    def get_or_create_session(self, session_id: str) -> SessionContext:
        if session_id in self._sessions:
            return self._sessions[session_id]

        # Try loading from Redis first
        if self._check_redis_online():
            try:
                raw = self.redis_client.get(f"session:{session_id}:context")
                if raw:
                    data = json.loads(raw)
                    session = SessionContext.from_dict(data)
                    session._on_change = lambda: self._save_session(session)
                    session._on_turns_evicted = lambda evicted: self._schedule_summarization(session, evicted)
                    session._streamed_count = len(session.turns)
                    self._sessions[session_id] = session
                    return session
            except Exception as e:
                logger.error(f"Failed to load session {session_id} from Redis: {e}")
                self._redis_online = False
                import time
                self._last_redis_check = time.time()

        # Fallback to local files
        file_path = self._get_file_path(session_id)
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                session = SessionContext.from_dict(data)
                session._on_change = lambda: self._save_session(session)
                session._on_turns_evicted = lambda evicted: self._schedule_summarization(session, evicted)
                session._streamed_count = len(session.turns)
                self._sessions[session_id] = session
                return session
            except Exception as e:
                logger.error(f"Failed to load session {session_id} from disk: {e}")

        session = SessionContext(session_id=session_id)
        session._on_change = lambda: self._save_session(session)
        session._on_turns_evicted = lambda evicted: self._schedule_summarization(session, evicted)
        session._streamed_count = 0
        self._sessions[session_id] = session
        self._save_session(session)
        return session

    def get_session_readonly(self, session_id: str) -> Optional[SessionContext]:
        if session_id in self._sessions:
            return self._sessions[session_id]

        if self._check_redis_online():
            try:
                raw = self.redis_client.get(f"session:{session_id}:context")
                if raw:
                    data = json.loads(raw)
                    session = SessionContext.from_dict(data)
                    session._on_change = lambda: self._save_session(session)
                    session._on_turns_evicted = lambda evicted: self._schedule_summarization(session, evicted)
                    session._streamed_count = len(session.turns)
                    self._sessions[session_id] = session
                    return session
            except Exception:
                pass

        file_path = self._get_file_path(session_id)
        if file_path.exists():
            try:
                with open(file_path, "r") as f:
                    data = json.load(f)
                session = SessionContext.from_dict(data)
                session._on_change = lambda: self._save_session(session)
                session._on_turns_evicted = lambda evicted: self._schedule_summarization(session, evicted)
                session._streamed_count = len(session.turns)
                self._sessions[session_id] = session
                return session
            except Exception:
                pass

        return None

    def update_session_context(self, session_id: str, **kwargs):
        session = self.get_or_create_session(session_id)
        for k, v in kwargs.items():
            if hasattr(session, k):
                setattr(session, k, v)
        self._save_session(session)

    def _save_session(self, session: SessionContext):
        # 1. Save to local disk backup
        try:
            file_path = self._get_file_path(session.session_id)
            data = session.to_dict()
            temp_file = file_path.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(data, f)
            temp_file.replace(file_path)
            self._sessions[session.session_id] = session
        except Exception as e:
            logger.error(f"Failed to save session {session.session_id} to disk: {e}")

        # 2. Save to Redis context and stream transcript if Redis is live
        if self._check_redis_online():
            try:
                self.redis_client.set(
                    f"session:{session.session_id}:context",
                    json.dumps(session.to_dict()),
                    ex=3600  # 1 hour expiration
                )

                if not hasattr(session, "_streamed_count"):
                    session._streamed_count = 0

                # XADD any new turns to the Redis stream transcript
                new_turns = session.turns[session._streamed_count:]
                for turn in new_turns:
                    user_val = turn.get("user") or turn.get("user_input", "")
                    bot_val = turn.get("bot") or turn.get("bot_response", "")
                    ts_val = turn.get("ts")
                    ts_str = ts_val.isoformat() if isinstance(ts_val, datetime) else str(ts_val or datetime.utcnow())

                    self.redis_client.xadd(
                        f"session:{session.session_id}:transcript",
                        {
                            "role": "user",
                            "content": user_val,
                            "ts": ts_str,
                        }
                    )
                    self.redis_client.xadd(
                        f"session:{session.session_id}:transcript",
                        {
                            "role": "assistant",
                            "content": bot_val,
                            "ts": ts_str,
                        }
                    )
                session._streamed_count = len(session.turns)
            except Exception as e:
                logger.error(f"Failed to save session {session.session_id} to Redis: {e}")
                self._redis_online = False
                import time
                self._last_redis_check = time.time()


# PostgreSQL Archiving & Querying Routines (Draft/Reference Implementation)
# Skip calling these until PostgreSQL connection config is live.

def flush_session_to_pg(session_id: str, user_id: str, redis_conn, pg_conn, keep_last_n: int = 20):
    """
    Flushes older Redis Stream transcript logs to Postgres and trims the Redis tail.
    To use this, wire a background cron/APScheduler worker to invoke it.
    """
    if redis_conn is None or pg_conn is None:
        return

    stream_key = f"session:{session_id}:transcript"
    try:
        entries = redis_conn.xrange(stream_key)  # [(entry_id, {field: value}), ...]
        if len(entries) <= keep_last_n:
            return  # Nothing old enough to flush yet

        to_flush = entries[:-keep_last_n]  # Keep the hot tail in memory

        with pg_conn.cursor() as cur:
            for entry_id, fields in to_flush:
                cur.execute(
                    """INSERT INTO transcript_archive
                       (user_id, session_id, redis_entry_id, role, content, ts)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (user_id, session_id, entry_id, fields["role"], fields["content"], fields["ts"]),
                )
        pg_conn.commit()  # Confirm write BEFORE trimming Redis stream

        last_flushed_id = to_flush[-1][0]
        redis_conn.xtrim(stream_key, minid=last_flushed_id, approximate=False)
        logger.info(f"Flushed {len(to_flush)} transcript entries for session {session_id} to Postgres")
    except Exception as e:
        logger.error(f"Failed to flush stream {session_id} to Postgres: {e}")


def get_user_history(pg_conn, user_id: str, limit: int = 200) -> List[tuple]:
    """Retrieves full chat history across all sessions for a stable user identity."""
    if pg_conn is None:
        return []
    try:
        with pg_conn.cursor() as cur:
            cur.execute(
                """SELECT session_id, role, content, ts FROM transcript_archive
                   WHERE user_id = %s ORDER BY ts DESC LIMIT %s""",
                (user_id, limit),
            )
            return cur.fetchall()
    except Exception as e:
        logger.error(f"Failed to query user history for {user_id}: {e}")
        return []


async def async_summarize_evicted_turns(session: SessionContext, evicted_turns: List[Dict[str, Any]]):
    """
    Constructs prompting context containing current summary and newly evicted turns,
    invokes the Gemini provider to generate a cohesive updated summary,
    updates session.rolling_summary, triggers session._trigger_change(), and saves to DB.
    """
    try:
        from ..ai import get_llm_first_layer_service
        first_layer = get_llm_first_layer_service()
        llm_service = first_layer._get_llm_service()
        gemini_provider = llm_service.router.providers.get("gemini")
        if not gemini_provider or not gemini_provider.is_available():
            logger.warning("Gemini provider not available for rolling summarization, using fallback summary formatting")
            fallback_summary(session, evicted_turns)
            return

        # Format evicted turns
        evicted_text = "\n".join(
            f"User: {t.get('user', '')}\nAssistant: {t.get('bot', '')}"
            for t in evicted_turns
        )

        # Render prompt
        prompt = gemini_provider.prompt_manager.render(
            "summarize_evicted_turns",
            rolling_summary=session.rolling_summary,
            evicted_turns=evicted_text
        )

        # Call Gemini
        response = await asyncio.to_thread(
            gemini_provider.client.models.generate_content,
            model=gemini_provider.model_name,
            contents=prompt
        )

        new_summary = (response.text or "").strip()
        if new_summary:
            session.rolling_summary = new_summary
            logger.info(f"Successfully generated rolling summary for session {session.session_id}")
            session._trigger_change()

            # Save updated rolling summary to DB using context session
            try:
                from app.infrastructure.database import get_db_context
                from app.services.db_service import ChatbotDBService
                last_msg_idx = getattr(session, "total_turns_count", 0)
                with get_db_context() as db:
                    await ChatbotDBService.save_conversation_summary(
                        db=db,
                        session_id=session.session_id,
                        summary=session.rolling_summary,
                        last_message_index=last_msg_idx
                    )
            except Exception as db_err:
                logger.error(f"Failed to save rolling summary to database: {db_err}")

    except Exception as e:
        logger.error(f"Error in async_summarize_evicted_turns: {e}", exc_info=True)
        # Log failed summarization request to DB
        try:
            from app.infrastructure.database import get_db_context
            from app.services.db_service import sync_save_failed_request
            with get_db_context() as db:
                sync_save_failed_request(
                    db=db,
                    session_id=session.session_id,
                    service_name="rolling_summarizer",
                    error_message=str(e),
                    error_type=type(e).__name__
                )
        except Exception as db_err:
            logger.error(f"Failed to log rolling_summarizer error to DB: {db_err}")

        # Fallback to local deterministic formatting
        fallback_summary(session, evicted_turns)


def fallback_summary(session: SessionContext, evicted_turns: List[Dict[str, Any]]):
    """Fallback rolling summarizer that slices cleanly on turn boundaries and saves to DB."""
    fallback_text = " | ".join(
        f"U:{t.get('user', '')} B:{t.get('bot', '')}" for t in evicted_turns
    )
    combined = (session.rolling_summary + " | " + fallback_text).strip(" | ")
    
    # Slicing cleanly on turn boundary if length exceeds 1600 chars
    if len(combined) > 1600:
        truncated = combined[-1600:]
        sep_index = truncated.find(" | ")
        if sep_index != -1:
            session.rolling_summary = truncated[sep_index + 3:].strip()
        else:
            session.rolling_summary = truncated.strip()
    else:
        session.rolling_summary = combined

    session._trigger_change()

    # Save fallback summary to DB using context session
    try:
        from app.infrastructure.database import get_db_context
        from app.services.db_service import sync_save_conversation_summary
        last_msg_idx = getattr(session, "total_turns_count", 0)
        with get_db_context() as db:
            sync_save_conversation_summary(
                db=db,
                session_id=session.session_id,
                summary=session.rolling_summary,
                last_message_index=last_msg_idx
            )
    except Exception as db_err:
        logger.error(f"Failed to save fallback rolling summary to database: {db_err}")

