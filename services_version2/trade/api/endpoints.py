"""Trade Query API routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from core.service import TradeService
from core.exceptions import ValidationError, UnknownIntentError, NoResultsError
from dal.exceptions import DALError
from core.normaliser import NormalisationError
from api.exceptions import map_core_exception_to_http, InvalidInputError, NotFoundError, DALServiceError, QueryTimeoutError
from api.schemas import QueryRequest, TradeQueryResponse
from api.validators import validate_question, validate_year_range
from core.constants import SUGGESTED_REPHRASE_WARNING

logger = logging.getLogger(__name__)

# Module-level service reference + setter/getter (injected from app.py at startup)
_service: TradeService | None = None


def set_service(service_instance: TradeService) -> None:
    global _service
    _service = service_instance


def get_service() -> TradeService:
    if _service is None:
        raise RuntimeError("TradeService not initialised. Call set_service() at startup.")
    return _service


router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0"}


@router.post("/query", tags=["Trade Queries"], response_model=TradeQueryResponse)
async def query_trade_data(request: QueryRequest) -> dict[str, Any]:
    try:
        question = validate_question(request.question)
        svc = get_service()
        result = svc.query_from_question(question, request.extracted_params)
        result["question"] = question
        return result
    except (ValidationError, UnknownIntentError) as e:
        logger.warning(f"Validation error: {e}")
        raise map_core_exception_to_http(e)
    except NoResultsError as e:
        logger.info(f"No results: {e}")
        
        q_params = getattr(e, "query_params", {}) or {}
        dal_url = getattr(e, "dal_source_url", None) or getattr(e, "query_params", {}).get("dal_source_url", "")
        raw_params = getattr(e, "query_params", None)
        filtered_params = None
        if isinstance(raw_params, dict):
            filtered_params = {k: v for k, v in raw_params.items() if v is not None and k != "dal_source_url"}
    
        intent = q_params.get("intent") or "summary"
        chart_type = "line" if intent == "trend" else ("pie" if intent == "breakdown" else "bar")
        title = f"No Data Found for {intent.replace('_', ' ').capitalize()}"
        fallback_viz = {
            "type": "empty",
            "title": title,
            "labels": [],
            "datasets": []
        }
        fallback_table = {"columns": [], "rows": []}

        return {
            "question": question,
            "status": "no_data",
            "count": 0,
            "records": [],
            "summary": {},
            "query_params": filtered_params,
            "table": fallback_table,
            "visualization": fallback_viz,
            "metadata": {
                "dal_source_url": dal_url,
                "intent": intent
            },
            "message": str(e),
            "suggestion": ["Try adjusting your filters (e.g. using a different country, year, or transport mode)."]
        }
    except DALError as e:
        logger.error(f"DAL error: {e}")
        raise map_core_exception_to_http(e)
    except NormalisationError as e:
        logger.error(f"Normalisation error: {e}")
        raise map_core_exception_to_http(e)
    except Exception as e:
        logger.error(f"POST /query error: {e}", exc_info=True)
        # Fix #9: Never return a bare {"status":"error","error":"..."} with no message/suggestions.
        # Always return a well-formed response so the frontend can display something useful.
        try:
            question_text = request.question if request and request.question else "your query"
        except Exception:
            question_text = "your query"
        return {
            "question": question_text,
            "status": "error",
            "count": 0,
            "records": [],
            "summary": {},
            "query_params": None,
            "table": {"columns": [], "rows": []},
            "visualization": {"type": "empty", "title": "Unable to process query", "labels": [], "datasets": []},
            "metadata": {"intent": "summary"},
            "message": (
                "Sorry, we encountered an unexpected error processing your request. "
                "Please try rephrasing your question or try again in a moment."
            ),
            "suggestion": [
                SUGGESTED_REPHRASE_WARNING,
                "Try a simpler query first, then add filters",
                "Contact support if this error persists",
            ],
        }


@router.post("/extract-params", tags=["Debug"])
async def extract_params(request: QueryRequest) -> dict[str, Any]:
    try:
        question = validate_question(request.question)
        svc = get_service()
        params = svc.extract_params_only(question)
        return {"question": question, "params": params}
    except (ValidationError, UnknownIntentError) as e:
        raise map_core_exception_to_http(e)
    except Exception as e:
        logger.error(f"POST /extract-params error: {e}", exc_info=True)
        raise map_core_exception_to_http(e)
