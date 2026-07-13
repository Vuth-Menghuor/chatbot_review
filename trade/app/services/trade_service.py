"""TradeService facade — orchestrates Stage 1 to Stage 5 pipeline."""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.core.exceptions import NoResultsError, ValidationError
from app.core.normaliser import normalise
from app.dal import DALClient, DALRequestBuilder

logger = logging.getLogger(__name__)

# Retry policy loaded from settings inside the service methods


class TradeService:
    """Business logic facade for trade_query."""

    def __init__(
        self,
        dal_client: DALClient | None = None,
        request_builder: DALRequestBuilder | None = None,
    ) -> None:
        self.dal_client = dal_client or DALClient.from_env()
        self.request_builder = request_builder or DALRequestBuilder()
        from app.services.cache_service import CacheService
        self.cache = CacheService()

    def query_from_question(self, question: str, extracted_params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Full pipeline: NL question → extract (with repair loop) → transform → handle → normalise."""
        logger.info(f"[TradeService] Received query_from_question request. Question: '{question}'")

        cached = self.cache.get(question)
        if cached:
            logger.info(f"[TradeService] Serving cached result for question: '{question}'")
            return cached

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
            "extra": final.extra,
            "question": question,
        }

        # Flatten helper keys for downstream consumption
        dal_params["trade_direction"] = final.filters.get("FLOW")
        partners = final.filters.get("PARTNER_COUNTRY")
        dal_params["partner_countries"] = partners if isinstance(partners, list) else None
        dal_params["partner_country"] = partners if isinstance(partners, str) else None
        dal_params["mode_of_transport"] = final.filters.get("MODE_OF_TRANSPORT")
        dal_params["hs_code"] = final.filters.get("HS_HEADING") or final.filters.get("HS_CODE")
        dal_params["hs_chapter"] = final.filters.get("HS_CHAPTER")
        dal_params["sitc_section"] = final.filters.get("SITC_SECTION")
        dal_params["sitc_division"] = final.filters.get("SITC_DIVISION")

        # Execute via DALClient
        logger.info(f"[TradeService] Executing trade database lookup via DALClient for sub-intent '{final.intent}'...")
        dal_request = self.request_builder.build_request(final.intent, dal_params)

        # Workaround for DAL Range Query Bug with FLOW filter
        is_range_query = bool(dal_request.start_period or dal_request.end_period)
        flow_filter_value = None
        if is_range_query and "FLOW" in dal_request.filters:
            logger.info("[TradeService] Range query detected with FLOW filter. Temporarily keeping FLOW filter in request to bypass DAL bug.")
            flow_filter_value = dal_request.filters.get("FLOW")

        dal_response = self.dal_client.execute(dal_request)

        # 1. Flow Post-filtering (workaround for range query bug / database leak)
        if flow_filter_value:
            # Restore FLOW filter in request
            dal_request.filters["FLOW"] = flow_filter_value

            allowed_flows = flow_filter_value if isinstance(flow_filter_value, list) else [flow_filter_value]
            allowed_flows_upper = {str(f).upper() for f in allowed_flows}

            raw_records = dal_response.get("records", [])
            filtered_records = []
            for r in raw_records:
                flow_key_in_record = None
                for k in r.keys():
                    if k.upper() == "FLOW":
                        flow_key_in_record = k
                        break
                if flow_key_in_record:
                    val = str(r.get(flow_key_in_record)).upper()
                    if val in allowed_flows_upper:
                        filtered_records.append(r)
                else:
                    filtered_records.append(r)

            dal_response["records"] = filtered_records

        # 2. Time Sub-Period Post-filtering (workaround for range query over-fetching e.g. "Q1 each year")
        if is_range_query:
            records = dal_response.get("records", [])
            filtered_records = list(records)
            did_filter_time = False

            req_quarter = scoped.quarter
            if req_quarter:
                q_suffix = f"-{str(req_quarter).upper()}"
                filtered_records = [
                    r for r in filtered_records
                    if str(r.get("PERIOD", r.get("period", ""))).endswith(q_suffix)
                ]
                did_filter_time = True
                logger.info(f"[TradeService] Post-filtering range query by quarter '{req_quarter}'. Kept {len(filtered_records)} records.")

            req_semester = scoped.semester
            if req_semester is not None:
                s_suffix = f"-S{req_semester}"
                filtered_records = [
                    r for r in filtered_records
                    if str(r.get("PERIOD", r.get("period", ""))).endswith(s_suffix)
                ]
                did_filter_time = True
                logger.info(f"[TradeService] Post-filtering range query by semester '{req_semester}'. Kept {len(filtered_records)} records.")

            req_month = scoped.month
            if req_month is not None:
                m_suffix = f"-{str(req_month).zfill(2)}"
                filtered_records = [
                    r for r in filtered_records
                    if str(r.get("PERIOD", r.get("period", ""))).endswith(m_suffix)
                ]
                did_filter_time = True
                logger.info(f"[TradeService] Post-filtering range query by month '{req_month}'. Kept {len(filtered_records)} records.")

            # Post-filtering by start_period and end_period range constraint
            start_p = final.start_period
            end_p = final.end_period
            if start_p or end_p:
                original_len = len(filtered_records)
                if start_p:
                    filtered_records = [
                        r for r in filtered_records
                        if str(r.get("PERIOD", r.get("period", ""))) >= str(start_p)
                    ]
                if end_p:
                    filtered_records = [
                        r for r in filtered_records
                        if str(r.get("PERIOD", r.get("period", ""))) <= str(end_p)
                    ]
                if len(filtered_records) != original_len:
                    logger.info(f"[TradeService] Post-filtering range query by range [{start_p}, {end_p}]. Kept {len(filtered_records)} records.")
                    did_filter_time = True

            if did_filter_time:
                dal_response["records"] = filtered_records

        # Summary recalculation (recalculate dal_response summary total to match filtered records)
        if "summary" in dal_response and isinstance(dal_response["summary"], dict):
            total_val = sum(float(r.get("VALUE_USD", r.get("trade_value", 0.0)) or 0.0) for r in dal_response.get("records", []))
            dal_response["summary"]["total_trade_value"] = total_val

        # Sanity check: if requested period differs from returned records,
        # post-filter to the requested period so we never silently serve wrong-year data.
        records = dal_response.get("records", [])
        if records and final.period:
            mismatched_periods = set()
            req_p_str = str(final.period)
            for r in records:
                r_p = r.get("PERIOD") or r.get("period")
                if r_p:
                    r_p_str = str(r_p)
                    if not (r_p_str == req_p_str or r_p_str.startswith(req_p_str + "-")):
                        mismatched_periods.add(r_p_str)
            
            if mismatched_periods:
                returned_period = sorted(list(mismatched_periods))[0]
                logger.warning(
                    f"[TradeService] Sanity Check Warning: Request period was '{final.period}', "
                    f"but DAL returned records with mismatched periods: {sorted(list(mismatched_periods))}. "
                    f"Post-filtering to requested period."
                )
                original_len = len(records)
                filtered_by_period = [
                    r for r in records
                    if str(r.get("PERIOD") or r.get("period", "")) == req_p_str
                    or str(r.get("PERIOD") or r.get("period", "")).startswith(req_p_str + "-")
                ]
                if len(filtered_by_period) != original_len:
                    dal_response["records"] = filtered_by_period
                    extra = dal_params.get("extra") or {}
                    extra["period_mismatch"] = True
                    extra["requested_period"] = req_p_str
                    extra["returned_period"] = returned_period
                    dal_params["extra"] = extra
                    logger.info(
                        f"[TradeService] Post-filtered from {original_len} to {len(filtered_by_period)} records "
                        f"matching requested period '{final.period}'."
                    )

        # Rebuild the canonical dal_source_url from the url_builder using the
        # original requested params so the URL always reflects what was asked for.
        try:
            corrected_req = self.request_builder.build_request(final.intent, dal_params)
            dal_url = self.dal_client._url_builder.build(corrected_req)
        except Exception:
            dal_url = dal_response.get("metadata", {}).get("dal_source_url", "")
        dal_params["dal_source_url"] = dal_url
        if isinstance(dal_response, dict):
            dal_response.setdefault("metadata", {})["dal_source_url"] = dal_url
        record_count = len(dal_response.get("records", [])) if isinstance(dal_response, dict) else 0
        logger.info(f"[TradeService] DAL query executed successfully. Retrieved {record_count} raw records.")

        # Normalise response
        logger.info("[TradeService] Normalising retrieved trade records into final response structures...")
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
        logger.info("[TradeService] Stage 6: Generating conversational NLG summary and suggestions...")
        from app.ai.nlg import generate_nlg_response
        try:
            result = generate_nlg_response(result, dal_params)
        except Exception as nlg_exc:
            logger.error(f"[TradeService] NLG generation failed — degrading gracefully: {nlg_exc}", exc_info=True)
            # NLG failure should never crash the whole response.
            # Return normalised data with a fallback message.
            result.setdefault("message", "Data retrieved successfully. (Summary generation unavailable.)")
            result.setdefault("suggestion", [
                "Try asking about a specific year or country for more detailed results.",
                "Show the breakdown by product category.",
                "Compare exports and imports for the same period.",
            ])

        # Ensure only the 10 allowed keys are returned in the result
        allowed_keys = {
            "status", "count", "records", "summary", "metadata",
            "query_params", "table", "visualization", "message", "suggestion"
        }
        result = {k: v for k, v in result.items() if k in allowed_keys}

        # Store in cache
        self.cache.set(question, result)

        logger.info("[TradeService] Processing complete. Returning normalised query results to Orchestrator.")
        return result

    def extract_params_only(self, question: str) -> dict[str, Any]:
        """Debug helper: return extracted params without hitting DAL.
        Now properly uses the full pipeline and LLM repair loop.
        """
        # Use the full pipeline WITH the repair loop
        scoped, final = self._build_validated_plan(question)

        from app.core.enrichment import _map_mot_to_names, deduce_year

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
            "year": deduce_year(scoped.year, final.period, final.start_period, final.end_period),
            "years": scoped.years,
            "month": scoped.month,
            "quarter": scoped.quarter,
            "semester": scoped.semester,
            "trade_direction": final.filters.get("FLOW"),
            "mode_of_transport": _map_mot_to_names(final.filters.get("MODE_OF_TRANSPORT")),
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
        from app.ai.extractor import extract_parameters_llm
        from app.core.enrichment_orchestrate import orchestrate_query_plan
        from app.core.enrichment_semantic import enrich_query_plan
        from app.core.validation import validate_query_plan, validate_question
        from app.handlers.scopes import apply_intent_scoping
        from app.schemas.query_plan import RawQueryPlan

        owns_extraction = extracted_params is None
        llm_params = extracted_params
        retry_context: Optional[str] = None
        last_error: Optional[Exception] = None

        from app.core.config import get_settings
        settings = get_settings()
        max_retries = settings.max_extraction_retries
        attempts = max_retries + 1 if owns_extraction else 1

        for attempt in range(1, attempts + 1):
            if owns_extraction:
                question = validate_question(question)
                llm_params = extract_parameters_llm(question, retry_context=retry_context)
                if llm_params is None:
                    raise ValidationError("LLM parameter extraction returned no parameters", field="question")
                logger.info(f"[TradeService] Extraction attempt {attempt}/{attempts}: {llm_params}")

            if llm_params is None:
                llm_params = {}

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
                raw_sitc_section=llm_params.get("sitc_section"),
                raw_sitc_division=llm_params.get("sitc_division"),
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
    from app.core.enrichment_orchestrate import orchestrate_query_plan
    from app.core.enrichment_semantic import enrich_query_plan
    from app.core.validation import validate_query_plan
    from app.handlers.scopes import apply_intent_scoping
    from app.schemas.query_plan import RawQueryPlan

    raw_params = dict(llm_params)

    raw_plan = RawQueryPlan(
        intent=raw_params.get("intent", "summary"),
        raw_origin_country=raw_params.get("origin_country"),
        raw_destination_country=raw_params.get("destination_country"),
        raw_partner_countries=raw_params.get("partner_countries"),
        raw_trade_direction=raw_params.get("trade_direction"),
        raw_product=raw_params.get("hs_code") or raw_params.get("hs_chapter") or raw_params.get("product"),
        raw_sitc_section=raw_params.get("sitc_section"),
        raw_sitc_division=raw_params.get("sitc_division"),
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

    from app.registry.semantic_registry import find_dimension_by_synonym

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
        "start_period": final.start_period or scoped.start_period,
        "end_period": final.end_period or scoped.end_period,
        "frequency": final.frequency,
        "sort": final.sort,
        "limit": scoped.limit or final.limit,
        "offset": final.offset,
        "extra": final.extra,
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
        if sp:
            sp_str = str(sp)
            if len(sp_str) >= 4 and sp_str[:4].isdigit():
                res["year"] = int(sp_str[:4])

    res["trade_direction"] = final.filters.get("FLOW")
    partners = final.filters.get("PARTNER_COUNTRY")
    res["partner_countries"] = partners if isinstance(partners, list) else None
    res["partner_country"] = partners if isinstance(partners, str) else None

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
    from app.core.validation import validate_question
    question = validate_question(question)
    logger.info(f"[extract_parameters] Question: {question}")

    try:
        from app.ai.extractor import extract_parameters_llm
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
