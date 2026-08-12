from __future__ import annotations
from sqlalchemy.engine import result
import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional, Any

from ...infrastructure.cache_service import get_cache_service
from ..translator import QueryTranslator


if TYPE_CHECKING:
    from ..coordinator import ServiceCoordinator
    from ..workflow import WorkflowContext

logger = logging.getLogger(__name__)


def is_genuine_product_desc(product: Optional[str], hs_code: Optional[str]) -> bool:
    if not product:
        return False
    prod_clean = str(product).strip().lower()
    # Check if there is at least one alphabetic letter
    has_alpha = any(c.isalpha() for c in prod_clean)
    if not has_alpha:
        return False
    
    # Extract digit sequence
    prod_digits = re.sub(r'[^0-9]', '', prod_clean)
    if hs_code and prod_digits:
        hs_digits = re.sub(r'[^0-9]', '', str(hs_code))
        # If the extracted digits exactly match the HS code, it's field-bleed
        if prod_digits == hs_digits:
            return False
            
    return True


def is_cif_value_plausible(cif_val: Any, currency: str) -> bool:
    try:
        val = float(cif_val)
        if val <= 0 or val > 100_000_000_000:
            return False
        # Currency-aware decimal constraints
        if str(currency).upper() == "KHR":
            if round(val) != val:
                return False
        else:
            if round(val, 2) != val:
                return False
        return True
    except (TypeError, ValueError):
        return False


