import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import ErrorResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_body(request: Request, detail: str, error_code: str, errors: list | None = None) -> dict:
    return ErrorResponse(
        detail=detail,
        error_code=error_code,
        request_id=_request_id(request),
        errors=errors,
    ).model_dump(exclude_none=True)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    error_code = "http_error"
    if exc.status_code == 401:
        error_code = "unauthorized"
    elif exc.status_code == 403:
        error_code = "forbidden"
    elif exc.status_code == 404:
        error_code = "not_found"
    elif exc.status_code == 409:
        error_code = "conflict"
    elif exc.status_code == 422:
        error_code = "validation_error"
    elif exc.status_code == 429:
        error_code = "rate_limit_exceeded"

    if exc.status_code >= 500:
        logger.error("HTTP %s %s %s", exc.status_code, request.method, request.url.path, extra={"request_id": _request_id(request)})
    elif exc.status_code >= 400:
        logger.info("HTTP %s %s %s", exc.status_code, request.method, request.url.path, extra={"request_id": _request_id(request)})

    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    request.state.error_detail = detail[:512]
    return JSONResponse(status_code=exc.status_code, content=_error_body(request, detail, error_code))


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [{"loc": list(error.get("loc", [])), "msg": error.get("msg", ""), "type": error.get("type", "")} for error in exc.errors()]
    detail = "Request validation failed"
    request.state.error_detail = detail
    logger.info("Validation error %s %s", request.method, request.url.path, extra={"request_id": _request_id(request), "errors": errors})
    return JSONResponse(
        status_code=422,
        content=_error_body(request, detail, "validation_error", errors),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request.state.error_detail = "Internal server error"
    logger.exception(
        "Unhandled error %s %s",
        request.method,
        request.url.path,
        extra={"request_id": _request_id(request)},
    )
    return JSONResponse(
        status_code=500,
        content=_error_body(request, "Internal server error", "internal_error"),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
