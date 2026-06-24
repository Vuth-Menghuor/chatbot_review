"""TradeService facade — orchestrates Stage 1 to Stage 5 pipeline."""

from __future__ import annotations

import logging
from typing import Any, Optional

from ..dal import DALClient, DALRequestBuilder
from .exceptions import ValidationError, NoResultsError
from .normaliser import normalise

logger = logging.getLogger(__name__)

MAX_EXTRACTION_RETRIES = 2


class TradeService:
    """Business logic facade for trade_query."""

    def __init__(
        self,
        dal_client: DALClient | None = None,
        request_builder: DALRequestBuilder | None = None,
    ) -> None:
        self.dal_client = dal_client or DALClient.from_env()
        self.request_builder = request_builder or DALRequestBuilder()

    def query_from_question(self, question: str, extracted_params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Full pipeline: NL question → extract (with repair loop) → transform → handle → normalise."""
        logger.info(f"[TradeService] Received query_from_question request. Question: '{question}'")

        # Stage 1-5: extraction + enrichment + scoping + orchestration + validation,
        # with a validation-feedback repair loop around the LLM extraction call.
        scoped, final = self._build_validated_plan(question, extracted_params)

        # Convert back to compat dict format for the handlers & normalisers
        dal_params = {
            "intent": final.intent,
            "version": final.version,
            "filters": final.filters,
            "metrics": final.metrics,
            "group_by": final.group_by,
            "dimensions": final.dimensions,
            "period": final.period,
            "start_period": final.start_period,
            "end_period": final.end_period,
            "frequency": final.frequency,
            "sort": final.sort,
            "limit": final.limit,
            "offset": final.offset,
        }

        # Flatten helper keys for downstream consumption
        dal_params["trade_direction"] = final.filters.get("FLOW")
        dal_params["partner_countries"] = final.filters.get("PARTNER_COUNTRY") if isinstance(final.filters.get("PARTNER_COUNTRY"), list) else None
        dal_params["partner_country"] = final.filters.get("PARTNER_COUNTRY") if isinstance(final.filters.get("PARTNER_COUNTRY"), str) else None
        dal_params["mode_of_transport"] = final.filters.get("MODE_OF_TRANSPORT")
        dal_params["hs_code"] = final.filters.get("HS_HEADING") or final.filters.get("HS_CODE")
        dal_params["hs_chapter"] = final.filters.get("HS_CHAPTER")
        dal_params["sitc_section"] = final.filters.get("SITC_SECTION")
        dal_params["sitc_division"] = final.filters.get("SITC_DIVISION")

        # Execute via DALClient
        logger.info(f"[TradeService] Executing trade database lookup via DALClient for sub-intent '{final.intent}'...")
        dal_request = self.request_builder.build_request(final.intent, dal_params)
        dal_response = self.dal_client.execute(dal_request)
        dal_params["dal_source_url"] = dal_response.get("metadata", {}).get("dal_source_url", "")
        record_count = len(dal_response.get("records", [])) if isinstance(dal_response, dict) else 0
        logger.info(f"[TradeService] DAL query executed successfully. Retrieved {record_count} raw records.")

        # Normalise response
        logger.info(f"[TradeService] Normalising retrieved trade records into final response structures...")
        result = normalise(dal_response, final.intent, query_params=dal_params)

        filtered_params = {k: v for k, v in dal_params.items() if v is not None and k != "dal_source_url"}
        if result["count"] == 0:
            logger.warning(f"[TradeService] No trade data matches query criteria for question: '{question}'")
            raise NoResultsError(
                f"No trade data found for: {question}",
                query_params=filtered_params,
                dal_source_url=dal_params.get("dal_source_url"),
            )

        # Attach original query params for transparency
        result["query_params"] = filtered_params

        # Stage 6: Natural Language Generation (NLG)
        logger.info(f"[TradeService] Stage 6: Generating conversational NLG summary and suggestions...")
        from .nlg import generate_nlg_response
        result = generate_nlg_response(result, dal_params)

        # Ensure only the 10 allowed keys are returned in the result
        allowed_keys = {
            "status", "count", "records", "summary", "metadata",
            "query_params", "table", "visualization", "message", "suggestion"
        }
        result = {k: v for k, v in result.items() if k in allowed_keys}

        logger.info(f"[TradeService] Processing complete. Returning normalised query results to Orchestrator.")
        return result

    def extract_params_only(self, question: str) -> dict[str, Any]:
        """Debug helper: return extracted params without hitting DAL.
        Now properly uses the full pipeline and LLM repair loop.
        """
        # Use the full pipeline WITH the repair loop
        scoped, final = self._build_validated_plan(question)
        
        # Build the structured dictionary expected by the test script
        res = {
            "intent": final.intent,
            "version": final.version,
            "filters": final.filters,
            "metrics": final.metrics,
            "group_by": scoped.group_by,
            "dimensions": scoped.dimensions,
            "period": final.period,
            "start_period": final.start_period,
            "end_period": final.end_period,
            "frequency": final.frequency,
            "sort": final.sort,
            "limit": final.limit,
            "offset": final.offset,
            "sort_order": scoped.sort_order,
            "sort_metric": scoped.sort_metric,
            "year": scoped.year,
            "years": scoped.years,
            "month": scoped.month,
            "quarter": scoped.quarter,
            "semester": scoped.semester,
            "trade_direction": final.filters.get("FLOW"),
            "mode_of_transport": final.filters.get("MODE_OF_TRANSPORT"),
            "hs_chapter": final.filters.get("HS_CHAPTER"),
            "hs_code": final.filters.get("HS_HEADING") or final.filters.get("HS_CODE"),
            "sitc_section": final.filters.get("SITC_SECTION"),
            "sitc_division": final.filters.get("SITC_DIVISION"),
            "origin_country": scoped.origin_country,
            "destination_country": scoped.destination_country,
        }
        
        # Flatten partner countries so the test script can easily read them
        partners = final.filters.get("PARTNER_COUNTRY")
        if isinstance(partners, list):
            res["partner_countries"] = partners
            res["partner_country"] = partners[0] if len(partners) == 1 else None
        elif isinstance(partners, str):
            res["partner_countries"] = [partners]
            res["partner_country"] = partners
        else:
            res["partner_countries"] = None
            res["partner_country"] = None

        return res

    def _build_validated_plan(self, question: str, extracted_params: Optional[dict[str, Any]] = None):
        """Stage 1-5 pipeline with a validation-feedback repair loop.

        If the caller already supplied extracted_params (e.g. from an upstream
        orchestrator), we still validate them, but we do NOT retry against the
        LLM on failure since we have no extraction call to repair -- we just
        raise immediately. The retry loop only applies when *this* service is
        responsible for the extraction call.

        Returns:
            (scoped, final) tuple — the ScopedQueryPlan and FinalQueryPlan.
        """
        from .query_plan import RawQueryPlan
        from .enrichment import enrich_query_plan, orchestrate_query_plan
        from ..handlers.scopes import apply_intent_scoping
        from .validation import validate_question, validate_query_plan
        from .llm_extractor import extract_parameters_llm

        owns_extraction = extracted_params is None
        llm_params = extracted_params
        retry_context: Optional[str] = None
        last_error: Optional[Exception] = None

        attempts = MAX_EXTRACTION_RETRIES + 1 if owns_extraction else 1

        for attempt in range(1, attempts + 1):
            if owns_extraction:
                question = validate_question(question)
                llm_params = extract_parameters_llm(question, retry_context=retry_context)
                if llm_params is None:
                    raise ValidationError("LLM parameter extraction returned no parameters", field="question")
                logger.info(f"[TradeService] Extraction attempt {attempt}/{attempts}: {llm_params}")

            raw_plan = RawQueryPlan(
                intent=llm_params.get("intent", "summary"),
                raw_origin_country=llm_params.get("origin_country"),
                raw_destination_country=llm_params.get("destination_country"),
                raw_partner_countries=llm_params.get("partner_countries"),
                raw_trade_direction=llm_params.get("trade_direction"),
                raw_product=llm_params.get("hs_code") or llm_params.get("hs_chapter") or llm_params.get("product"),
                raw_mode_of_transport=llm_params.get("mode_of_transport"),
                raw_year=llm_params.get("year"),
                raw_years=llm_params.get("years"),
                raw_month=llm_params.get("month"),
                raw_quarter=llm_params.get("quarter"),
                raw_semester=llm_params.get("semester"),
                raw_start_period=llm_params.get("start_period"),
                raw_end_period=llm_params.get("end_period"),
                raw_frequency=llm_params.get("frequency"),
                raw_group_by=llm_params.get("group_by"),
                raw_dimensions=llm_params.get("dimensions"),
                raw_metrics=llm_params.get("metrics"),
                raw_sort_order=llm_params.get("sort_order"),
                raw_sort_metric=llm_params.get("sort_metric"),
                raw_limit=llm_params.get("limit"),
                raw_offset=llm_params.get("offset"),
                version=llm_params.get("version", "trade_volume_1.0"),
                question=question,
            )

            try:
                enriched = enrich_query_plan(raw_plan)
                scoped = apply_intent_scoping(enriched)
                final = orchestrate_query_plan(scoped)
                validate_query_plan(final)
                return scoped, final  # success
            except ValidationError as e:
                last_error = e
                logger.warning(
                    f"[TradeService] Query plan validation failed on attempt {attempt}/{attempts}: {e}"
                )
                if not owns_extraction or attempt == attempts:
                    # Either the params were handed to us (nothing to retry), or
                    # we're out of retries -- surface the error.
                    raise
                # Feed the validation error back to the LLM for the next attempt.
                retry_context = f"{e}"
                continue

        # Should be unreachable, but keep a defensive raise.
        raise last_error or ValidationError("Query plan validation failed", field="question")


# ---------------------------------------------------------------------------
# Legacy module-level helpers (unchanged from before Phase 1 — used by the
# /extract-params debug endpoint via extract_params_only() above).
# NOTE: this is the dual-pipeline duplication flagged earlier as a Phase 3
# cleanup target. Left as-is here since Phase 1 scope is the repair loop
# and regex-override removal only.
# ---------------------------------------------------------------------------

def post_resolve_parameters(llm_params: dict[str, Any], question: str) -> dict[str, Any]:
    """Resolve product mappings, apply defaults, and validate structured params (legacy pipeline coordinator)."""
    from .query_plan import RawQueryPlan
    from .enrichment import enrich_query_plan, orchestrate_query_plan
    from ..handlers.scopes import apply_intent_scoping
    from .validation import validate_query_plan

    raw_params = dict(llm_params)

    raw_plan = RawQueryPlan(
        intent=raw_params.get("intent", "summary"),
        raw_origin_country=raw_params.get("origin_country"),
        raw_destination_country=raw_params.get("destination_country"),
        raw_partner_countries=raw_params.get("partner_countries"),
        raw_trade_direction=raw_params.get("trade_direction"),
        raw_product=raw_params.get("hs_code") or raw_params.get("hs_chapter") or raw_params.get("product"),
        raw_mode_of_transport=raw_params.get("mode_of_transport"),
        raw_year=raw_params.get("year"),
        raw_years=raw_params.get("years"),
        raw_month=raw_params.get("month"),
        raw_quarter=raw_params.get("quarter"),
        raw_semester=raw_params.get("semester"),
        raw_start_period=raw_params.get("start_period"),
        raw_end_period=raw_params.get("end_period"),
        raw_frequency=raw_params.get("frequency"),
        raw_group_by=raw_params.get("group_by"),
        raw_dimensions=raw_params.get("dimensions"),
        raw_metrics=raw_params.get("metrics"),
        raw_sort_order=raw_params.get("sort_order"),
        raw_sort_metric=raw_params.get("sort_metric"),
        raw_limit=raw_params.get("limit"),
        raw_offset=raw_params.get("offset"),
        version=raw_params.get("version", "trade_volume_1.0"),
        question=question,
    )

    enriched = enrich_query_plan(raw_plan)
    scoped = apply_intent_scoping(enriched)
    final = orchestrate_query_plan(scoped)

    validate_query_plan(final)

    from .semantic_registry import find_dimension_by_synonym

    raw_group_by = raw_params.get("group_by")
    if raw_group_by:
        resolved_group_by = [find_dimension_by_synonym(g) or g.upper() for g in raw_group_by]
    else:
        resolved_group_by = scoped.group_by

    raw_dimensions = raw_params.get("dimensions")
    if raw_dimensions:
        resolved_dimensions = [find_dimension_by_synonym(d) or d.upper() for d in raw_dimensions]
    else:
        resolved_dimensions = scoped.dimensions

    res_metrics = list(final.metrics)
    raw_m = raw_params.get("metrics") or []
    if "VALUE_KHR" in raw_m or any(str(m).upper() == "VALUE_KHR" for m in raw_m):
        if "VALUE_KHR" not in res_metrics:
            res_metrics.append("VALUE_KHR")
        if "VALUE_USD" in res_metrics:
            res_metrics.remove("VALUE_USD")

    res = {
        "intent": final.intent,
        "version": final.version,
        "filters": final.filters,
        "metrics": res_metrics,
        "group_by": resolved_group_by,
        "dimensions": resolved_dimensions,
        "period": final.period,
        "start_period": final.start_period,
        "end_period": final.end_period,
        "frequency": final.frequency,
        "sort": final.sort,
        "limit": final.limit,
        "offset": final.offset,
        "sort_order": scoped.sort_order,
        "sort_metric": scoped.sort_metric,
        "year": scoped.year,
        "years": scoped.years,
        "month": scoped.month,
        "quarter": scoped.quarter,
        "semester": scoped.semester,
    }

    if raw_params.get("mode_of_transport"):
        res["mode_of_transport"] = raw_params.get("mode_of_transport")
    else:
        res["mode_of_transport"] = None

    orig = enriched.origin_country or raw_params.get("origin_country")
    dest = enriched.destination_country or raw_params.get("destination_country")

    partners = enriched.partner_countries or raw_params.get("partner_countries")
    partner = None
    if isinstance(partners, list) and len(partners) == 1:
        partner = partners[0]
    elif isinstance(partners, str):
        partner = partners
    if not partner:
        partner = raw_params.get("partner_country")

    if orig == "KH" and not dest and partner:
        dest = partner
    elif dest == "KH" and not orig and partner:
        orig = partner
    elif not orig and not dest and partner:
        flow = final.filters.get("FLOW") or raw_params.get("trade_direction")
        if flow == "EX":
            orig = "KH"
            dest = partner
        elif flow == "IM":
            orig = partner
            dest = "KH"
        else:
            orig = "KH"
            dest = partner

    if orig and not dest:
        res["origin_country"] = orig
        res["destination_country"] = None
    elif dest and not orig:
        res["origin_country"] = dest
        res["destination_country"] = None
    else:
        res["origin_country"] = orig
        res["destination_country"] = dest

    if res.get("year") is None:
        sp = res.get("start_period")
        if sp and len(sp) >= 4 and sp[:4].isdigit():
            res["year"] = int(sp[:4])

    res["trade_direction"] = final.filters.get("FLOW")
    res["partner_countries"] = final.filters.get("PARTNER_COUNTRY") if isinstance(final.filters.get("PARTNER_COUNTRY"), list) else None
    res["partner_country"] = final.filters.get("PARTNER_COUNTRY") if isinstance(final.filters.get("PARTNER_COUNTRY"), str) else None

    res["hs_chapter"] = raw_params.get("hs_chapter") or final.filters.get("HS_CHAPTER")
    if raw_params.get("hs_chapter"):
        res["hs_code"] = None
    else:
        res["hs_code"] = final.filters.get("HS_HEADING") or final.filters.get("HS_CODE")

    res["sitc_section"] = final.filters.get("SITC_SECTION")
    res["sitc_division"] = final.filters.get("SITC_DIVISION")

    return res


def extract_parameters(question: str) -> dict[str, Any]:
    """Master extraction: detect intent + extract entities from NL question."""
    from .validation import validate_question
    question = validate_question(question)
    logger.info(f"[extract_parameters] Question: {question}")

    try:
        from .llm_extractor import extract_parameters_llm
        llm_params = extract_parameters_llm(question)
        if llm_params is None:
            raise ValidationError("LLM parameter extraction returned no parameters", field="question")
        logger.info(f"[extract_parameters] LLM extracted successfully: {llm_params}")
        return post_resolve_parameters(llm_params, question)
    except Exception as e:
        if isinstance(e, ValidationError):
            raise
        logger.error(f"[extract_parameters] LLM parameter extraction failed: {e}")
        raise ValidationError(f"Parameter extraction failed: {str(e)}", field="question") from e