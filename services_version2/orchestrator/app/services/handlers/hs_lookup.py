from __future__ import annotations
import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

from ...infrastructure.cache_service import get_cache_service
from ...utils import extract_entity, clean_hs_query_for_retrieval
from ..heuristics import MAX_PRODUCT_ASK_BACK_RETRIES
from ..hs_classifier import detect_simple_product_category
from ..hs_classifier import extract_hs_code
from ..clarification_manager import ClarificationManager
from ..translator import QueryTranslator

if TYPE_CHECKING:
    from ..coordinator import ServiceCoordinator
    from ..workflow import WorkflowContext

logger = logging.getLogger(__name__)


class HsCodeLookupHandler:
    @staticmethod
    async def handle(coordinator: ServiceCoordinator, context: WorkflowContext) -> None:
        logger.info(f"[{context.request_id}] Routing to retrieval service for HS Lookup")
        try:
            from ..workflow import WorkflowStatus
            if not coordinator.retrieval_client:
                context.add_error("Retrieval service not configured")
                context.status = WorkflowStatus.FAILED
                return

            service_query = coordinator._get_service_query(context)
            clean_query = clean_hs_query_for_retrieval(service_query)
            if coordinator._looks_like_short_product_lookup(clean_query):
                service_query = f"what is hs code of {clean_query}"
                clean_query = clean_hs_query_for_retrieval(service_query)
                context.question = service_query
            
            # Detect if there is an explicit HS code in the query
            explicit_hs = None
            raw_q_lower = service_query.lower()
            explicit_match = re.search(
                r"\b(?:hs\s*code|hs)\s*[:#]?\s*(\d{4}(?:\.\d{2}){1,2}|\d{8}|\d{6}|\d{4})\b",
                raw_q_lower
            )
            if explicit_match:
                explicit_hs = explicit_match.group(1).strip()
            if not explicit_hs:
                bare_match = re.search(r"\b(\d{4}\.\d{2}(?:\.\d{2})?)\b", service_query)
                if bare_match:
                    explicit_hs = bare_match.group(1).strip()
                    
            if explicit_hs and explicit_hs.isdigit():
                if len(explicit_hs) == 8:
                    explicit_hs = f"{explicit_hs[:4]}.{explicit_hs[4:6]}.{explicit_hs[6:8]}"
                elif len(explicit_hs) == 6:
                    explicit_hs = f"{explicit_hs[:4]}.{explicit_hs[4:6]}"
            elif explicit_hs:
                explicit_hs = explicit_hs.replace(" ", ".")

            hs_mode = "best"
            selected_code = None
            if explicit_hs:
                hs_mode = "select"
                selected_code = explicit_hs
                # If we have a clarification entity, preserve it as the query instead of any generalization
                if context.session_context and getattr(context.session_context, "clarification_entity", None):
                    clean_query = context.session_context.clarification_entity
            
            logger.info(f"[{context.request_id}] Cleaned retrieval query: '{service_query}' -> '{clean_query}' (hs_mode={hs_mode}, selected_code={selected_code})")

            timeout_sec = min(
                coordinator.timeout_config.get_intent_timeout(context.intent),
                coordinator.timeout_config.get_service_timeout("retrieval")
            )

            cache = get_cache_service()
            lang_tag = context.metadata.get("language") or getattr(context, "language", "en")
            cache_key = f"{clean_query}:{lang_tag}:{hs_mode}:{selected_code}"
            cached_result = cache.get_cached_response(cache_key, intent="hs_code_lookup")
            if cached_result:
                context.set_result("retrieval", cached_result)
                context.status = WorkflowStatus.COMPLETED
                return

            async def run_call():
                return await asyncio.wait_for(
                    coordinator.retrieval_client.hs_code_lookup(
                        query=clean_query,
                        top_k=5,
                        generate_answer=True,
                        hs_mode=hs_mode,
                        selected_code=selected_code,
                        session_id=context.session_id
                    ),
                    timeout=timeout_sec
                )

            result = await coordinator._execute_service_call(
                context=context,
                service_name="retrieval",
                client_call_fn=run_call,
                request_payload={
                    "query": clean_query,
                    "top_k": 5,
                    "generate_answer": True,
                    "hs_mode": hs_mode,
                    "selected_code": selected_code,
                    "session_id": context.session_id
                }
            )

            # ---- Backstop Khmer translation (mirrors TradeQueryHandler) ----
            lang_tag = context.metadata.get("language") or getattr(context, "language", "en")
            if lang_tag == "km" and result and isinstance(result, dict):
                ans = result.get("final_answer") or result.get("answer") or ""
                if ans and not QueryTranslator.is_khmer(ans):
                    _translator = getattr(coordinator, "query_translator", None) or QueryTranslator(coordinator.llm_service)
                    try:
                        km_ans = await _translator.translate_to_khmer(ans)
                        result["final_answer"] = km_ans
                        result["answer"] = km_ans
                    except Exception as tr_err:
                        logger.warning(f"[{context.request_id}] Backstop Khmer translation failed (hs_lookup): {tr_err}")

            cache.cache_response(
                question=cache_key,
                response=result,
                intent="hs_code_lookup",
                ttl_seconds=24 * 3600,
                source="retrieval"
            )
            context.set_result("retrieval", result)
            context.status = WorkflowStatus.COMPLETED

            # ---- Product-spec clarification post-processing ----------------------
            if context.session_context:
                session = context.session_context
                is_generic = bool(result.get("is_generic"))
                current_round = getattr(session, "product_ask_back_count", 0)

                if is_generic and current_round < MAX_PRODUCT_ASK_BACK_RETRIES:
                    context.status = WorkflowStatus.CLARIFICATION_REQUIRED
                    


                    if current_round == 0:
                        # If the user's query is a pure HS code, preserve the clarification entity.
                        # Otherwise, allow them to update the entity if they provided a new one.
                        is_pure_hs = False
                        if context.original_input:
                            is_pure_hs = bool(re.match(r"^\s*(?:hs\s*code|hs)?\s*(?:\d{4}\.\d{2}(?:\.\d{2})?|\d{8}|\d{4})\s*$", context.original_input.lower()))
                        
                        entity = getattr(session, "clarification_entity", None) if is_pure_hs else None
                        if not entity:
                            if context.metadata.get("has_nlu_entity", False):
                                entity = context.metadata.get("nlu_entity") or context.original_input
                            else:
                                entity = extract_entity(context.original_input) or context.original_input
                    else:
                        entity = context.original_input

                    clarifying_questions = result.get("clarifying_questions") or []
                    category = detect_simple_product_category(entity or "")
                    expected_terms = coordinator._build_spec_expected_terms(clarifying_questions, category)
                    candidate_codes = []
                    for doc in (result.get("documents") or [])[:5]:
                        code = extract_hs_code(doc)
                        if code and code not in candidate_codes:
                            candidate_codes.append(code)

                    session.product_clarification_needed = True
                    session.clarification_entity = entity
                    session.clarification_last_query = context.original_input
                    session.clarification_expected_terms = expected_terms
                    session.clarification_candidate_codes = candidate_codes
                    session._trigger_change()
                    logger.info(
                        f"[{context.request_id}] [SPEC-MERGE] Result is generic — "
                        f"saved entity='{entity}', category='{category}', "
                        f"expected_terms={expected_terms[:8]}, candidate_codes={candidate_codes[:5]}"
                    )
                else:
                    if getattr(session, "product_clarification_needed", False) or current_round > 0:
                        coordinator._clear_product_clarification(session)
                        logger.info(
                            f"[{context.request_id}] [SPEC-MERGE] Specific result or cap reached "
                            "— cleared product clarification state."
                        )

                    resolved_code = result.get("hs_code") or result.get("selected_code")
                    if not is_generic and resolved_code:
                        session.hs_code = resolved_code
                        session.last_entity = session.last_entity or context.original_input
                        session._trigger_change()

        except Exception as e:
            context.add_error(f"HS code lookup service error: {str(e)}")
            from ..workflow import WorkflowStatus
            context.status = WorkflowStatus.FAILED
