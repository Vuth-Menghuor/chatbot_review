import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.infrastructure.models import (
    ChatSession,
    ChatMessage,
    SessionContextModel,
    IntentRoute,
    ServiceCall,
    ConversationSummary,
    ChatFeedback,
    ChatAttachment,
    FailedRequest,
    ModelUsageLog,
)

logger = logging.getLogger(__name__)

# Synchronous Database Operations

def sync_get_or_create_session(db: Session, session_id: str, user_id: Optional[str] = None, project_id: Optional[str] = None) -> ChatSession:
    """Self-replicating function to get or create a chat session."""
    stmt = insert(ChatSession).values(
        session_id=session_id,
        user_id=user_id,
        project_id=project_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    ).on_conflict_do_nothing(index_elements=['session_id'])
    db.execute(stmt)
    db.commit()
    return db.query(ChatSession).filter_by(session_id=session_id).first()


def sync_save_chat_message(db: Session, session_id: str, role: str, content: str) -> ChatMessage:
    """Saves a message into the chat_messages table and returns the message model."""
    # Ensure session exists
    sync_get_or_create_session(db, session_id)
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        created_at=datetime.utcnow()
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def sync_save_session_context(db: Session, session_id: str, context_data: Dict[str, Any]) -> SessionContextModel:
    """Upserts session context using ON CONFLICT DO UPDATE."""
    stmt = insert(SessionContextModel).values(
        session_id=session_id,
        context_data=context_data,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=['session_id'],
        set_={
            'context_data': stmt.excluded.context_data,
            'updated_at': datetime.utcnow()
        }
    )
    db.execute(stmt)
    db.commit()
    return db.query(SessionContextModel).filter_by(session_id=session_id).first()