class CalculationHandler:
    @staticmethod
    def _has_open_hs_clarification(session_context: Optional[Any]) -> bool:
        if not session_context:
            return False
        return bool(
            getattr(session_context, "product_clarification_needed", False)
            and getattr(session_context, "clarification_entity", None)
        )

    @staticmethod
    async def enrich_calculation_query_from_context(
        coordinator: ServiceCoordinator,
        service_query: str,
        session_context: Optional[Any],
        nlu_entity: Optional[str] = None,
        nlu_entity_confidence: Optional[str] = None,
        original_input: Optional[str] = None,
    ) -> str:
        """Enrich a calculation query with missing CIF value, origin country, or HS code from
        session context/history.

        Price detection uses a two-tier approach:
        1. Regex — catches common numeric formats and multiplier shorthands.
        2. LLM fallback (Gemini) — handles natural-language prices that regex misses
           (e.g. "half a million", "a couple grand", "around 2 bil").
        """
        if not session_context:
            return service_query

        q_lower = service_query.lower()

        # 1. Extract explicit HS code from the query and update session.
        # Prioritize the original/raw user input to avoid picking up stale/concatenated
        # HS codes introduced by LLM rewrite merges.
        query_hs = None
        target_text = (original_input or service_query).lower()
        explicit_match = re.search(
            r"\b(?:hs\s*code|hs)\s*(\d{4}(?:\.\d{2}){0,2}|\d{6}|\d{8})\b",
            target_text,
        )
        if explicit_match:
            query_hs = explicit_match.group(1).strip()
        if not query_hs:
            bare_match = re.search(r"\b(\d{4}\.\d{2}(?:\.\d{2})?)\b", target_text)
            if bare_match:
                query_hs = bare_match.group(1).strip()

        if query_hs:
            if query_hs.isdigit():
                if len(query_hs) == 8:
                    query_hs = f"{query_hs[:4]}.{query_hs[4:6]}.{query_hs[6:8]}"
                elif len(query_hs) == 6:
                    query_hs = f"{query_hs[:4]}.{query_hs[4:6]}"
            else:
                query_hs = query_hs.replace(" ", ".")
            session_context.hs_code = query_hs
            session_context._trigger_change()

        # 2. Price detection — Tier 1: regex
        #
        # Supported formats (amount + currency marker, in either order):
        #   Symbols : $ ¥ € £ ฿
        #   ISO     : USD KHR THB EUR GBP CNY JPY VND SGD MYR
        #   Suffixes: k/K/thousand  m/M/mil/million  b/B/bil/billion  t/T/tril/trillion
        _MULT = (
            r'(?:'
            r'thousand|million|billion|trillion'
            r'|mil(?:lion)?|bil(?:lion)?|tril(?:lion)?|bn'
            r'|[kKmMbBtT]'
            r')'
        )
        _NUM = r'[\d,]+(?:\.\d+)?'
        _AMT = rf'{_NUM}(?:\s*{_MULT})?'     # e.g. 10k  1.5 million  2,000
        _SYM = r'[$¥€£฿]'
        _ISO = r'(?:usd|khr|thb|eur|gbp|cny|jpy|vnd|sgd|myr)'

        _PRICE_DETECT_RE = re.compile(
            rf'(?:'
            rf'{_SYM}\s*{_AMT}'           # $10k  $1.5 million  $10,000
            rf'|{_AMT}\s*{_SYM}'           # 10k$  1 million $
            rf'|{_AMT}\s*{_ISO}\b'         # 10k USD  1.5 mil KHR
            rf'|{_ISO}\s*{_AMT}'           # USD 10k  KHR 1000
            rf'|\b(?:cif|fob|cost|value|price)\s*{_AMT}\b' # cif 40000, fob 10500
            rf'|\b{_AMT}\s*(?:cif|fob)\b' # 40000 cif
            rf')',
            re.IGNORECASE,
        )
        _price_match = _PRICE_DETECT_RE.search(q_lower)
        has_explicit_price = bool(_price_match)

        # 3.a Price detection — Tier 2: LLM fallback
        #    Fires only when the regex found nothing, so there is no latency
        #    cost for normal well-formatted queries.
        llm_price_amount: Optional[float] = None
        llm_price_currency: Optional[str] = None

        if not has_explicit_price:
            try:
                from prompts.dynamic_prompt_manager import DynamicPromptManager
                _pm = DynamicPromptManager()
                gemini_provider = (
                    coordinator.llm_service.router.providers.get("gemini")
                    if coordinator.llm_service and hasattr(coordinator.llm_service, "router")
                    else None
                )
                if gemini_provider and gemini_provider.is_available():
                    import asyncio as _asyncio
                    import json as _json
                    prompt = _pm.render("extract_price_from_query", query=service_query)
                    response = await _asyncio.to_thread(
                        gemini_provider.client.models.generate_content,
                        model=gemini_provider.model_name,
                        contents=prompt,
                    )
                    raw_json = (response.text or "").strip()
                    # Strip markdown code fences if the model wrapped the JSON
                    raw_json = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw_json, flags=re.IGNORECASE).strip()
                    parsed = _json.loads(raw_json)
                    if parsed.get("amount") is not None:
                        llm_price_amount = float(parsed["amount"])
                        llm_price_currency = (parsed.get("currency") or "").upper() or None
                        has_explicit_price = True
                        logger.info(
                            f"[Price LLM] Extracted amount={llm_price_amount} "
                            f"currency={llm_price_currency} from '{service_query}'"
                        )
            except Exception as _e:
                logger.debug(f"[Price LLM] Fallback skipped: {_e}")

        """
        3.b. Entity-change gurde
         Session slots (origin, hs_code, cif) belong to whatever product
         was last being discussed. If the current query is about a
         *different* product than the one stored in session context,
         those slots are stale and must NOT be backfilled — this is
         what caused "calculate import tax iphone" -> "... from Car"
         (origin_country slot leaked from a prior car query).
         
        """
        session_product = (
            getattr(session_context, 'commercial_description', None)
            or getattr(session_context, 'product_category', None)
        )

        from app.utils.entity_utils import is_entity_changed
        entity_changed = is_entity_changed(session_product, nlu_entity) 

        if entity_changed:
            logger.info(
                f"[{getattr(session_context, 'session_id', 'session')}] "
                f"[ENTITY-GUARD] Product changed from '{session_product}' — "
                f"clearing stale origin/hs_code/cif before enrichment"
            )
            session_context.origin_country = None
            session_context.hs_code = None
            session_context.cif_value = None

        # 4. Session slot backfill from history
        has_origin = any(
            c in q_lower
            for c in [
                "china", "cambodia", "thailand", "vietnam", "laos", "japan",
                "korea", "singapore", "malaysia", "indonesia", "philippines",
                "usa", "us", "germany", "france", "uk", "india", "cn",
            ]
        )
        has_hs_code = bool(re.search(r"\b\d{4}\.\d{2}(?:\.\d{2})?\b", q_lower))

        cif_val = getattr(session_context, 'cif_value', None)
        currency = getattr(session_context, 'currency', None)
        origin = getattr(session_context, 'origin_country', None)
        hs_code = getattr(session_context, 'hs_code', None)
        product = (
            getattr(session_context, 'commercial_description', None)
            or getattr(session_context, 'product_category', None)
            or getattr(session_context, 'last_entity', None)
            or (nlu_entity if nlu_entity_confidence in ("high", "medium") else None)
        )

        if not cif_val or not origin or not hs_code or not currency:
            has_confirmed_hs = bool(session_context and getattr(session_context, "hs_code", None))
            # Detect an explicit HS code in the current query using two distinct patterns:
            # (a) Prefixed: "hs 8703.22.00", "hs code 87032200", "hs8703.22.00" (no space)
            # (b) Unprefixed but dotted: "8703.22.00" — the dots make it unambiguous as HS,
            #     unlike bare 8-digit numbers which could be CIF values or other numbers.
            # Bare 8-digit numbers WITHOUT dots are intentionally excluded from (b) to avoid
            # false-positiving on CIF values like "40000000" or DQ percentages.
            has_explicit_hs_in_query = bool(
                re.search(r'\bhs\s*(?:code)?\s*\d{4,8}', q_lower)  # prefixed form (any spacing)
                or re.search(r'\b\d{4}\.\d{2}(?:\.\d{2})?\b', q_lower)  # dotted form (unambiguous)
            )
            is_unresolved = not (has_confirmed_hs or has_explicit_hs_in_query)

            turns_to_check = []
            if hasattr(session_context, "turns") and session_context.turns:
                turns_to_check = [
                    t.get("user") or t.get("user_input", "")
                    for t in reversed(session_context.turns)
                ]
            # Always prepend last_normalized_query so CIF / origin / currency from the
            # previous turn can still be inherited into follow-up queries.  Only the
            # HS code backfill line (below) is guarded by has_explicit_hs_in_query,
            # so switching HS codes never bleeds in the old code while other inherited
            # slots remain available.
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
                    if not currency and params.get("currency"):
                        currency = params.get("currency")
                    if not origin and params.get("origin_country"):
                        origin = params.get("origin_country")
                    # Guard: only backfill HS from history when the current query does NOT
                    # already supply its own HS code.  When has_explicit_hs_in_query is True
                    # the user has provided a new HS this turn; pulling from history would
                    # produce a duplicate/stale second code alongside the intended one.
                    if not hs_code and params.get("hs_code") and not is_unresolved and not has_explicit_hs_in_query:
                        hs_code = params.get("hs_code")
                    if not product and params.get("product_name"):
                        product = params.get("product_name")
                except Exception:
                    pass
            if not currency:
                currency = "USD"

        # 5. Helper: expand shorthand multiplier in a regex-matched token
        _MULT_MAP = {
            'thousand': 1_000, 'k': 1_000,
            'million': 1_000_000, 'mil': 1_000_000, 'm': 1_000_000,
            'billion': 1_000_000_000, 'bil': 1_000_000_000, 'b': 1_000_000_000, 'bn': 1_000_000_000,
            'trillion': 1_000_000_000_000, 'tril': 1_000_000_000_000, 't': 1_000_000_000_000,
        }
        _CURR_MAP = [
            ('$', 'USD'), ('¥', 'JPY'), ('€', 'EUR'), ('£', 'GBP'), ('฿', 'THB'),
        ]
        _ISO_MAP = [
            ('usd','USD'),('khr','KHR'),('thb','THB'),('eur','EUR'),
            ('gbp','GBP'),('cny','CNY'),('jpy','JPY'),('vnd','VND'),
            ('sgd','SGD'),('myr','MYR'),
        ]

        def _parse_price_token(token: str):
            """Return (amount: int|float, currency: str) from a matched price token."""
            t = token.strip()
            # currency
            cur = None
            for sym, iso in _CURR_MAP:
                if sym in t:
                    cur = iso
                    break
            for tok, iso in _ISO_MAP:
                if re.search(r'(?<![a-z])' + tok + r'\b', t, re.IGNORECASE):
                    cur = iso
                    break
            # amount with optional multiplier suffix
            nm = re.search(
                r'([\d,]+(?:\.\d+)?)\s*(thousand|million|billion|trillion|mil(?:lion)?|bil(?:lion)?|bn|tril(?:lion)?|[kKmMbBtT])?',
                t.replace(',', ''),
            )
            if not nm:
                return None, cur
            val = float(nm.group(1))
            sfx = (nm.group(2) or '').strip().lower()
            val *= _MULT_MAP.get(sfx, 1)
            return (int(val) if val == int(val) else val), cur

        # 6. Build enriched query
        # ---------------------------------------------------------
        # If the rewritten query is already a well-formed calculation
        # sentence, DON'T rebuild it from scratch — just append the
        # slots that are genuinely missing (CIF, origin).
        # Rebuilding causes double-prefix like:
        #   "calculate import tax for calculate import tax for iPhone"
        # ---------------------------------------------------------
        _CALC_PREFIX_RE = re.compile(
            r'^(?:calculate|compute|what(?:\'s|\s+is)\s+(?:the\s+)?import|how\s+much)',
            re.IGNORECASE,
        )
        query_is_well_formed = bool(_CALC_PREFIX_RE.match(q_lower.strip()))

        is_follow_up_fragment = bool(
            re.search(r'\buse\b', q_lower)
            or re.search(r'\bprovided\b', q_lower)
            or not has_explicit_price
            or len(q_lower.split()) <= 6
        )

        if (
            not is_follow_up_fragment
            and has_explicit_price
            and (has_origin or not origin)
            and (has_hs_code or not hs_code)
        ):
            return service_query

        session_cif_valid = cif_val and float(cif_val) > 0
        cif_to_use = cif_val if (not has_explicit_price and session_cif_valid) else None

        # Slots to append (CIF and/or origin)
        slot_parts = []
        if cif_to_use is not None:
            cif_display = int(cif_to_use) if cif_to_use == int(cif_to_use) else cif_to_use
            slot_parts.append(f"CIF {cif_display} {currency}")
        elif has_explicit_price:
            if llm_price_amount is not None:
                eff_cur = llm_price_currency or currency or 'USD'
                slot_parts.append(f"CIF {llm_price_amount} {eff_cur}")
            elif _price_match:
                amount, inline_cur = _parse_price_token(_price_match.group(0))
                if amount is not None:
                    eff_cur = inline_cur or currency or 'USD'
                    slot_parts.append(f"CIF {amount} {eff_cur}")

        origin_to_use = origin if not has_origin else None
        if origin_to_use:
            slot_parts.append(f"from {origin_to_use}")

        if query_is_well_formed:
            # The rewritten query is already a proper sentence.
            # Just append any missing slots and return it.
            enriched = (service_query.rstrip() + (" " + " ".join(slot_parts) if slot_parts else "")).strip()
        else:
            # Build from scratch: assemble a canonical calculation sentence.
            # Rule: if HS code is known, always use it — NEVER use product name alongside it.
            # Product name only appears when there is no HS code at all.
            parts = ["calculate import tax"]
            if hs_code:
                parts.append(f"for HS {hs_code}")
            elif product:
                parts.append(f"for {product}")
            else:
                parts.append(f"for {service_query}")
            parts.extend(slot_parts)
            enriched = " ".join(parts)

        logger.info(
            f"[{getattr(session_context, 'session_id', 'session')}] "
            f"Enriched calculation query from context: '{service_query}' -> '{enriched}'"
        )
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

            session_context = context.session_context
            open_hs_clarification = CalculationHandler._has_open_hs_clarification(session_context)
            is_clarification_resolution = bool(context.metadata and context.metadata.get("clarification_resolved"))

            # --- HS Clarification Resolution (BEFORE enrichment) ---
            # The enricher's CIF-value regex can greedily match HS code digits
            # (e.g. 8703.23 in "HS 8703.23.21 CIF 8000") and strip the real HS
            # code from the query.  We must extract explicit_hs from the raw
            # query FIRST so clarification resolution is not defeated.
            if open_hs_clarification and session_context:
                candidate_codes = list(getattr(session_context, "clarification_candidate_codes", []) or [])
                raw_q_lower = raw_service_query.lower()
                explicit_hs = None
                # Primary: "hs <code>" or "hs code <code>"
                explicit_match = re.search(
                    r"\b(?:hs\s*code|hs)\s*(\d{4}(?:\.\d{2}){0,2}|\d{6}|\d{8})\b",
                    raw_q_lower
                )
                if explicit_match:
                    explicit_hs = explicit_match.group(1).strip()
                # Fallback: bare dotted HS code anywhere in the raw query (e.g. "8703.23.21")
                if not explicit_hs:
                    bare_match = re.search(r"\b(\d{4}\.\d{2}(?:\.\d{2})?)\b", raw_service_query)
                    if bare_match:
                        explicit_hs = bare_match.group(1).strip()

                # Normalise digit-only codes into dotted form
                if explicit_hs and explicit_hs.isdigit():
                    if len(explicit_hs) == 8:
                        explicit_hs = f"{explicit_hs[:4]}.{explicit_hs[4:6]}.{explicit_hs[6:8]}"
                    elif len(explicit_hs) == 6:
                        explicit_hs = f"{explicit_hs[:4]}.{explicit_hs[4:6]}"
                elif explicit_hs:
                    explicit_hs = explicit_hs.replace(" ", ".")

                matched_candidate = None
                if explicit_hs:
                    norm_explicit = explicit_hs.replace(".", "").replace(" ", "").strip()
                    for cand in candidate_codes:
                        if cand.replace(".", "").replace(" ", "").strip() == norm_explicit:
                            matched_candidate = cand
                            break
                    if not matched_candidate and norm_explicit.isdigit() and len(norm_explicit) >= 8:
                        matched_candidate = explicit_hs

                if matched_candidate:
                    # User confirmed a valid candidate — resolve clarification and proceed
                    session_context.hs_code = matched_candidate
                    session_context.product_clarification_needed = False
                    session_context.clarification_entity = None
                    session_context.clarification_candidate_codes = []
                    session_context._trigger_change()
                    logger.info(
                        f"[{context.request_id}] HS clarification resolved from raw query: {matched_candidate!r}"
                    )
                    open_hs_clarification = False  # allow calculation to proceed
                elif explicit_hs or candidate_codes:
                    logger.info(
                        f"[{context.request_id}] Calculation blocked by open HS clarification: "
                        f"explicit_hs={explicit_hs!r}, candidate_codes={candidate_codes[:5]}"
                    )
                    product_name = (
                        getattr(session_context, 'clarification_entity', None)
                        or getattr(session_context, 'commercial_description', None)
                        or getattr(session_context, 'product_category', None)
                        or "this product"
                    )
                    context.set_result("calculation", {
                        "answer": (
                            f"I still need the HS code for **{product_name}** before I can calculate the import duty. "
                            "Please confirm one of the previously returned HS candidates or continue the HS lookup first."
                        ),
                        "clarification_required": True,
                        "missing_fields": ["hs_code"]
                    })
                    context.status = WorkflowStatus.CLARIFICATION_REQUIRED
                    session_context.set_pending_clarification(
                        candidate_intents=["hs_code_lookup", "calculation"],
                        rewritten_query=context.question
                    )
                    return

            # Enrich AFTER HS clarification is resolved so the enricher sees the
            service_query = await CalculationHandler.enrich_calculation_query_from_context(
                coordinator,
                raw_service_query,
                context.session_context,
                context.metadata.get("nlu_entity") if context.metadata else None,
                context.metadata.get("nlu_entity_confidence") if context.metadata else None,
                original_input=context.original_input
            )
            cif_val = getattr(session_context, 'cif_value', None) if session_context else None
            q_lower = service_query.lower()

            # ------------------------------------------------------------------ #
            # UNIFIED SEQUENTIAL SLOT-COLLECTION GATE
            #
            # Mandatory slots for a calculation:
            #   1. hs_code  — confirmed HS code (from session or explicit in query)
            #   2. cif_value — the purchase price (from session or explicit in query)
            #
            # Priority: ask for HS code first, then CIF.
            # Each turn we ask for exactly ONE missing slot, store remaining
            # missing slots in session_context.calc_slot_collection, and return
            # CLARIFICATION_REQUIRED.  When all slots are filled we clear the
            # collection state and proceed to the calculator.
            # ------------------------------------------------------------------ #

            # --- Detect what is available RIGHT NOW in this enriched query ---
            has_explicit_price = bool(re.search(
                r'(?:'
                r'\$\s*[\d,]+(?:\.\d+)?[kKmMbBtT]?'
                r'|[\d,]+(?:\.\d+)?[kKmMbBtT]?\s*\$'
                r'|[\d,]+(?:\.\d+)?[kKmMbBtT]?\s*(?:usd|khr|thb|eur|gbp|cny|jpy|vnd|sgd|myr)\b'
                r'|(?:usd|khr|thb|eur|gbp|cny|jpy|vnd|sgd|myr)\s*[\d,]+(?:\.\d+)?[kKmMbBtT]?'
                r'|\b(?:cif|fob|cost|value|price)\s*[\d,]+(?:\.\d+)?[kKmMbBtT]?\b'
                r'|\b[\d,]+(?:\.\d+)?[kKmMbBtT]?\s*(?:cif|fob)\b'
                r')',
                q_lower,
                re.IGNORECASE,
            ))
            cif_is_valid = bool(cif_val and float(cif_val) > 0)
            has_confirmed_hs = bool(session_context and getattr(session_context, "hs_code", None))
            has_explicit_hs_in_query = bool(
                re.search(r"\b(?:hs\s*code|hs)?\s*(\d{4}(?:\.\d{2}){0,2}|\d{6}|\d{8})\b", q_lower)
            )

            # Check if product description itself is missing
            has_product = bool(
                getattr(session_context, 'commercial_description', None) or
                getattr(session_context, 'product_category', None) or
                getattr(session_context, 'last_entity', None) or
                (
                    context.metadata and context.metadata.get("nlu_entity")
                    and context.metadata.get("nlu_entity_confidence") in ("high", "medium")
                )
            )

            # Diagnostics: log slot sources for debugging and stress-testing
            product_source = "missing"
            if getattr(session_context, 'commercial_description', None) or getattr(session_context, 'product_category', None) or getattr(session_context, 'last_entity', None):
                product_source = f"session_slot (value: {getattr(session_context, 'commercial_description', None) or getattr(session_context, 'product_category', None) or getattr(session_context, 'last_entity', None)})"
            elif context.metadata and context.metadata.get("nlu_entity") and context.metadata.get("nlu_entity_confidence") in ("high", "medium"):
                product_source = f"nlu_entity (value: {context.metadata.get('nlu_entity')})"

            hs_source = "missing"
            if has_confirmed_hs:
                hs_source = f"session_slot (value: {getattr(session_context, 'hs_code')})"
            elif has_explicit_hs_in_query:
                hs_source = "regex_backstop"

            cif_source = "missing"
            if cif_is_valid:
                cif_source = f"session_slot (value: {cif_val})"
            elif has_explicit_price:
                cif_source = "regex_backstop"

            logger.info(
                f"[{context.request_id}] [SLOTS_DIAGNOSTIC] "
                f"product: {product_source} | "
                f"hs_code: {hs_source} | "
                f"cif_value: {cif_source}"
            )

            # Build the list of STILL-missing mandatory slots (in ask-order)
            missing_slots: list = []
            if not has_product and not (has_confirmed_hs or has_explicit_hs_in_query):
                missing_slots.append("product")
            if not (has_confirmed_hs or has_explicit_hs_in_query):
                missing_slots.append("hs_code")
            if not (cif_is_valid or has_explicit_price):
                missing_slots.append("cif_value")

            # Merge any previously tracked missing list with current evaluation
            # (removes slots the user just provided)
            if session_context and session_context.calc_slot_collection:
                prior_missing = session_context.calc_slot_collection.get("missing", [])
                # Keep only those that are STILL missing
                missing_slots = [s for s in prior_missing if s in missing_slots]

            # Cold-start shortcut: if NLU already produced a combined clarification prompt
            # and the session has ZERO prior calculation signal (fresh conversation, no
            # product/hs/cif at all), use it directly instead of the slot-by-slot flow.
            nlu_cache = (context.metadata or {}).get("nlu_unified_result") or {}
            is_cold_start = (
                not has_product
                and not (has_confirmed_hs or has_explicit_hs_in_query)
                and not (cif_is_valid or has_explicit_price)
            )
            if is_cold_start and nlu_cache.get("suggested_clarification_prompt"):
                logger.info(f"[{context.request_id}] Cold-start calculation query: using NLU suggested_clarification_prompt.")
                if session_context:
                    session_context.calc_slot_collection = {
                        "missing": missing_slots,
                        "original_query": raw_service_query,
                    }
                    session_context._trigger_change()
                    session_context.set_pending_clarification(
                        candidate_intents=["calculation"],
                        rewritten_query=context.question,
                    )
                context.set_result("calculation", {
                    "answer": nlu_cache["suggested_clarification_prompt"],
                    "clarification_required": True,
                    "missing_fields": missing_slots,
                })
                context.status = WorkflowStatus.CLARIFICATION_REQUIRED
                return

            if missing_slots:
                # Ask for the FIRST missing slot in the list
                next_slot = missing_slots[0]
                remaining_after = missing_slots[1:]  # will ask for these next turns

                # Helper: extract product display name for friendly messages
                def _product_label() -> str:
                    if session_context:
                        label = (
                            getattr(session_context, 'clarification_entity', None)
                            or getattr(session_context, 'commercial_description', None)
                            or getattr(session_context, 'product_category', None)
                            or getattr(session_context, 'last_entity', None)
                            or (
                                context.metadata.get("nlu_entity")
                                if (context.metadata and context.metadata.get("nlu_entity_confidence") in ("high", "medium"))
                                else None
                            )
                        )
                        if label:
                            return label
                    cleaned = re.sub(
                        r"(?i)\b(calculate|compute|how|about|the|tax|taxes|duty|duties|import|export|for|cbu|ckd|hs|code)\b",
                        "",
                        service_query,
                    ).strip()
                    cleaned = re.sub(r"\s+", " ", cleaned).strip()
                    return cleaned or "this product"

                if next_slot == "product":
                    logger.info(f"[{context.request_id}] Slot collection: asking for product.")
                    if session_context:
                        session_context.calc_slot_collection = {
                            "missing": missing_slots,
                            "original_query": raw_service_query,
                        }
                        session_context._trigger_change()
                        session_context.set_pending_clarification(
                            candidate_intents=["calculation"],
                            rewritten_query=context.question,
                        )
                    answer = (
                        "To calculate the import tax, I need to know what product or item you are importing. "
                        "Could you please tell me what you are importing?"
                    )

                elif next_slot == "hs_code":
                    logger.info(f"[{context.request_id}] Slot collection: asking for hs_code.")
                    product_name = _product_label()

                    # Run HS lookup so we can show candidate codes
                    try:
                        from ...utils import clean_hs_query_for_retrieval
                        clean_query = clean_hs_query_for_retrieval(product_name)
                        timeout_sec = min(
                            coordinator.timeout_config.get_intent_timeout(context.intent),
                            coordinator.timeout_config.get_service_timeout("retrieval"),
                        )
                        async def _run_lookup():
                            return await asyncio.wait_for(
                                coordinator.retrieval_client.hs_code_lookup(
                                    query=clean_query,
                                    top_k=5,
                                    generate_answer=True,
                                    hs_mode="best",
                                    session_id=context.session_id,
                                ),
                                timeout=timeout_sec,
                            )
                        lookup_result = await coordinator._execute_service_call(
                            context=context,
                            service_name="retrieval",
                            client_call_fn=_run_lookup,
                            request_payload={"query": clean_query, "top_k": 5, "generate_answer": True,
                                             "hs_mode": "best", "session_id": context.session_id},
                        )
                        candidate_codes = []
                        if lookup_result and isinstance(lookup_result, dict):
                            from ..hs_classifier import extract_hs_code
                            for doc in (lookup_result.get("documents") or [])[:5]:
                                code = extract_hs_code(doc)
                                if code and code not in candidate_codes:
                                    candidate_codes.append(code)
                        if not candidate_codes:
                            candidate_codes = []
                    except Exception:
                        candidate_codes = []

                    if session_context:
                        session_context.product_clarification_needed = True
                        session_context.clarification_entity = product_name
                        session_context.clarification_last_query = context.original_input
                        session_context.clarification_candidate_codes = candidate_codes
                        session_context.calc_slot_collection = {
                            "missing": missing_slots,   # full list incl. current
                            "original_query": raw_service_query,
                        }
                        session_context._trigger_change()
                        session_context.set_pending_clarification(
                            candidate_intents=["calculation", "hs_code_lookup"],
                            rewritten_query=context.question,
                        )

                    # Check if CIF value is also missing
                    cif_missing = "cif_value" in missing_slots

                    if cif_missing:
                        if candidate_codes:
                            candidates_str = ", ".join(f"`{c}`" for c in candidate_codes[:3])
                            answer = (
                                f"To calculate the import tax for **{product_name}**, I will need both its "
                                f"**product classification code (HS code)** and its **purchase price** (including shipping and insurance).\n\n"
                                f"Let's start with the HS code. Common codes for **{product_name}** include {candidates_str}. "
                                "Could you confirm the correct one, or provide another HS code?"
                            )
                        else:
                            answer = (
                                f"To calculate the import tax for **{product_name}**, I will need both its "
                                f"**product classification code (HS code)** and its **purchase price** (including shipping and insurance).\n\n"
                                f"Could you please provide the HS code first? (e.g., `8703.23.21`)"
                            )
                    else:
                        if candidate_codes:
                            candidates_str = ", ".join(f"`{c}`" for c in candidate_codes[:3])
                            answer = (
                                f"To calculate the import tax for **{product_name}**, I need its product classification code (HS code). "
                                f"Common codes include {candidates_str}. Could you confirm the correct one?"
                            )
                        else:
                            answer = (
                                f"To calculate the import tax for **{product_name}**, I need its product classification code (HS code). "
                                f"Could you please provide it? (e.g., `8703.23.21`)"
                            )

                elif next_slot == "cif_value":
                    logger.info(f"[{context.request_id}] Slot collection: asking for cif_value.")
                    product_name = _product_label()
                    hs_label = getattr(session_context, "hs_code", None) if session_context else None
                    subject = f"HS `{hs_label}`" if hs_label else f"**{product_name}**"

                    if session_context:
                        session_context.calc_slot_collection = {
                            "missing": missing_slots,
                            "original_query": raw_service_query,
                        }
                        session_context._trigger_change()
                        session_context.set_pending_clarification(
                            candidate_intents=["calculation"],
                            rewritten_query=context.question,
                        )

                    answer = (
                        f"To calculate the import tax for {subject}, "
                        "I need to know its **total value or purchase price** (including shipping and insurance).\n\n"
                        "How much did you pay for it? (e.g., `$8,000` or `32,000,000 KHR`)"
                    )
                else:
                    answer = "I need a bit more information to complete this calculation. Could you provide more details?"

                context.set_result("calculation", {
                    "answer": answer,
                    "clarification_required": True,
                    "missing_fields": [next_slot],
                    "remaining_fields": remaining_after,
                })
                context.status = WorkflowStatus.CLARIFICATION_REQUIRED
                return

            # All mandatory slots are present — clear collection state and proceed
            if session_context and session_context.calc_slot_collection:
                session_context.calc_slot_collection = None
                session_context._trigger_change()

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
            
            # --- Parse structured params from the enriched query and pass them
            # explicitly so the calculator service never has to re-parse them
            # from natural language (which silently fails and shows CIF = 0.00).
            try:
                from ...infrastructure.clients import CalculatorServiceClient
                _parsed = CalculatorServiceClient._parse_question_for_calculation(service_query)
            except Exception:
                _parsed = {}

            # Build a clean kwargs dict of non-None values to forward
            _extra_kwargs = {
                k: v for k, v in {
                    "hs_code":              _parsed.get("hs_code"),
                    "cif_value":            _parsed.get("cif_value"),
                    "currency":             _parsed.get("currency"),
                    "origin_country":       _parsed.get("origin_country"),
                    "quantity":             _parsed.get("quantity"),
                    "unit":                 _parsed.get("unit"),
                    "fta_applicable":       _parsed.get("fta_applicable"),
                    "fta_certificate_type": _parsed.get("fta_certificate_type"),
                    "preferential_cd_rate": _parsed.get("preferential_cd_rate"),
                    "dq_applicable":        _parsed.get("dq_applicable"),
                    "dq_factor":            _parsed.get("dq_factor"),
                    "declared_value":       _parsed.get("declared_value"),
                    "net_mass":             _parsed.get("net_mass"),
                    "volume":               _parsed.get("volume"),
                    "petroleum_case":       _parsed.get("petroleum_case"),
                    "regime":               _parsed.get("regime"),
                }.items() if v is not None
            }
            
            # Plausibility check for slot completeness
            parsed_cif = _extra_kwargs.get("cif_value")
            parsed_hs = _extra_kwargs.get("hs_code")
            eff_cur = _extra_kwargs.get("currency") or "USD"
            
            product_val = (
                getattr(session_context, 'commercial_description', None) or
                getattr(session_context, 'product_category', None) or
                getattr(session_context, 'last_entity', None) or
                (
                    context.metadata.get("nlu_entity")
                    if (context.metadata and context.metadata.get("nlu_entity_confidence") in ("high", "medium"))
                    else None
                )
            )
            
            has_genuine_product = is_genuine_product_desc(product_val, parsed_hs)
            is_cif_ok = is_cif_value_plausible(parsed_cif, eff_cur)
            is_hs_ok = parsed_hs is not None and len(parsed_hs.replace(".", "").strip()) >= 4
            
            if context.metadata is None:
                context.metadata = {}
                
            if has_genuine_product and is_cif_ok and is_hs_ok:
                context.metadata["slots_complete"] = True
                
            if parsed_hs:
                context.metadata["hs_code"] = parsed_hs

            logger.info(
                f"[{context.request_id}] [CONTEXT-ID] Setting slots_complete in handler. "
                f"context_id={id(context)}, metadata={context.metadata}, "
                f"has_genuine_product={has_genuine_product}, is_cif_ok={is_cif_ok}, is_hs_ok={is_hs_ok}"
            )

            _original_cif_value = _parsed.get("cif_value")
            _original_currency  = _parsed.get("currency") or "USD"

            # Build a canonical query string for the calculator service.
            # This ensures the calculator (which only parses the raw question string in its /query endpoint)
            # receives the correct final parameters (including multiplied unit prices) and flags
            # without description conflict false-positives.
            from app.utils.entity_utils import extract_entity
            regime = _extra_kwargs.get("regime") or "import"
            canonical_parts = [f"calculate {regime} tax"]
            
            product_desc = (
                getattr(session_context, 'commercial_description', None) or
                getattr(session_context, 'product_category', None) or
                getattr(session_context, 'last_entity', None) or
                extract_entity(service_query) or
                "goods"
            )
            hs_val = _extra_kwargs.get("hs_code")
            if hs_val:
                canonical_parts.append(f"for {product_desc} HS {hs_val}")
            else:
                canonical_parts.append(f"for {product_desc}")
                
            cif_val = _extra_kwargs.get("cif_value")
            if cif_val is not None:
                cif_display = int(cif_val) if cif_val == int(cif_val) else cif_val
                curr_val = _extra_kwargs.get("currency") or "USD"
                canonical_parts.append(f"CIF {cif_display} {curr_val}")

            # Preserve quantity so the calculator backend receives the correct
            # item count.  cif_val in _extra_kwargs is already the *total* CIF
            # (unit-price × qty multiplication was done earlier inside
            # _parse_question_for_calculation), so we intentionally omit "each"
            # / "per unit" here to prevent a second multiplication pass when the
            # calculator client re-parses the canonical string.
            qty_val = _extra_kwargs.get("quantity")
            if qty_val is not None:
                qty_display = int(qty_val) if qty_val == int(qty_val) else qty_val
                unit_val = _extra_kwargs.get("unit") or "units"
                canonical_parts.append(f"quantity {qty_display} {unit_val}")
                logger.info(
                    f"[{context.request_id}] [QUANTITY] Appended quantity={qty_display} unit={unit_val} "
                    f"to canonical calculator query (total CIF already={cif_display} {curr_val if cif_val is not None else 'N/A'})"
                )

            origin_val = _extra_kwargs.get("origin_country")
            if origin_val:
                canonical_parts.append(f"from {origin_val}")
                
            cert_val = _extra_kwargs.get("fta_certificate_type")
            if cert_val:
                canonical_parts.append(f"with {cert_val}")
            elif _extra_kwargs.get("fta_applicable"):
                canonical_parts.append("with FTA")
            elif _extra_kwargs.get("fta_applicable") is False:
                canonical_parts.append("no FTA")
                
            if _extra_kwargs.get("dq_applicable") and _extra_kwargs.get("dq_factor") is not None:
                dq_val = _extra_kwargs["dq_factor"]
                canonical_parts.append(f"dq {dq_val}")
                
            if _extra_kwargs.get("declared_value") is not None:
                dv_val = _extra_kwargs["declared_value"]
                canonical_parts.append(f"dv {dv_val}")
                
            if _extra_kwargs.get("net_mass") is not None:
                mass_val = _extra_kwargs["net_mass"]
                canonical_parts.append(f"net mass {mass_val} kg")
                
            if _extra_kwargs.get("volume") is not None:
                vol_val = _extra_kwargs["volume"]
                canonical_parts.append(f"volume {vol_val} liters")
                
            if _extra_kwargs.get("petroleum_case"):
                canonical_parts.append("petroleum")
                
            calculator_question = " ".join(canonical_parts)

            async def run_call():
                return await asyncio.wait_for(
                    coordinator.calculator_client.query(
                        question=calculator_question,
                        session_id=context.session_id,
                        **_extra_kwargs
                    ),
                    timeout=timeout_sec
                )

                
            result = await coordinator._execute_service_call(
                context=context,
                service_name="calculator",
                client_call_fn=run_call,
                request_payload={
                    "question": service_query,
                    "session_id": context.session_id
                }
            )
            # Inject the orchestrator-parsed CIF/currency so the formatter always
            # has them, regardless of what the calculator service returned.
            if result and isinstance(result, dict):
                if result.get("original_cif_value") is None and _original_cif_value is not None:
                    result["original_cif_value"] = _original_cif_value
                if result.get("original_currency") is None:
                    result["original_currency"] = _original_currency

            # ---- Orchestrator-side exchange rate sanity patch ----
            # The calculator service falls back to exchange_rate_usd_to_khr = 1 when
            # its own DB lookup fails.  Catch that here and substitute the standard
            # orchestrator fallback (4 022 KHR/USD) so the displayed rate is never
            # the nonsensical "1 USD = 1.00 KHR".
            _FALLBACK_RATE = 4022.0
            if result and isinstance(result, dict):
                raw_rate = result.get("exchange_rate_usd_to_khr")
                try:
                    _rate_float = float(raw_rate) if raw_rate is not None else 0.0
                except (TypeError, ValueError):
                    _rate_float = 0.0

                if _rate_float <= 1.0:
                    result["exchange_rate_usd_to_khr"] = _FALLBACK_RATE
                    result["exchange_rate_is_fallback"] = True #flag 
                    logger.warning(
                        f"[{context.request_id}] Calculator returned invalid exchange rate "
                        f"({raw_rate!r}). Patching to {_FALLBACK_RATE:,.1f} KHR/USD."
                    )
                    # Also fix the rate inside any pre-formatted text already built
                    # by the calculator service (human_readable, answer, final_answer …).
                    _bad_rate_re = re.compile(
                        r'((?:1\s+)?(?:USD|KHR|THB|EUR|CNY|GBP|JPY)\s*=\s*)1(?:\.0+)?\s*KHR',
                        re.IGNORECASE,
                    )
                    _replacement = rf'\g<1>{_FALLBACK_RATE:,.1f} KHR'
                    for _text_key in ("human_readable", "answer", "final_answer", "formatted_answer", "message"):
                        _txt = result.get(_text_key)
                        if _txt and isinstance(_txt, str):
                            _txt = _bad_rate_re.sub(_replacement, _txt)
                            result[_text_key] = _txt

                    # Append a short caveat so the user sees this isn't a live rate,
                    # instead of silently presenting a stale hardcoded number as authoritative.
                    _caveat = " (Note: using a fallback exchange rate, not today's live rate.)"
                    for _text_key in ("human_readable", "answer", "final_answer", "formatted_answer"):
                        if result.get(_text_key) and isinstance(result[_text_key], str):
                            result[_text_key] += _caveat
                            break  # one caveat is enough — don't stack it across every field

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
                        logger.warning(f"[{context.request_id}] Backstop Khmer translation failed (calculation): {tr_err}")

            is_clarification = False
            if isinstance(result, dict):
                if result.get("clarification_required") or result.get("status") == "clarification_required":
                    is_clarification = True
                elif result.get("success") is False:
                    err_text = str(result.get("error", "") or result.get("answer", "") or "").lower()
                    if "not found" in err_text:
                        if not context.metadata or not context.metadata.get("slots_complete"):
                            is_clarification = True
                    elif any(term in err_text for term in ["mismatch", "clarification", "please rewrite", "validation error"]):
                        is_clarification = True
                    else:
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
                _is_fallback = bool(result.get("exchange_rate_is_fallback"))
                _ttl = 300 if _is_fallback else 2 * 3600
                cache.cache_response(question=cache_query_key, response=result, intent="calculation", ttl_seconds=_ttl, source="calculator")
                context.status = WorkflowStatus.COMPLETED

        except Exception as e:
            logger.error(f"[{context.request_id}] Calculation failed: {e}")
            context.add_error(f"Calculator service error: {str(e)}")
            from ..workflow import WorkflowStatus
            context.status = WorkflowStatus.FAILED
