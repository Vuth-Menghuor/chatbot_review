import time
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.services.api_log_service import save_api_request_log


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            user_id = getattr(request.state, "user_id", None)
            if user_id is not None and not isinstance(user_id, UUID):
                try:
                    user_id = UUID(str(user_id))
                except (TypeError, ValueError):
                    user_id = None

            await save_api_request_log(
                user_id=user_id,
                method=request.method,
                path=request.url.path,
                query_string=request.url.query[:2048] if request.url.query else None,
                status_code=status_code,
                ip_address=request.client.host if request.client else None,
                user_agent=(request.headers.get("user-agent") or "")[:512],
                duration_ms=round((time.perf_counter() - started) * 1000),
                request_id=getattr(request.state, "request_id", None),
                error_detail=getattr(request.state, "error_detail", None),
            )
