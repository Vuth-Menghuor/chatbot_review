from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from fastapi import HTTPException

from app.core.exceptions import ErrorResponse
from app.services.rate_limit_service import check_general_rate_limit


class GeneralRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Health probes must stay available even when general API rate limits are saturated.
        if request.url.path.endswith("/health") or request.url.path.startswith("/api/v1/health/"):
            return await call_next(request)

        try:
            await check_general_rate_limit(request)
        except HTTPException as exc:
            if exc.status_code == 429:
                request.state.error_detail = str(exc.detail)
                return JSONResponse(
                    status_code=429,
                    content=ErrorResponse(
                        detail=str(exc.detail),
                        error_code="rate_limit_exceeded",
                        request_id=getattr(request.state, "request_id", None),
                    ).model_dump(exclude_none=True),
                )
            raise

        return await call_next(request)
