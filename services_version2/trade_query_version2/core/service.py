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
        logger.info(f"[TradeService] Received query_from_question request. Question: '{question}'")

        # 1. Extract parameters
        if extracted_params:
            logger.info(f"[TradeService] Using provided extracted_params from Orchestrator: {extracted_params}")
            from .validation import post_resolve_parameters
            raw_params = post_resolve_parameters(extracted_params, question)
            logger.info(f"[TradeService] Post-resolved parameters: {raw_params}")
        else:
            logger.info(f"[TradeService] No extracted_params provided. Running parameter extraction from question...")
            raw_params = extract_parameters(question)
        
        intent = raw_params.get("intent", "summary")
        logger.info(f"[TradeService] Selected sub-intent: '{intent}' (of the 7 trade intents: summary, trend, comparison, breakdown, ranking, growth, trade_balance)")

        # 2. Transform to DAL-ready params
        logger.info(f"[TradeService] Transforming raw parameters to DAL query format...")
        dal_params = transform_params_for_dal(raw_params)
        logger.info(f"[TradeService] DAL-ready query parameters: {dal_params}")

        # 3. Execute via handler
        logger.info(f"[TradeService] Executing trade database lookup via DAL handler for sub-intent '{intent}'...")
        dal_response = self.handler.handle(intent, dal_params)
        record_count = len(dal_response.get("records", [])) if isinstance(dal_response, dict) else 0
        logger.info(f"[TradeService] DAL query executed successfully. Retrieved {record_count} raw records.")

        # 4. Normalise response
        logger.info(f"[TradeService] Normalising retrieved trade records into final response structures...")
        result = normalise(dal_response, intent, query_params=dal_params)

        if result["count"] == 0:
            logger.warning(f"[TradeService] No trade data matches query criteria for question: '{question}'")
            raise NoResultsError(f"No trade data found for: {question}", query_params=dal_params)

        # Attach original query params for transparency
        result["query_params"] = dal_params
        logger.info(f"[TradeService] Processing complete. Returning normalised query results to Orchestrator.")
        return result

    def extract_params_only(self, question: str) -> dict[str, Any]:
        """Debug helper: return extracted params without hitting DAL."""
        return extract_parameters(question)
