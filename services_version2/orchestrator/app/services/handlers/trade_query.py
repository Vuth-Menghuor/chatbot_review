from __future__ import annotations
import asyncio
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List, Any

from prompts.dynamic_prompt_manager import DynamicPromptManager
from ..heuristics import _TRADE_COUNTRIES, MAX_PRODUCT_ASK_BACK_RETRIES
from ..translator import QueryTranslator
from ...utils import extract_entity

if TYPE_CHECKING:
    from ..coordinator import ServiceCoordinator
    from ..workflow import WorkflowContext

logger = logging.getLogger(__name__)
_prompt_manager = DynamicPromptManager()


class TradeQueryHandler:
    @staticmethod
    async def generate_trade_clarification_message(
        coordinator: ServiceCoordinator,
        query: str,
        missing_slots: List[str],
        product_name: str
    ) -> str:
        """Generates a friendly, conversational LLM message requesting missing mandatory trade parameters for trade queries."""
        missing_desc = ", ".join(missing_slots)
        fallback_msg = (
            f"To assist you with trade statistics for **{product_name}**, please specify the missing details: "
            + ", ".join(f"**{p}**" for p in missing_slots) + "."
        )

        if coordinator.llm_service and coordinator.llm_service.is_available():
            prompt = _prompt_manager.render(
                "generate_trade_clarification",
                query=query,
                product_name=product_name,
                missing_desc=missing_desc,
            )
            try:
                provider = coordinator.llm_service.router.providers.get("gemini")
                if provider and provider.is_available():
                    response = await asyncio.to_thread(
                        provider.client.models.generate_content,
                        model=provider.model_name,
                        contents=prompt,
                    )
                    content = (response.text or "").strip()
                    if content:
                        return content
            except Exception as e:
                logger.warning(f"LLM trade clarification generation failed: {e}")

        return fallback_msg

    @staticmethod
    async def handle(coordinator: ServiceCoordinator, context: WorkflowContext) -> None:
        try:
            from ..workflow import WorkflowStatus
            if not coordinator.trade_data_client:
                context.add_error("Trade data service not configured")
                context.status = WorkflowStatus.FAILED
                return
            
            service_query = coordinator._get_service_query(context)

            session_context = context.session_context
            current_text = (service_query or context.question or "").lower()

            def strip_negated_terms(text: str) -> str:
                if not text:
                    return text
                cleaned = re.sub(r"(?i)\b(?:not|no|instead of|other than)\s+[a-z0-9\s-]+\b(?=,|$|\band\b|\bor\b|\bbut\b)", "", text)
                cleaned = re.sub(r"(?i)\b[a-z0-9\s-]+\s+instead\b", "", cleaned)
                return cleaned.strip()

            cleaned_current = strip_negated_terms(current_text)

            layer1_slots = context.metadata.get("layer1_slots")
            slot_source = "layer1_structured"
            product_entity = None

            if isinstance(layer1_slots, dict) and layer1_slots:
                product_entity = layer1_slots.get("product")

            if not product_entity:
                if context.metadata.get("has_nlu_entity", False):
                    product_entity = context.metadata.get("nlu_entity")
                else:
                    slot_source = "local_regex_fallback"
                    logger.warning(f"[{context.request_id}] [SLOT_EXTRACTION] Degraded to local regex fallback")
                    product_entity = extract_entity(cleaned_current)

            if product_entity:
                p_low = product_entity.lower().strip()
                if any(kw in p_low for kw in ["trade data", "trade statistics", "trade volume", "trade flow", "tell me", "can you", "help me", "information", "compare", "comparison"]) or p_low in {"trade", "data", "import export", "import", "export"}:
                    product_entity = None

            context.metadata["slot_extraction_source"] = slot_source
            
            has_flow = any(f in cleaned_current for f in ["import", "export", "imported", "exported", "imports", "exports"])
            
            has_time_period = bool(
                re.search(
                    r"\b(19|20)\d{2}\b|\bq[1-4]\b|\bquarter\s+[1-4]\b|\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\b|\b(last|this|next)\s+(month|quarter|year)\b",
                    cleaned_current
                )
            )

            partner_countries = [c for c in _TRADE_COUNTRIES if c != "cambodia"]
            has_partner_country = any(re.search(rf"\b{re.escape(c)}\b", cleaned_current) for c in partner_countries)

            is_overall_trade_query = bool(re.search(
                r"\b(total\s+trade|overall\s+trade|total\s+volume|overall\s+volume|all\s+products?|no\s+specific\s+product|all\s+commodit|entire\s+trade|aggregate\s+trade|macro\s+trade|total\s+import|total\s+export|total\s+imports|total\s+exports)\b",
                cleaned_current
            ))

            is_ranking_query = bool(re.search(
                r"\b(top\s+\d+|top\s+ten|top\s+five|top\s+partners?|top\s+countries|top\s+commodit|top\s+products?|ranking|most\s+export|highest\s+export|most\s+import|highest\s+import)\b",
                cleaned_current
            ))

            ask_back_count = getattr(session_context, 'ask_back_count', 0) if session_context else 0
            is_escape_hatch = is_overall_trade_query or is_ranking_query or any(term in service_query.lower() for term in ["whatever", "idk", "don't know", "dont know", "any", "latest", "default", "overall", "total", "no specific"]) or ask_back_count >= MAX_PRODUCT_ASK_BACK_RETRIES

            missing_slots = []

            if missing_slots and not is_escape_hatch:
                product_name = product_entity or "the product"
                friendly_message = await TradeQueryHandler.generate_trade_clarification_message(
                    coordinator=coordinator,
                    query=service_query,
                    missing_slots=missing_slots,
                    product_name=product_name
                )
                logger.info(f"[{context.request_id}] Trade query missing mandatory parameters: {missing_slots}. Prompting user with LLM message.")
                
                EXPECTED_TERMS_MAP = {
                    "product": ["commodity name", "HS code", "e.g. rice, coffee, motor vehicle"],
                    "flow": ["import", "export"],
                    "trade_period": ["month", "quarter", "year", "date range", "e.g. Q1 2026, 2025, last month"],
                    "partner_country": ["trading partner country", "e.g. Thailand, China, Vietnam, USA"]
                }
                if session_context:
                    session_context.pending_clarification = True
                    session_context.clarification_intents = ["trade_query"]
                    session_context.clarification_entity = missing_slots
                    session_context.pending_rewritten_query = context.question
                    session_context.ask_back_count += 1
                    session_context._trigger_change()

                context.set_result("trade_query", {
                    "answer": friendly_message,
                    "clarification_required": True,
                    "missing_fields": missing_slots,
                    "metadata": {
                        "pending_clarification": True,
                        "clarification_entity": missing_slots,
                        "clarification_expected_terms": {s: EXPECTED_TERMS_MAP[s] for s in missing_slots if s in EXPECTED_TERMS_MAP},
                        "original_query": context.question,
                        "guard_triggered": "trade_mandatory_params"
                    }
                })
                context.status = WorkflowStatus.CLARIFICATION_REQUIRED
                return

            if session_context:
                session_context.pending_clarification = False
                session_context.clarification_intents = []
                session_context.ask_back_count = 0
                session_context._trigger_change()

            timeout_sec = min(
                coordinator.timeout_config.get_intent_timeout(context.intent),
                coordinator.timeout_config.get_service_timeout("trade_data")
            )

            query_to_send = service_query or context.question
            if not has_flow and not re.search(r"\b(import|export|imports|exports|imported|exported)\b", query_to_send.lower()):
                if re.search(r"\b(trade|trading)\s+partners?\b", query_to_send.lower()):
                    query_to_send = re.sub(r"\b(trade|trading)\s+partners?\b", "import partners", query_to_send, flags=re.IGNORECASE)
                else:
                    query_to_send = f"{query_to_send} import"

            LATEST_TRADE_YEAR = "2025"
            if not has_time_period and not re.search(r"\b(19|20)\d{2}\b", query_to_send.lower()):
                if re.search(r"\blatest\b", query_to_send, flags=re.IGNORECASE):
                    query_to_send = re.sub(r"\blatest\b", LATEST_TRADE_YEAR, query_to_send, flags=re.IGNORECASE)
                else:
                    query_to_send = f"{query_to_send} {LATEST_TRADE_YEAR}"
            elif re.search(r"\blatest\b", query_to_send, flags=re.IGNORECASE):
                query_to_send = re.sub(r"\blatest\b", LATEST_TRADE_YEAR, query_to_send, flags=re.IGNORECASE)

            # --- Trade Query Slots Diagnostic Logging ---
            raw_lower = (context.original_input or "").lower()
            rewritten_lower = (service_query or "").lower()
            final_lower = query_to_send.lower()

            # Year resolution
            raw_year_match = re.search(r"\b(19|20)\d{2}\b", raw_lower)
            rewritten_year_match = re.search(r"\b(19|20)\d{2}\b", rewritten_lower)
            if rewritten_year_match:
                year_val = rewritten_year_match.group(0)
                year_source = "user_input" if raw_year_match else "inherited_history"
            elif re.search(r"\b(19|20)\d{2}\b", final_lower):
                year_val = re.search(r"\b(19|20)\d{2}\b", final_lower).group(0)
                year_source = "default_fallback"
            else:
                year_val = "2025"
                year_source = "default_fallback"

            # Flow resolution
            raw_flow_match = re.search(r"\b(import|export|imports|exports|imported|exported)\b", raw_lower)
            rewritten_flow_match = re.search(r"\b(import|export|imports|exports|imported|exported)\b", rewritten_lower)
            if rewritten_flow_match:
                flow_val = rewritten_flow_match.group(0)
                flow_source = "user_input" if raw_flow_match else "inherited_history"
            elif re.search(r"\b(import|export|imports|exports|imported|exported)\b", final_lower):
                flow_val = re.search(r"\b(import|export|imports|exports|imported|exported)\b", final_lower).group(0)
                flow_source = "default_fallback"
            else:
                flow_val = "import"
                flow_source = "default_fallback"

            # Metric/Topic resolution
            raw_ranking = bool(re.search(r"\b(top\s+\d+|top\s+ten|top\s+five|top\s+partners?|top\s+countries|top\s+commodit|top\s+products?|ranking|most\s+export|highest\s+export|most\s+import|highest\s+import)\b", raw_lower))
            rewritten_ranking = bool(re.search(r"\b(top\s+\d+|top\s+ten|top\s+five|top\s+partners?|top\s+countries|top\s+commodit|top\s+products?|ranking|most\s+export|highest\s+export|most\s+import|highest\s+import)\b", rewritten_lower))
            raw_overall = bool(re.search(r"\b(total\s+trade|overall\s+trade|total\s+volume|overall\s+volume|all\s+products?|no\s+specific\s+product|all\s+commodit|entire\s+trade|aggregate\s+trade|macro\s+trade|total\s+import|total\s+export|total\s+imports|total\s+exports)\b", raw_lower))
            rewritten_overall = bool(re.search(r"\b(total\s+trade|overall\s+trade|total\s+volume|overall\s+volume|all\s+products?|no\s+specific\s+product|all\s+commodit|entire\s+trade|aggregate\s+trade|macro\s+trade|total\s+import|total\s+export|total\s+imports|total\s+exports)\b", rewritten_lower))

            metric_source = "user_input"
            if (rewritten_ranking and not raw_ranking) or (rewritten_overall and not raw_overall):
                metric_source = "inherited_history"
            else:
                raw_entity = extract_entity(raw_lower)
                rewritten_entity = extract_entity(rewritten_lower)
                if rewritten_entity and not raw_entity:
                    metric_source = "inherited_history"

            logger.info(
                f"[{context.request_id}] [TRADE_SLOTS_DIAGNOSTIC] "
                f"metric_source: {metric_source} | "
                f"flow: {flow_val} ({flow_source}) | "
                f"year: {year_val} ({year_source})"
            )

            lang_tag = context.metadata.get("language") or getattr(context, "language", "en")
            async def run_call():
                return await asyncio.wait_for(
                    coordinator.trade_data_client.query(query_to_send), timeout=timeout_sec
                )
                
            result = await coordinator._execute_service_call(
                context=context,
                service_name="trade_data",
                client_call_fn=run_call,
                request_payload={"question": query_to_send}
            )

            is_no_data = (
                isinstance(result, dict) and 
                (result.get("status") == "NO_DATA" or result.get("success") is False or "couldn't pull up" in (result.get("answer") or "").lower())
            )
            if is_no_data:
                fallback_q = re.sub(r"\btop\s+ten\b", "top 10", query_to_send, flags=re.IGNORECASE)
                fallback_q = re.sub(r"\btop\s+five\b", "top 5", fallback_q, flags=re.IGNORECASE)
                fallback_q = re.sub(r"\b(trade|trading)\s+partners?\b", "import partners", fallback_q, flags=re.IGNORECASE)
                fallback_q = re.sub(r"\s+", " ", fallback_q).strip()

                if fallback_q != query_to_send:
                    logger.info(f"[{context.request_id}] Trade query '{query_to_send}' returned NO_DATA. Attempting fallback retry: '{fallback_q}'")
                    try:
                        retry_res = await asyncio.wait_for(
                            coordinator.trade_data_client.query(fallback_q), timeout=timeout_sec
                        )
                        if isinstance(retry_res, dict) and retry_res.get("success") is not False and retry_res.get("status") != "NO_DATA":
                            logger.info(f"[{context.request_id}] Fallback trade query succeeded!")
                            result = retry_res
                    except Exception as retry_err:
                        logger.warning(f"[{context.request_id}] Trade query fallback retry failed: {retry_err}")

            lang_tag = context.metadata.get("language") or getattr(context, "language", "en")
            if lang_tag == "km" and result and isinstance(result, dict):
                ans = result.get("final_answer") or result.get("answer") or ""
                if ans and not QueryTranslator.is_khmer(ans):
                    translator = getattr(coordinator, "query_translator", None) or QueryTranslator(coordinator.llm_service)
                    try:
                        km_ans = await translator.translate_to_khmer(ans)
                        result["final_answer"] = km_ans
                        result["answer"] = km_ans
                    except Exception as tr_err:
                        logger.warning(f"Failed backstop translation to Khmer: {tr_err}")

            if is_escape_hatch and result and isinstance(result, dict):
                disclosed_defaults = []
                if not has_flow:
                    disclosed_defaults.append("**Import**")
                if not has_time_period:
                    disclosed_defaults.append(f"**{datetime.now().year} (latest year)**")
                if not has_partner_country:
                    disclosed_defaults.append("**All Countries**")
                if disclosed_defaults:
                    notice = f"_Showing trade statistics using assumed defaults: {', '.join(disclosed_defaults)}._\n\n"
                    orig_ans = result.get("final_answer") or result.get("answer") or ""
                    result["final_answer"] = notice + orig_ans
                    result["answer"] = notice + orig_ans

            context.set_result("trade_query", result)
            context.status = WorkflowStatus.COMPLETED
        except Exception as e:
            context.add_error(f"Trade data service error: {str(e)}")
            from ..workflow import WorkflowStatus
            context.status = WorkflowStatus.FAILED
