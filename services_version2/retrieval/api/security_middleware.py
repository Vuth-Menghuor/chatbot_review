# Security middleware migrated from shared to retrieval
import time
import logging
from typing import Dict, Callable
from collections import defaultdict
from datetime import datetime, timedelta
from fastapi import Request, FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = defaultdict(list)
    def is_allowed(self, identifier: str) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - self.window_seconds
        self.requests[identifier] = [req_time for req_time in self.requests[identifier] if req_time > cutoff]
        if len(self.requests[identifier]) < self.max_requests:
            self.requests[identifier].append(now)
            return True, 0
        oldest_request = self.requests[identifier][0]
        retry_after = int(oldest_request - cutoff) + 1
        return False, retry_after

class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, max_requests_per_minute: int = 100, max_payload_size_mb: int = 10):
        super().__init__(app)
        self.rate_limiter = RateLimiter(max_requests_per_minute, 60)
        self.max_payload_size = max_payload_size_mb * 1024 * 1024
        self.suspicious_patterns = [
            "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
            "../", "..\\", "<script", "javascript:", "onerror=", "onclick="
        ]
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        allowed, retry_after = self.rate_limiter.is_allowed(client_ip)
        if not allowed:
            return JSONResponse(status_code=429, content={"detail": f"Rate limit exceeded. Retry after {retry_after}s."})
        # ...existing code for security checks...
        response = await call_next(request)
        return response