def sync_save_intent_route(db: Session, session_id: str, message_id: Optional[int], intent: str, service: str, confidence: Optional[float] = None) -> IntentRoute:
    """Saves route and intent details."""
    route = IntentRoute(
        session_id=session_id,
        message_id=message_id,
        detected_intent=intent,
        selected_service=service,
        confidence=confidence,
        created_at=datetime.utcnow()
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


def sync_save_service_call(db: Session, session_id: str, service_name: str, request_payload: Optional[Dict[str, Any]], response_payload: Optional[Dict[str, Any]], latency_ms: Optional[float], status: str) -> ServiceCall:
    """Logs downstream service requests/responses."""
    call = ServiceCall(
        session_id=session_id,
        service_name=service_name,
        request_payload=request_payload,
        response_payload=response_payload,
        latency_ms=latency_ms,
        status=status,
        created_at=datetime.utcnow()
    )
    db.add(call)
    db.commit()
    db.refresh(call)
    return call


def sync_save_conversation_summary(db: Session, session_id: str, summary: str, last_message_index: int) -> ConversationSummary:
    """Upserts rolling conversation summary using ON CONFLICT (session_id, last_message_index) DO UPDATE."""
    stmt = insert(ConversationSummary).values(
        session_id=session_id,
        summary=summary,
        last_message_index=last_message_index,
        created_at=datetime.utcnow()
    )
    stmt = stmt.on_conflict_do_update(
        constraint='uq_session_summary_index',
        set_={
            'summary': stmt.excluded.summary
        }
    )
    db.execute(stmt)
    db.commit()
    return db.query(ConversationSummary).filter_by(session_id=session_id, last_message_index=last_message_index).first()


def sync_save_failed_request(db: Session, session_id: str, service_name: str, error_message: str, error_type: Optional[str] = None, request_payload: Optional[Dict[str, Any]] = None) -> FailedRequest:
    """Logs fallback failures or service call errors."""
    failed = FailedRequest(
        session_id=session_id,
        service_name=service_name,
        error_message=error_message,
        error_type=error_type,
        request_payload=request_payload,
        created_at=datetime.utcnow()
    )
    db.add(failed)
    db.commit()
    db.refresh(failed)
    return failed


def sync_save_model_usage(db: Session, session_id: str, model_name: str, prompt_tokens: Optional[int], completion_tokens: Optional[int], total_tokens: Optional[int], cost: Optional[float] = None, message_id: Optional[int] = None) -> ModelUsageLog:
    """Logs token usage and cost for LLM calls."""
    usage = ModelUsageLog(
        session_id=session_id,
        message_id=message_id,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost=cost,
        created_at=datetime.utcnow()
    )
    db.add(usage)
    db.commit()
    db.refresh(usage)
    return usage


def sync_save_chat_feedback(db: Session, session_id: str, rating: int, comment: Optional[str] = None, message_id: Optional[int] = None) -> ChatFeedback:
    """Saves user rating and comment feedback."""
    feedback = ChatFeedback(
        session_id=session_id,
        message_id=message_id,
        rating=rating,
        comment=comment,
        created_at=datetime.utcnow()
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def sync_save_chat_attachment(db: Session, session_id: str, file_id: str, file_name: Optional[str] = None, file_url: Optional[str] = None, message_id: Optional[int] = None) -> ChatAttachment:
    """Links uploaded files to a session or message."""
    attachment = ChatAttachment(
        session_id=session_id,
        message_id=message_id,
        file_id=file_id,
        file_name=file_name,
        file_url=file_url,
        created_at=datetime.utcnow()
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


# Asynchronous thread-safe wrappers for use in Orchestrator v2

class ChatbotDBService:
    """Service class executing DB operations in threads to prevent blocking the async loop."""
    
    # Synchronous DB operations exposed for direct with-block executions
    sync_get_or_create_session = staticmethod(sync_get_or_create_session)
    sync_save_chat_message = staticmethod(sync_save_chat_message)
    sync_save_session_context = staticmethod(sync_save_session_context)
    sync_save_intent_route = staticmethod(sync_save_intent_route)
    sync_save_service_call = staticmethod(sync_save_service_call)
    sync_save_conversation_summary = staticmethod(sync_save_conversation_summary)
    sync_save_failed_request = staticmethod(sync_save_failed_request)
    sync_save_model_usage = staticmethod(sync_save_model_usage)
    sync_save_chat_feedback = staticmethod(sync_save_chat_feedback)
    sync_save_chat_attachment = staticmethod(sync_save_chat_attachment)
    
    @staticmethod
    async def get_or_create_session(db: Session, session_id: str, user_id: Optional[str] = None, project_id: Optional[str] = None) -> ChatSession:
        return await asyncio.to_thread(sync_get_or_create_session, db, session_id, user_id, project_id)
        
    @staticmethod
    async def save_chat_message(db: Session, session_id: str, role: str, content: str) -> ChatMessage:
        return await asyncio.to_thread(sync_save_chat_message, db, session_id, role, content)
        
    @staticmethod
    async def save_session_context(db: Session, session_id: str, context_data: Dict[str, Any]) -> SessionContextModel:
        return await asyncio.to_thread(sync_save_session_context, db, session_id, context_data)
        
    @staticmethod
    async def save_intent_route(db: Session, session_id: str, message_id: Optional[int], intent: str, service: str, confidence: Optional[float] = None) -> IntentRoute:
        return await asyncio.to_thread(sync_save_intent_route, db, session_id, message_id, intent, service, confidence)
        
    @staticmethod
    async def save_service_call(db: Session, session_id: str, service_name: str, request_payload: Optional[Dict[str, Any]], response_payload: Optional[Dict[str, Any]], latency_ms: Optional[float], status: str) -> ServiceCall:
        return await asyncio.to_thread(sync_save_service_call, db, session_id, service_name, request_payload, response_payload, latency_ms, status)
        
    @staticmethod
    async def save_conversation_summary(db: Session, session_id: str, summary: str, last_message_index: int) -> ConversationSummary:
        return await asyncio.to_thread(sync_save_conversation_summary, db, session_id, summary, last_message_index)
        
    @staticmethod
    async def save_failed_request(db: Session, session_id: str, service_name: str, error_message: str, error_type: Optional[str] = None, request_payload: Optional[Dict[str, Any]] = None) -> FailedRequest:
        return await asyncio.to_thread(sync_save_failed_request, db, session_id, service_name, error_message, error_type, request_payload)
        
    @staticmethod
    async def save_model_usage(db: Session, session_id: str, model_name: str, prompt_tokens: Optional[int], completion_tokens: Optional[int], total_tokens: Optional[int], cost: Optional[float] = None, message_id: Optional[int] = None) -> ModelUsageLog:
        return await asyncio.to_thread(sync_save_model_usage, db, session_id, model_name, prompt_tokens, completion_tokens, total_tokens, cost, message_id)
        
    @staticmethod
    async def save_chat_feedback(db: Session, session_id: str, rating: int, comment: Optional[str] = None, message_id: Optional[int] = None) -> ChatFeedback:
        return await asyncio.to_thread(sync_save_chat_feedback, db, session_id, rating, comment, message_id)
        
    @staticmethod
    async def save_chat_attachment(db: Session, session_id: str, file_id: str, file_name: Optional[str] = None, file_url: Optional[str] = None, message_id: Optional[int] = None) -> ChatAttachment:
        return await asyncio.to_thread(sync_save_chat_attachment, db, session_id, file_id, file_name, file_url, message_id)
