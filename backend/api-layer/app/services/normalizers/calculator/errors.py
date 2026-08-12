import logging
import re
from typing import Any

from app.schemas.normalized_chat import PublicError

logger = logging.getLogger(__name__)

PUBLIC_CALCULATOR_ERROR_MESSAGES = {
    "CALCULATOR_VALIDATION_ERROR": "The calculator request could not be validated.",
    "CALCULATOR_MISSING_INPUT": "More information is needed to complete the calculation.",
    "CALCULATOR_SERVICE_UNAVAILABLE": "The calculator service is temporarily unavailable.",
    "CALCULATOR_TIMEOUT": "The calculator service timed out.",
    "INVALID_CALCULATOR_RESPONSE": "The calculator returned an unsupported response.",
    "INTERNAL_API_ERROR": "The calculator response could not be processed.",
}

RETRYABLE_CALCULATOR_ERROR_CODES = {
    "CALCULATOR_SERVICE_UNAVAILABLE",
    "CALCULATOR_TIMEOUT",
    "INTERNAL_API_ERROR",
}


def normalize_calculator_public_errors(payload: dict[str, Any]) -> list[PublicError]:
    if is_calculator_clarification(payload):
        return []

    raw_errors = payload.get("errors") or payload.get("error") or payload.get("message")
    code = calculator_error_code(payload, raw_errors)
    if not code:
        return []

    log_raw_calculator_error(payload, raw_errors, code)
    return [
        PublicError(
            code=code,
            message=PUBLIC_CALCULATOR_ERROR_MESSAGES[code],
            retryable=code in RETRYABLE_CALCULATOR_ERROR_CODES,
        )
    ]


def calculator_error_block_message(errors: list[PublicError]) -> str | None:
    return errors[0].message if errors else None


def is_calculator_clarification(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").lower()
    return bool(
        payload.get("clarification_required") is True
        or status in {"clarification_required", "needs_clarification", "clarify", "clarification"}
    )


def calculator_error_code(payload: dict[str, Any], raw_errors: Any) -> str | None:
    status = str(payload.get("status") or "").lower()
    text = raw_error_text(raw_errors).lower()
    upstream_code = raw_error_code(raw_errors)

    if upstream_code:
        mapped = map_upstream_calculator_code(upstream_code)
        if mapped:
            return mapped
    if any(marker in text for marker in ("missing", "required", "clarification", "need")):
        return "CALCULATOR_MISSING_INPUT"
    if any(marker in text for marker in ("validation", "invalid input", "bad request")):
        return "CALCULATOR_VALIDATION_ERROR"
    if any(marker in text for marker in ("timeout", "timed out", "deadline")):
        return "CALCULATOR_TIMEOUT"
    if any(marker in text for marker in ("unavailable", "connection", "connect", "refused", "service down")):
        return "CALCULATOR_SERVICE_UNAVAILABLE"
    if any(marker in text for marker in ("malformed", "unsupported response", "invalid response")):
        return "INVALID_CALCULATOR_RESPONSE"
    if status in {"failed", "error", "invalid_query"}:
        return "CALCULATOR_SERVICE_UNAVAILABLE"
    return None


def map_upstream_calculator_code(value: str) -> str | None:
    normalized = value.strip().upper()
    if normalized in PUBLIC_CALCULATOR_ERROR_MESSAGES:
        return normalized
    if "TIMEOUT" in normalized:
        return "CALCULATOR_TIMEOUT"
    if "VALIDATION" in normalized or "INVALID_INPUT" in normalized:
        return "CALCULATOR_VALIDATION_ERROR"
    if "MISSING" in normalized or "REQUIRED" in normalized:
        return "CALCULATOR_MISSING_INPUT"
    if "UNAVAILABLE" in normalized or "CONNECTION" in normalized:
        return "CALCULATOR_SERVICE_UNAVAILABLE"
    if "INVALID_RESPONSE" in normalized or "MALFORMED" in normalized:
        return "INVALID_CALCULATOR_RESPONSE"
    return None


def log_raw_calculator_error(payload: dict[str, Any], raw_errors: Any, public_code: str) -> None:
    logger.warning(
        "calculator_upstream_error request_id=%s session_id=%s public_code=%s raw_error=%r",
        payload.get("request_id") or payload.get("requestId"),
        payload.get("session_id") or payload.get("sessionId"),
        public_code,
        raw_errors,
    )


def raw_error_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(str(item) for item in (
            value.get("message"),
            value.get("detail"),
            value.get("error"),
            value.get("code"),
            value.get("type"),
        ) if item is not None)
    if isinstance(value, list):
        return " ".join(raw_error_text(item) for item in value)
    return str(value)


def raw_error_code(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("code", "error_code", "type"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
    if isinstance(value, list):
        for item in value:
            code = raw_error_code(item)
            if code:
                return code
    return None


def contains_sensitive_internal_text(value: str) -> bool:
    return bool(
        re.search(
            r"(traceback|exception|postgres|database|api[_ -]?key|secret|token|http://|https://|prompt)",
            value,
            flags=re.IGNORECASE,
        )
    )
