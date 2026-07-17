"""
Structured logging configuration with correlation IDs
"""

import contextvars
import logging
import json
from typing import Any, Dict
import structlog
from datetime import datetime


# Context variable to hold the correlation ID for each request in an async environment 
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=None
)

def get_request_id() -> str:
    """Get the current request ID from context."""
    return request_id_var.get()

def set_request_id(request_id: str) -> None:
    """Set the request ID in context."""
    request_id_var.set(request_id)
    

def setup_structured_logging() -> None:
    """
    Configure structlog for JSON logging with correlation IDs
    """
    # Configure Structlog 
    structlog.configure(
        processors = [
            structlog.contextvars.merge_contextvars,  # Merge context variables (like request_id) into log entries
            structlog.processors.TimeStamper(fmt="iso"),  # Add ISO8601 timestamps
            structlog.processors.add_log_level,  # Add log level to entries
            structlog.processors.StackInfoRenderer(),  # Add stack info if available
            structlog.processors.format_exc_info,  # Format exception info if present
            structlog.dev.ConsoleRenderer() 
            # Render logs in a human-readable format (use JSONRenderer for production) - structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard loggin to use structlog
    logging.basicConfig(
        format="%(message)s",
        level = logging.INFO,
    )
    
def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structlog logger with the given name.
    
    Request ID is automatically added via contextvars processor.
    """
    logger = structlog.get_logger(name)
    # Bind request_id from context - contextvars processor will also add it
    request_id = get_request_id()
    if request_id:
        logger = logger.bind(request_id=request_id)
    return logger