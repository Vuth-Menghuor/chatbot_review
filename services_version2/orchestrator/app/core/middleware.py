"""
Middleware for request tracking and logging
"""

import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import time
import structlog

from .logging import set_request_id, get_request_id, get_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Generates/extracts request_id for each request
    2. Logs request start and completion with correlation IDs
    3. Includes timing and status information
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Generate or extract request_id
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        set_request_id(request_id)
        
        # Get logger AFTER setting request_id so it's included in context
        logger = get_logger(__name__)
        
        # Log request start
        start_time = time.time()
        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params)
        )
        
        try:
            # process request 
            response = await call_next(request)
            
            # Log request completion 
            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2)
            )
            
            # add request_id to response headers for client correlation
            response.headers["X-Request-ID"] = request_id
            return response
        
        except Exception as e:
            # log errors 
            duration_ms = (time.time() - start_time) * 1000
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=round(duration_ms, 2)
            )
            raise