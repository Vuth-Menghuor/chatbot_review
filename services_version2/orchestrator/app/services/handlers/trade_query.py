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
                translator = getattr(coordinator, "query_translator", None) or QueryTranslator(coordinator.llm_service)
                ans = result.get("final_answer") or result.get("answer") or ""
                if ans and not QueryTranslator.is_khmer(ans):
                    try:
                        km_ans = await translator.translate_to_khmer(ans)
                        result["final_answer"] = km_ans
                        result["answer"] = km_ans
                    except Exception as tr_err:
                        logger.warning(f"Failed backstop translation to Khmer: {tr_err}")
                try:
                    await translate_trade_payload_to_khmer(result, translator)
                except Exception as tr_err:
                    logger.warning(f"Failed structured fields translation to Khmer: {tr_err}")

            if is_escape_hatch and result and isinstance(result, dict):
                disclosed_defaults = []
                if not has_flow:
                    disclosed_defaults.append("**Import**" if lang_tag != "km" else "**នាំចូល**")
                if not has_time_period:
                    disclosed_defaults.append(f"**{datetime.now().year} (latest year)**" if lang_tag != "km" else f"**{datetime.now().year} (ឆ្នាំចុងក្រោយបង្អស់)**")
                if not has_partner_country:
                    disclosed_defaults.append("**All Countries**" if lang_tag != "km" else "**គ្រប់ប្រទេសទាំងអស់**")
                if disclosed_defaults:
                    if lang_tag == "km":
                        notice = f"_បង្ហាញស្ថិតិពាណិជ្ជកម្មដោយផ្អែកលើតម្លៃលំនាំដើម៖ {', '.join(disclosed_defaults)}。_\n\n"
                    else:
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


