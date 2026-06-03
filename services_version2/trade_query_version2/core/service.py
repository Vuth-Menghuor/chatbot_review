"""TradeService facade — orchestrates extract → transform → handle → normalise."""

from __future__ import annotations

import logging
from typing import Any

from ..dal import DALClient
from ..handlers.base import BaseHandler
from .exceptions import ValidationError, NoResultsError
from .normaliser import normalise
from .transformers import transform_params_for_dal
from .validation import extract_parameters

logger = logging.getLogger(__name__)


class TradeService:
    """Business logic facade for trade_query."""

    def __init__(
        self,
        handler: BaseHandler | None = None,
    ) -> None:
        self.handler = handler or BaseHandler()

    def query_from_question(self, question: str, extracted_params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Full pipeline: NL question → extract → transform → handle → normalise."""
        logger.info(f"[query_from_question] Question: {question}")

        # 1. Extract parameters
        if extracted_params:
            logger.info(f"[query_from_question] Using provided extracted_params: {extracted_params}")
            from .validation import post_resolve_parameters
            raw_params = post_resolve_parameters(extracted_params, question)
        else:
            raw_params = extract_parameters(question)
        intent = raw_params.get("intent", "summary")

        # 2. Transform to DAL-ready params
        dal_params = transform_params_for_dal(raw_params)

        # 3. Execute via handler
        dal_response = self.handler.handle(intent, dal_params)

        # 4. Normalise response
        result = normalise(dal_response, intent, query_params=dal_params)

        if result["count"] == 0:
            raise NoResultsError(f"No trade data found for: {question}", query_params=dal_params)

        # Attach original query params for transparency
        result["query_params"] = dal_params
        return result

    def extract_params_only(self, question: str) -> dict[str, Any]:
        """Debug helper: return extracted params without hitting DAL."""
        return extract_parameters(question)
