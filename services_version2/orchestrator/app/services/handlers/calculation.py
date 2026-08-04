from __future__ import annotations
import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional, Any

from ...infrastructure.cache_service import get_cache_service

if TYPE_CHECKING:
    from ..coordinator import ServiceCoordinator
    from ..workflow import WorkflowContext

logger = logging.getLogger(__name__)


class CalculationHandler:
    @staticmethod
    def enrich_calculation_query_from_context(coordinator: ServiceCoordinator, service_query: str, session_context: Optional[Any]) -> str:
        """Enrich a calculation query with missing CIF value, origin country, or HS code from session context/history."""
        if not session_context:
            return service_query

        q_lower = service_query.lower()
        has_numeric_val = bool(re.search(r'\d+(?:,\d{3})*(?:\.\d+)?', q_lower))
        has_cif_keyword = any(k in q_lower for k in ["cif", "usd", "$", "khr", "price", "value", "worth", "cost"])
        has_origin = any(c in q_lower for c in ["china", "cambodia", "thailand", "vietnam", "laos", "japan", "korea", "singapore", "malaysia", "indonesia", "philippines", "usa", "us", "germany", "france", "uk", "india", "cn"])
        has_hs_code = bool(re.search(r"\b\d{4}\.\d{2}(?:\.\d{2})?\b", q_lower))

        cif_val = getattr(session_context, 'cif_value', None)
        currency = getattr(session_context, 'currency', None) or "USD"
        origin = getattr(session_context, 'origin_country', None)
        hs_code = getattr(session_context, 'hs_code', None)
        product = getattr(session_context, 'commercial_description', None) or getattr(session_context, 'product_category', None)

        if not cif_val or not origin or not hs_code:
            turns_to_check = []
            if hasattr(session_context, "turns") and session_context.turns:
                turns_to_check = [t.get("user") or t.get("user_input", "") for t in reversed(session_context.turns)]
            last_norm = getattr(session_context, 'last_normalized_query', None)
            if last_norm:
                turns_to_check.insert(0, last_norm)

            for prev_q in turns_to_check:
                if not prev_q:
                    continue
                try:
                    from app.infrastructure.clients import CalculatorServiceClient
                    params = CalculatorServiceClient._parse_question_for_calculation(prev_q)
                    if not cif_val and params.get("cif_value") is not None:
                        cif_val = params.get("cif_value")
                        if params.get("currency"):
                            currency = params.get("currency")
                    if not origin and params.get("origin_country"):
                        origin = params.get("origin_country")
                    if not hs_code and params.get("hs_code"):
                        hs_code = params.get("hs_code")
                    if not product and params.get("product_name"):
                        product = params.get("product_name")
                except Exception:
                    pass

        is_follow_up_fragment = (
            "use" in q_lower or "provided" in q_lower or "hs" in q_lower or
            not (has_numeric_val and has_cif_keyword) or len(q_lower.split()) <= 6
        )

        if not is_follow_up_fragment and (has_numeric_val and has_cif_keyword) and (has_origin or not origin) and (has_hs_code or not hs_code):
            return service_query

        parts = ["calculate import tax"]
        if ("hs" in q_lower or "code" in q_lower) and hs_code:
            parts.append(f"for HS {hs_code}")
        elif product:
            parts.append(f"for {product}")
            if hs_code:
                parts.append(f"HS {hs_code}")
        elif hs_code:
            parts.append(f"for HS {hs_code}")
        else:
            parts.append(f"for {service_query}")

        cif_to_use = cif_val if not (has_numeric_val and has_cif_keyword) else None
        if cif_to_use is not None:
            cif_display = int(cif_to_use) if cif_to_use == int(cif_to_use) else cif_to_use
            parts.append(f"CIF {cif_display} {currency}")
        elif has_numeric_val and has_cif_keyword:
            val_match = re.search(r'\d+(?:,\d{3})*(?:\.\d+)?', q_lower)
            if val_match:
                parts.append(f"CIF {val_match.group(0)} {currency}")

        origin_to_use = origin if not has_origin else None
        if origin_to_use:
            parts.append(f"from {origin_to_use}")

        enriched = " ".join(parts)
        logger.info(f"[{getattr(session_context, 'session_id', 'session')}] Enriched calculation query from context: '{service_query}' -> '{enriched}'")
        return enriched

    @staticmethod
    async def handle(coordinator: ServiceCoordinator, context: WorkflowContext) -> None:
        logger.info(f"[{context.request_id}] Routing to calculator service")
        try:
            from ..workflow import WorkflowStatus
            if not coordinator.calculator_client:
                context.add_error("Calculator service not configured")
                context.status = WorkflowStatus.FAILED
                return
                
            raw_service_query = coordinator._get_service_query(context)
            service_query = CalculationHandler.enrich_calculation_query_from_context(coordinator, raw_service_query, context.session_context)

            cif_val = getattr(context.session_context, 'cif_value', None) if context.session_context else None
            q_lower = service_query.lower()
            has_numeric_val = bool(re.search(r'\d+(?:,\d{3})*(?:\.\d+)?', q_lower))
            has_cif_keyword = any(k in q_lower for k in ["cif", "usd", "$", "khr", "price", "value", "worth", "cost"])
            is_clarification_resolution = bool(context.metadata and context.metadata.get("clarification_resolved"))
            if not cif_val and not (has_numeric_val and has_cif_keyword) and not is_clarification_resolution:
                logger.info(f"[{context.request_id}] Calculation missing CIF value. Prompting user for clarification.")
                
                product_name = None
                if context.session_context:
                    product_name = (
                        getattr(context.session_context, 'clarification_entity', None)
                        or getattr(context.session_context, 'commercial_description', None)
                        or getattr(context.session_context, 'product_category', None)
                    )
                if not product_name:
                    cleaned_product = re.sub(
                        r"(?i)\b(calculate|compute|how|about|the|tax|taxes|duty|duties|import|export|for|cbu|ckd|hs|code)\b",
                        "",
                        service_query
                    ).strip()
                    cleaned_product = re.sub(r"\s+", " ", cleaned_product).strip()
                    product_name = cleaned_product if cleaned_product else "this product"

                context.set_result("calculation", {
                    "answer": (
                        f"To calculate the import duty and taxes for **{product_name}**, please provide the **CIF value** "
                        "(Cost, Insurance, and Freight invoice value in USD or KHR, e.g., `$80,000 USD`)."
                    ),
                    "clarification_required": True,
                    "missing_fields": ["cif_value"]
                })
                context.status = WorkflowStatus.CLARIFICATION_REQUIRED
                if context.session_context:
                    context.session_context.set_pending_clarification(
                        candidate_intents=["calculation"],
                        rewritten_query=context.question
                    )
                return

            cache = get_cache_service()
            lang_tag = getattr(context.session_context, "language", "en") if context.session_context else "en"
            cache_query_key = f"{service_query}:{lang_tag}"
            cached_result = cache.get_cached_response(cache_query_key, intent="calculation")
            if cached_result:
                context.set_result("calculation", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return

            timeout_sec = min(
                coordinator.timeout_config.get_intent_timeout(context.intent),
                coordinator.timeout_config.get_service_timeout("calculator")
            )
            
            async def run_call():
                return await asyncio.wait_for(
                    coordinator.calculator_client.query(question=service_query), timeout=timeout_sec
                )
                
            result = await coordinator._execute_service_call(
                context=context,
                service_name="calculator",
                client_call_fn=run_call,
                request_payload={"question": service_query}
            )
            
            is_clarification = False
            if isinstance(result, dict):
                if result.get("clarification_required") or result.get("status") == "clarification_required":
                    is_clarification = True
                elif result.get("success") is False:
                    err_text = str(result.get("error", "") or result.get("answer", "") or "").lower()
                    if any(term in err_text for term in ["mismatch", "clarification", "please rewrite", "not found", "validation error"]):
                        is_clarification = True

            context.set_result("calculation", result)
            if is_clarification:
                context.status = WorkflowStatus.CLARIFICATION_REQUIRED
                if context.session_context:
                    context.session_context.set_pending_clarification(
                        candidate_intents=["calculation"],
                        rewritten_query=context.question
                    )
            else:
                cache.cache_response(question=cache_query_key, response=result, intent="calculation", ttl_seconds=2 * 3600, source="calculator")
                context.status = WorkflowStatus.COMPLETED

        except Exception as e:
            logger.error(f"[{context.request_id}] Calculation failed: {e}")
            context.add_error(f"Calculator service error: {str(e)}")
            from ..workflow import WorkflowStatus
            context.status = WorkflowStatus.FAILED