async def translate_trade_payload_to_khmer(result: dict, translator: QueryTranslator) -> None:
    """Translates table, visualization, and other structured fields in a trade query result to Khmer."""
    # 1. Translate table
    tbl = result.get("table")
    
    col_map = {
        "frequency": "ប្រេកង់",
        "freq": "ប្រេកង់",
        "period": "រយៈពេល",
        "hs_heading": "កូដ HS Heading",
        "hs_code": "កូដ HS",
        "hs_chapter": "ជំពូក HS",
        "trade_value": "តម្លៃពាណិជ្ជកម្ម (USD)",
        "flow": "ទិសដៅពាណិជ្ជកម្ម",
        "mode_of_transport": "មធ្យោបាយដឹកជញ្ជូន",
        "partner_country": "ប្រទេសដៃគូ",
        "net_weight": "ទម្ងន់សុទ្ធ (គីឡូក្រាម)",
        "growth_rate_pct": "អត្រាកំណើន (%)",
    }
    
    val_map = {
        "Other": "ផ្សេងៗ",
        "others": "ផ្សេងៗ",
        "other": "ផ្សេងៗ",
        "EXPORT": "នាំចេញ",
        "EXPORTING": "នាំចេញ",
        "EX": "នាំចេញ",
        "Exports": "នាំចេញ",
        "export": "នាំចេញ",
        "IMPORT": "នាំចូល",
        "IMPORTING": "នាំចូល",
        "IM": "នាំចូល",
        "Imports": "នាំចូល",
        "import": "នាំចូល",
        "A": "ប្រចាំឆ្នាំ",
        "M": "ប្រចាំខែ",
        "Q": "ប្រចាំត្រីមាស",
        "S": "ប្រចាំឆមាស",
        "Sea transport": "ការដឹកជញ្ជូនតាមផ្លូវសមុទ្រ",
        "Rail transport": "ការដឹកជញ្ជូនតាមផ្លូវដែក",
        "Road transport": "ការដឹកជញ្ជូនតាមផ្លូវគោក",
        "Air transport": "ការដឹកជញ្ជូនតាមផ្លូវអាកាស",
        "Postal": "ប្រៃសណីយ៍",
        "Multimodal": "ការដឹកជញ្ជូនពហុមធ្យោបាយ",
        "Fixed": "ថេរ",
        "Inland waterway": "ការដឹកជញ្ជូនតាមផ្លូវទឹកក្នុងស្រុក",
        "Other transport": "ការដឹកជញ្ជូនផ្សេងៗ",
        "Unknown": "មិនស្គាល់",
        "unknown": "មិនស្គាល់",
        "Annual": "ប្រចាំឆ្នាំ",
        "Monthly": "ប្រចាំខែ",
        "Quarterly": "ប្រចាំត្រីមាស",
    }
    
    country_map = {
        "China": "ប្រទេសចិន",
        "United States": "សហរដ្ឋអាមេរិក",
        "Vietnam": "ប្រទេសវៀតណាម",
        "Thailand": "ប្រទេសថៃ",
        "Japan": "ប្រទេសជប៉ុន",
        "Singapore": "ប្រទេសសិង្ហបុរី",
        "Germany": "ប្រទេសអាល្លឺម៉ង់",
        "Hong Kong": "ហុងកុង",
        "Canada": "ប្រទេសកាណាដា",
        "United Kingdom": "ចក្រភពអង់គ្លេស",
        "France": "ប្រទេសបារាំង",
        "South Korea": "ប្រទេសកូរ៉េខាងត្បូង",
        "Taiwan": "តៃវ៉ាន់",
        "Switzerland": "ប្រទេសស្វីស",
        "Italy": "ប្រទេសអ៊ីតាលី",
        "Spain": "ប្រទេសអេស្ប៉ាញ",
        "Australia": "ប្រទេសអូស្ត្រាលី",
        "India": "ប្រទេសឥណ្ឌា",
        "Malaysia": "ប្រទេសម៉ាឡេស៊ី",
        "Indonesia": "ប្រទេសឥណ្ឌូនេស៊ី",
        "Belgium": "ប្រទេសប៊ែលហ្សិក",
        "Netherlands": "ប្រទេសហូឡង់",
        "Cambodia": "ប្រទេសកម្ពុជា",
        "the EU": "សហភាពអឺរ៉ុប",
        "ASEAN": "អាស៊ាន",
    }
    
    viz_map = {
        "Trade Volume Ranking": "ចំណាត់ថ្នាក់ទំហំពាណិជ្ជកម្ម",
        "Trade Trend over Time": "និន្នាការពាណិជ្ជកម្មតាមពេលវេលា",
        "Trade Comparison Analysis": "ការវិភាគប្រៀបធៀបពាណិជ្ជកម្ម",
        "Trade Share Breakdown": "ការបែងចែកចំណែកពាណិជ្ជកម្ម",
        "Trade Growth Analysis": "ការវិភាគកំណើនពាណិជ្ជកម្ម",
        "Trade Balance Analysis": "ការវិភាគតុល្យភាពពាណិជ្ជកម្ម",
        "Trade Volume Summary": "សេចក្តីសង្ខេបទំហំពាណិជ្ជកម្ម",
        "Growth Rate (%) Not Available": "មិនមានទិន្នន័យអត្រាកំណើន (%)",
        "Trade Value (USD)": "តម្លៃពាណិជ្ជកម្ម (USD)",
        "Trade Value": "តម្លៃពាណិជ្ជកម្ម",
        "Net Weight (kg)": "ទម្ងន់សុទ្ធ (គីឡូក្រាម)",
        "Growth Rate (%)": "អត្រាកំណើន (%)",
        "Trade Balance": "តុល្យភាពពាណិជ្ជកម្ម",
        "Volume (kg)": "ទម្ងន់ (គីឡូក្រាម)",
    }
    
    async def translate_str(text: str) -> str:
        if not text or not text.strip():
            return text
        if QueryTranslator.is_khmer(text):
            return text
        # Skip translation for purely numeric, dates, codes, or punctuation values
        if not re.search(r"[a-zA-Z]", text):
            return text
        # Try direct mapping
        if text in val_map:
            return val_map[text]
        if text in country_map:
            return country_map[text]
        if text in viz_map:
            return viz_map[text]
        # Try lowercase check
        text_lower = text.lower().strip()
        if text_lower in val_map:
            return val_map[text_lower]
        if text_lower in country_map:
            return country_map[text_lower]
        if text_lower in viz_map:
            return viz_map[text_lower]
        # LLM Translation fallback
        try:
            translated = await translator.translate_to_khmer(text)
            if translated:
                return translated
        except Exception as e:
            logger.warning(f"Failed to translate '{text}' to Khmer: {e}")
        return text

    if isinstance(tbl, dict) and "columns" in tbl and "rows" in tbl:
        old_cols = tbl.get("columns") or []
        new_cols = []
        for col in old_cols:
            col_lower = col.lower().strip()
            translated_col = col_map.get(col_lower, col)
            if translated_col == col and not QueryTranslator.is_khmer(col):
                translated_col = await translate_str(col)
            new_cols.append(translated_col)
        tbl["columns"] = new_cols
        
        old_rows = tbl.get("rows") or []
        new_rows = []
        for row in old_rows:
            new_row = {}
            for k, v in row.items():
                k_lower = k.lower().strip()
                new_key = col_map.get(k_lower, k)
                if new_key == k and not QueryTranslator.is_khmer(k):
                    new_key = await translate_str(k)
                
                new_val = v
                if isinstance(v, str):
                    if k_lower == "partner_country":
                        if v in country_map:
                            new_val = country_map[v]
                        else:
                            new_val = await translate_str(v)
                    else:
                        new_val = await translate_str(v)
                new_row[new_key] = new_val
            new_rows.append(new_row)
        tbl["rows"] = new_rows

    viz = result.get("visualization")
    if isinstance(viz, dict):
        if "title" in viz and isinstance(viz["title"], str):
            viz["title"] = await translate_str(viz["title"])
            
        if "labels" in viz and isinstance(viz["labels"], list):
            new_labels = []
            for label in viz["labels"]:
                if isinstance(label, str):
                    new_labels.append(await translate_str(label))
                else:
                    new_labels.append(label)
            viz["labels"] = new_labels
            
        if "datasets" in viz and isinstance(viz["datasets"], list):
            for dataset in viz["datasets"]:
                if isinstance(dataset, dict) and "label" in dataset and isinstance(dataset["label"], str):
                    dataset["label"] = await translate_str(dataset["label"])

    for summary_key in ["summary", "summary_metrics"]:
        summary_obj = result.get(summary_key)
        if isinstance(summary_obj, dict) and "data_quality" in summary_obj:
            dq = summary_obj["data_quality"]
            if isinstance(dq, dict):
                if dq.get("partial_year_note"):
                    py = dq.get("partial_year")
                    if py:
                        dq["partial_year_note"] = f" ទិន្នន័យឆ្នាំ {py} មិនទាន់មានភាពពេញលេញនៅឡើយទេ។"
                    else:
                        match = re.search(r"The\s+(\d{4})\s+data\s+is\s+not\s+complete", dq["partial_year_note"], re.IGNORECASE)
                        if match:
                            dq["partial_year_note"] = f" ទិន្នន័យឆ្នាំ {match.group(1)} មិនទាន់មានភាពពេញលេញនៅឡើយទេ។"
                        else:
                            dq["partial_year_note"] = await translate_str(dq["partial_year_note"])

                if dq.get("truncation_note"):
                    shown_cnt = dq.get("shown_count")
                    if shown_cnt is not None:
                        dq["truncation_note"] = f"បង្ហាញលទ្ធផលចំនួន {shown_cnt} - ចំនួនសរុបដែលបានបង្ហាញអាចមិនតំណាងឱ្យទីផ្សារទាំងមូលឡើយ។"
                    else:
                        match = re.search(r"Showing\s+(\d+)\s+results", dq["truncation_note"], re.IGNORECASE)
                        if match:
                            dq["truncation_note"] = f"បង្ហាញលទ្ធផលចំនួន {match.group(1)} - ចំនួនសរុបដែលបានបង្ហាញអាចមិនតំណាងឱ្យទីផ្សារទាំងមូលឡើយ។"
                        else:
                            dq["truncation_note"] = await translate_str(dq["truncation_note"])

                if dq.get("period_coverage_note"):
                    actual_range = dq.get("actual_period_range")
                    requested_range = dq.get("requested_period_range")
                    if isinstance(actual_range, list) and len(actual_range) >= 2 and isinstance(requested_range, list) and len(requested_range) >= 2:
                        dq["period_coverage_note"] = f"ទិន្នន័យមានត្រឹមតែពីឆ្នាំ {actual_range[0]} ដល់ {actual_range[1]} ប៉ុណ្ណោះ (តាមការស្នើសុំឆ្នាំ {requested_range[0]}–{requested_range[1]})។"
                    else:
                        match = re.search(r"Data\s+available\s+from\s+(\d+)\s+to\s+(\d+)\s+only\s+\(requested\s+(\d+)–(\d+)\)", dq["period_coverage_note"], re.IGNORECASE)
                        if match:
                            dq["period_coverage_note"] = f"ទិន្នន័យមានត្រឹមតែពីឆ្នាំ {match.group(1)} ដល់ {match.group(2)} ប៉ុណ្ណោះ (តាមការស្នើសុំឆ្នាំ {match.group(3)}–{match.group(4)})។"
                        else:
                            dq["period_coverage_note"] = await translate_str(dq["period_coverage_note"])

                if dq.get("period_mismatch_note"):
                    req_p = dq.get("requested_period")
                    ret_p = dq.get("returned_period")
                    if req_p and ret_p:
                        dq["period_mismatch_note"] = f"សម្គាល់៖ ទិន្នន័យដែលបានស្នើសុំសម្រាប់ឆ្នាំ {req_p} ប៉ុន្តែបង្ហាញទិន្នន័យឆ្នាំ {ret_p} វិញ។"
                    else:
                        match = re.search(r"Requested\s+data\s+for\s+(\w+),\s+but\s+displaying\s+(\w+)\s+data", dq["period_mismatch_note"], re.IGNORECASE)
                        if match:
                            dq["period_mismatch_note"] = f"សម្គាល់៖ ទិន្នន័យដែលបានស្នើសុំសម្រាប់ឆ្នាំ {match.group(1)} ប៉ុន្តែបង្ហាញទិន្នន័យឆ្នាំ {match.group(2)} វិញ។"
                        else:
                            dq["period_mismatch_note"] = await translate_str(dq["period_mismatch_note"])

