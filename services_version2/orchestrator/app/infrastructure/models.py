from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    ForeignKey,
    Text,
    Float,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from .database import Base


class ChatSession(Base):
    __tablename__ = 'chat_sessions'

    session_id = Column(String(255), primary_key=True, index=True)
    user_id = Column(String(255), nullable=True, index=True)
    project_id = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships with DB-level ON DELETE CASCADE
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)
    context = relationship("SessionContextModel", back_populates="session", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    routes = relationship("IntentRoute", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)
    service_calls = relationship("ServiceCall", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)
    summaries = relationship("ConversationSummary", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)
    feedback = relationship("ChatFeedback", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)
    attachments = relationship("ChatAttachment", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)
    failed_requests = relationship("FailedRequest", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)
    model_usage_logs = relationship("ModelUsageLog", back_populates="session", cascade="all, delete-orphan", passive_deletes=True)


class ChatMessage(Base):
    __tablename__ = 'chat_messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")
    routes = relationship("IntentRoute", back_populates="message", cascade="all, delete-orphan", passive_deletes=True)
    feedback = relationship("ChatFeedback", back_populates="message", cascade="all, delete-orphan", passive_deletes=True)
    attachments = relationship("ChatAttachment", back_populates="message", cascade="all, delete-orphan", passive_deletes=True)
    model_usage_logs = relationship("ModelUsageLog", back_populates="message", cascade="all, delete-orphan", passive_deletes=True)


class SessionContextModel(Base):
    __tablename__ = 'session_contexts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.session_id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    context_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    session = relationship("ChatSession", back_populates="context")


class IntentRoute(Base):
    __tablename__ = 'intent_routes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey('chat_messages.id', ondelete='SET NULL'), nullable=True)
    detected_intent = Column(String(100), nullable=False)
    selected_service = Column(String(100), nullable=False)
    confidence = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    session = relationship("ChatSession", back_populates="routes")
    message = relationship("ChatMessage", back_populates="routes")


class ServiceCall(Base):
    __tablename__ = 'service_calls'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)
    service_name = Column(String(100), nullable=False, index=True)
    request_payload = Column(JSON, nullable=True)
    response_payload = Column(JSON, nullable=True)
    latency_ms = Column(Float, nullable=True)
    status = Column(String(50), nullable=False)  # 'success' or 'failed'
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    session = relationship("ChatSession", back_populates="service_calls")


class ConversationSummary(Base):
    __tablename__ = 'conversation_summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)
    summary = Column(Text, nullable=False)
    last_message_index = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Unique constraint to prevent race conditions on concurrent evictions
    __table_args__ = (
        UniqueConstraint('session_id', 'last_message_index', name='uq_session_summary_index'),
    )

    # Relationships
    session = relationship("ChatSession", back_populates="summaries")


class ChatFeedback(Base):
    __tablename__ = 'chat_feedback'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey('chat_messages.id', ondelete='SET NULL'), nullable=True)
    rating = Column(Integer, nullable=False)  # e.g., 1-5
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    session = relationship("ChatSession", back_populates="feedback")
    message = relationship("ChatMessage", back_populates="feedback")


class ChatAttachment(Base):
    __tablename__ = 'chat_attachments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey('chat_messages.id', ondelete='SET NULL'), nullable=True)
    file_id = Column(String(255), nullable=False)  # References API Layer files ID
    file_name = Column(String(255), nullable=True)
    file_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    session = relationship("ChatSession", back_populates="attachments")
    message = relationship("ChatMessage", back_populates="attachments")


class FailedRequest(Base):
    __tablename__ = 'failed_requests'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)
    service_name = Column(String(100), nullable=False, index=True)
    error_message = Column(Text, nullable=False)
    error_type = Column(String(100), nullable=True)
    request_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    session = relationship("ChatSession", back_populates="failed_requests")


class ModelUsageLog(Base):
    __tablename__ = 'model_usage_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey('chat_sessions.session_id', ondelete='CASCADE'), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey('chat_messages.id', ondelete='SET NULL'), nullable=True)
    model_name = Column(String(255), nullable=False)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    cost = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    session = relationship("ChatSession", back_populates="model_usage_logs")
    message = relationship("ChatMessage", back_populates="model_usage_logs")
