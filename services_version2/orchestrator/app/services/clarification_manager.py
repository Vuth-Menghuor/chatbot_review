from __future__ import annotations
import logging
import re
from typing import Optional, Any, TYPE_CHECKING

from ..utils import extract_entity
from .heuristics import (
    _TRADE_COUNTRIES,
    _CLARIFY_STOP_WORDS,
    _CLARIFY_GENERIC_NOUNS,
    _SPEC_DISCRIMINATORS,
    MAX_PRODUCT_ASK_BACK_RETRIES,
    Heuristics,
)

if TYPE_CHECKING:
    from .coordinator import ServiceCoordinator
    from .workflow import WorkflowContext

logger = logging.getLogger(__name__)


class ClarificationManager:
    @staticmethod
    def merge_pending_with_clarification(
        coordinator: ServiceCoordinator,
        pending_query: str,
        clarification_response: str,
        resolved_intent: str,
        session_last_entity: Optional[str] = None,
        session_context: Optional[Any] = None,
        was_clarification_pending: bool = False,
    ) -> str:
        """
        Assemble a usable query out of an incomplete fragment + the user's
        chosen intent from the ask-back round-trip.
        """
        if not was_clarification_pending:
            logger.warning("[MERGE] Attempted to merge query when clarification was not pending. Skipping merge.")
            return clarification_response or pending_query or ""

        try:
            # ---- Step 1: extract entity from the clarification response (the user's answer) ----
            entity = extract_entity(clarification_response) if clarification_response else None

            # ---- Step 2: fall back to the pending query fragment ----
            if entity is None and pending_query:
                entity = extract_entity(pending_query)

            # ---- Step 3: fall back to turn-1 entity held in session state ----
            if entity is None and session_last_entity:
                entity = session_last_entity

            # ---- Step 2.6: Perform pronoun replacement early ----
            response_lower = clarification_response.strip().lower()
            pronouns = ["its", "it", "that", "this", "these", "those"]
            pronoun_match = None
            for pronoun in pronouns:
                if response_lower.startswith(pronoun):
                    if len(response_lower) == len(pronoun) or response_lower[len(pronoun)].isspace() or response_lower[len(pronoun)] == '-':
                        pronoun_match = pronoun
                        break

            if pronoun_match and entity:
                clarification_response = clarification_response.replace(pronoun_match, entity, 1).strip()
                response_lower = clarification_response.lower()

            # Detect if user clarification response is just an intent keyword choice
            is_keyword_choice = False
            intent_whitelist_patterns = [
                r"^calculation$", r"^calculator$", r"^calculate$", r"^tax$", r"^duty$",
                r"^hs[-_\s]*code(?:[-_\s]*lookup)?$", r"^hs$", r"^code$", r"^lookup$",
                r"^classify$", r"^classification$",
                r"^trade[-_\s]*query$", r"^trade$", r"^trade[-_\s]*data$", r"^statistics$", r"^volume$",
                r"^general$", r"^general[-_\s]*question$", r"^definition$", r"^policy$", r"^procedure$"
            ]
            if any(re.match(pat, response_lower) for pat in intent_whitelist_patterns):
                is_keyword_choice = True

            if not is_keyword_choice and clarification_response and clarification_response.strip():
                if len(clarification_response) > len(pending_query or ""):
                    merged = clarification_response
                    if entity and entity.lower() not in merged.lower():
                        merged = f"{entity} {merged}"
                    if resolved_intent == "calculation" and not any(
                        phrase in merged.lower() for phrase in ["calculate", "import tax", "duty", "tariff"]
                    ):
                        merged = f"Calculate {merged}"
                    return merged

            product = entity or "goods"
            if resolved_intent == "calculation":
                cif_val = None
                currency = None
                origin = None
                hs_code = None
                
                try:
                    from ..infrastructure.clients import CalculatorServiceClient
                    latest_params = CalculatorServiceClient._parse_question_for_calculation(clarification_response)
                    cif_val = latest_params.get("cif_value")
                    currency = latest_params.get("currency")
                    origin = latest_params.get("origin_country")
                    hs_code = latest_params.get("hs_code")
                except Exception:
                    pass

                if session_context:
                    turns_to_check = []
                    if hasattr(session_context, "turns") and session_context.turns:
                        turns_to_check = [turn.get("user") or turn.get("user_input", "") for turn in reversed(session_context.turns)]
                    
                    last_norm = getattr(session_context, 'last_normalized_query', None)
                    if last_norm:
                        turns_to_check.insert(0, last_norm)
                        
                    for q in turns_to_check:
                        if not q:
                            continue
                        try:
                            from ..infrastructure.clients import CalculatorServiceClient
                            params = CalculatorServiceClient._parse_question_for_calculation(q)
                            if cif_val is None and params.get("cif_value") is not None:
                                cif_val = params.get("cif_value")
                                if not currency:
                                    currency = params.get("currency")
                            if not origin and params.get("origin_country"):
                                origin = params.get("origin_country")
                            if not hs_code and params.get("hs_code"):
                                hs_code = params.get("hs_code")
                        except Exception:
                            pass
                
                if not currency:
                    currency = "USD"
                if not origin:
                    origin = "Thailand"

                if hs_code and hs_code not in product:
                    product = f"{product} HS {hs_code}"

                if cif_val is not None:
                    cif_display = int(cif_val) if cif_val == int(cif_val) else cif_val
                    sym_map = {
                        "USD": "$", "KHR": "៛", "EUR": "€", "GBP": "£",
                        "CNY": "¥", "JPY": "¥", "THB": "฿", "VND": "₫",
                        "KRW": "₩", "INR": "₹"
                    }
                    cur_str = sym_map.get(currency, f"{currency} ")
                    return f"Calculate import tax for {product} {cur_str}{cif_display} from {origin}"
                else:
                    return f"Calculate import tax for {product}"

            elif resolved_intent == "hs_code_lookup":
                return f"What is the HS code for {product}?"

            elif resolved_intent == "trade_query":
                mode = None
                country_phrase = None
                year = None
                month = None

                if session_context and getattr(session_context, 'import_export_mode', None):
                    mode = session_context.import_export_mode

                texts_to_scan = []
                if clarification_response:
                    texts_to_scan.append(clarification_response)
                if pending_query:
                    texts_to_scan.append(pending_query)
                if session_context:
                    if getattr(session_context, 'last_normalized_query', None):
                        texts_to_scan.append(session_context.last_normalized_query)
                    if hasattr(session_context, "turns") and session_context.turns:
                        for turn in reversed(session_context.turns):
                            texts_to_scan.append(turn.get("user") or turn.get("user_input", ""))

                COUNTRIES = list(_TRADE_COUNTRIES)
                MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

                for t in texts_to_scan:
                    if not t:
                        continue
                    t_lower = t.lower()
                    
                    if not mode:
                        if "export" in t_lower:
                            mode = "export"
                        elif "import" in t_lower:
                            mode = "import"
                            
                    if not country_phrase:
                        country_pat = "|".join(COUNTRIES)
                        prep_match = re.search(r"\b(to|from|in|into|with|for)\s+(" + country_pat + r")\b", t_lower)
                        if prep_match:
                            country_phrase = prep_match.group(0)
                        else:
                            c_match = re.search(r"\b(" + country_pat + r")\b", t_lower)
                            if c_match:
                                country_name = c_match.group(1)
                                if mode == "export":
                                    country_phrase = f"to {country_name}"
                                elif mode == "import":
                                    country_phrase = f"from {country_name}"
                                else:
                                    country_phrase = f"with {country_name}"
                                    
                    if not year:
                        year_match = re.search(r"\b(20\d{2}|19\d{2})\b", t_lower)
                        if year_match:
                            year = year_match.group(1)
                        else:
                            rel_match = re.search(
                                r"\b(latest|recent|current|most\s+recent|latest\s+year|latest\s+month|q[1-4]\b|quarter\s+[1-4]\b|last\s+(?:month|quarter|year)|this\s+(?:month|quarter|year))\b",
                                t_lower
                            )
                            if rel_match:
                                year = rel_match.group(1)
                            
                    if not month:
                        month_pat = "|".join(MONTHS)
                        month_match = re.search(r"\b(" + month_pat + r")\b", t_lower)
                        if month_match:
                            month = month_match.group(1)

                mode = mode or "import"
                query_parts = [f"What are the {mode} statistics for {product}"]
                if country_phrase:
                    words = country_phrase.split()
                    if len(words) > 1:
                        words[1:] = [w.capitalize() for w in words[1:]]
                        country_phrase = " ".join(words)
                    else:
                        country_phrase = country_phrase.capitalize()
                    query_parts.append(country_phrase)
                
                time_parts = []
                if month:
                    time_parts.append(month.capitalize())
                if year:
                    time_parts.append(year)
                if time_parts:
                    prep = "in " if (time_parts[0].isdigit() or (len(time_parts) > 1 and time_parts[1].isdigit())) else "for "
                    query_parts.append(prep + " ".join(time_parts))
                
                return " ".join(query_parts) + "?"

            elif resolved_intent == "general":
                return f"Tell me about {product}"

            if clarification_response and clarification_response.strip() and entity:
                if entity.lower() not in clarification_response.lower():
                    return f"{entity} {clarification_response}"

            return pending_query if pending_query and pending_query.strip() else clarification_response or ""
        except Exception as e:
            logger.error(f"[MERGE] Unexpected error during merge: {str(e)}", exc_info=True)
            return clarification_response or ""

    @staticmethod
    def validate_merged_query(
        coordinator: ServiceCoordinator,
        merged_query: str,
        resolved_intent: str,
    ) -> bool:
        """
        Validates that a merged/combined query is substantive enough and contains 
        relevant keywords for the detected intent.
        """
        if not merged_query or not merged_query.strip() or len(merged_query.strip()) < 5:
            return False  
                
        if resolved_intent == "calculation":
            calc_keywords = ["tax", "duty", "tariff", "import", "cif", "value", "calculate", "cost"]
            if not any(kw in merged_query.lower() for kw in calc_keywords): 
                return False

        if resolved_intent == "hs_code_lookup":
            hs_keywords = ["hs code", "hs-code", "tariff code", "code", "ahtn", "harmonized code"]
            has_explicit_hs_keywords = any(kw in merged_query.lower() for kw in hs_keywords)
            looks_commercial = coordinator._looks_like_commercial_description(merged_query)

            if not (has_explicit_hs_keywords or looks_commercial): 
                return False

        return True

    @staticmethod
    async def try_merge_product_spec(
        coordinator: ServiceCoordinator,
        context: WorkflowContext,
        request_id: str,
        question: str,
        normalized_question: str,
        session_id: Optional[str],
    ) -> tuple[str, str]:
        """
        Attempt to merge an incoming user message with a saved product
        entity when the session is awaiting a spec clarification answer.
        """
        session = context.session_context
        stripped = question.strip()
        normalized = coordinator._light_normalize_query(stripped)
        input_tokens = set(re.findall(r"[a-z0-9]+", normalized))

        # ---- Guard 1: Small talk / explicit exit ---------------------------------
        small_talk_resp = await coordinator._detect_small_talk(normalized_question, llm_service=None)
        if small_talk_resp:
            logger.info(
                f"[{request_id}] [SPEC-MERGE] Small talk detected ('{stripped[:40]}') — "
                "resetting product clarification state."
            )
            context.metadata["small_talk_response"] = small_talk_resp
            ClarificationManager.clear_product_clarification(session)
            return question, normalized_question

        # ---- Guard 2: Retry cap --------------------------------------------------
        if session.product_ask_back_count >= MAX_PRODUCT_ASK_BACK_RETRIES:
            logger.info(
                f"[{request_id}] [SPEC-MERGE] Retry cap reached "
                f"({session.product_ask_back_count}/{MAX_PRODUCT_ASK_BACK_RETRIES}) — "
                "treating as fresh query."
            )
            ClarificationManager.clear_product_clarification(session)
            return question, normalized_question

        # ---- Guard 3: Dynamic relevance check -----------------------------------
        expected_terms = set(session.clarification_expected_terms or [])
        overlap = input_tokens & expected_terms
        if not overlap:
            if not expected_terms:
                logger.info(
                    f"[{request_id}] [SPEC-MERGE] No expected terms — accepting '{stripped[:40]}' "
                    "as spec answer (Guard 4 validates the merged result)."
                )
            else:
                logger.info(
                    f"[{request_id}] [SPEC-MERGE] Input '{stripped[:40]}' has no overlap "
                    f"with expected terms {list(expected_terms)[:6]} — resetting, treating as fresh query."
                )
                ClarificationManager.clear_product_clarification(session)
                return question, normalized_question
        else:
            logger.info(
                f"[{request_id}] [SPEC-MERGE] Matched expected terms: {list(overlap)}"
            )

        # ---- Guard 4: Validate merged query -------------------------------------
        entity = session.clarification_entity or ""
        merged = f"{entity} {stripped}".strip()
        if not ClarificationManager.validate_merged_query(coordinator, merged, "hs_code_lookup"):
            logger.info(
                f"[{request_id}] [SPEC-MERGE] Merged query '{merged[:60]}' failed "
                "validation — treating as fresh query."
            )
            ClarificationManager.clear_product_clarification(session)
            return question, normalized_question

        # ---- All guards passed — inject merged query ----------------------------
        logger.info(
            f"[{request_id}] [SPEC-MERGE] Merging '{entity}' + '{stripped}' "
            f"-> '{merged}' (round {session.product_ask_back_count + 1})"
        )
        session.product_ask_back_count += 1
        session.product_clarification_needed = False
        context.question = merged
        context.original_input = merged
        context.metadata["_spec_merge_done"] = True
        context.metadata["spec_merge_entity"] = entity
        context.metadata["spec_merge_answer"] = stripped
        session.last_entity = merged
        session._trigger_change()

        normalized_merged = coordinator._light_normalize_query(merged)
        return merged, normalized_merged

    @staticmethod
    def clear_product_clarification(session) -> None:
        """Reset all product-spec clarification state on the session."""
        session.product_clarification_needed = False
        session.clarification_entity = None
        session.clarification_last_query = None
        session.product_ask_back_count = 0
        session.clarification_expected_terms = []
        session._trigger_change()

    @staticmethod
    def build_spec_expected_terms(
        clarifying_questions: Optional[list],
        category: str,
    ) -> list:
        """
        Build the list of allowed response tokens that Step 2c will accept on the
        next user turn as a legitimate spec answer.
        """
        base = set(_SPEC_DISCRIMINATORS.get(category, frozenset()))
        if not clarifying_questions:
            return sorted(base)

        question_tokens: set = set()
        for q in clarifying_questions:
            for tok in re.findall(r"[a-z0-9]+", (q or "").lower()):
                if (
                    len(tok) > 2
                    and tok not in _CLARIFY_STOP_WORDS
                    and tok not in _CLARIFY_GENERIC_NOUNS
                ):
                    question_tokens.add(tok)

        return sorted(base | question_tokens)
