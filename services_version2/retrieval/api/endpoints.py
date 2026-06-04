
"""
API Endpoints - Retrieval service
FastAPI routes for retrieval operations aligned with Orchestrator v2 architecture

Port: 8003 (as per GDCE services architecture)
Base Path: /v1

Service Role: Handles retrieval-based intents from the Orchestrator:
- Intent.HS_CODE_LOOKUP      → POST /hs-code-lookup
- Intent.DEFINITION          → POST /definition
- Intent.POLICY_INQUIRY      → POST /policy-inquiry
- Intent.GENERAL             → POST /general

Internal endpoints (still supported):
- POST /retrieval/retrieve   → General document retrieval
- POST /retrieval/answer-lookup → HS code lookup from Qdrant

Orchestrator Routing Reference (from ORCHESTRATOR_V2_ARCHITECTURE.md):
- Calculator (8002)   → Intent.CALCULATION
- Retrieval  (8003)   → Intent.{HS_CODE_LOOKUP, DEFINITION, POLICY_INQUIRY, GENERAL}
- Trade Data (8004)   → Intent.TRADE_QUERY
- Orchestrator (8001) → Main entry point, routes to above services
"""

import logging
import re
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, Any, List

from .schemas import QueryRequest, QueryResponse, HealthCheckResponse, DocumentResult
from fastapi import Body

try:
    from ..core.hybrid_hs_lookup import HybridHSLookup
    from ..core import RetrievalService, AnswerGenerator
except ImportError:
    from core.hybrid_hs_lookup import HybridHSLookup
    from core import RetrievalService, AnswerGenerator

from pydantic import BaseModel

class RankedHSResponse(BaseModel):
    status: str
    final_answer: Optional[str]
    answer_source: Optional[str]

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["retrieval"])

# Service dependency (will be injected by app)
_service: Optional[RetrievalService] = None
_answer_generator: Optional[AnswerGenerator] = None


def set_service(service: RetrievalService):
    """Set the retrieval service instance."""
    global _service, _answer_generator
    _service = service
    _answer_generator = AnswerGenerator(
        service.config,
        gemini_client=getattr(service, 'gemini_client', None),
    ) if service and service.config else None


def get_service() -> RetrievalService:
    """Get the current retrieval service."""
    if _service is None:
        raise RuntimeError("Retrieval service not initialized")
    return _service


async def build_final_answer(
    query: str,
    transformed_docs: List[Dict[str, Any]],
    generate_answer: bool,
    intent: Optional[str] = None,
    status: Optional[str] = None,
    clarification: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Build user-friendly final answer from documents."""
    if not generate_answer:
        return {"final_answer": None, "answer_source": None}

    if status == "clarification_required" and clarification:
        return {
            "final_answer": clarification,
            "answer_source": "clarification_required",
        }

    if _answer_generator is not None:
        generated = await _answer_generator.generate(
            query=query,
            documents=transformed_docs,
            intent=intent,
            status=status,
        )
        return {
            "final_answer": generated.get("final_answer"),
            "answer_source": generated.get("answer_source"),
        }

    # Safe fallback when generator is unavailable
    if transformed_docs:
        snippet = transformed_docs[0].get("content", "")
        snippet = str(snippet).replace("\n", " ").strip()
        if len(snippet) > 320:
            snippet = snippet[:317].rstrip() + "..."
        return {
            "final_answer": f"Here is what I found: {snippet}" if snippet else None,
            "answer_source": "extractive_fallback",
        }

    return {
        "final_answer": "I could not find relevant information for your question. Please try rephrasing it.",
        "answer_source": "no_results",
    }
async def build_ranked_hs_answer(
    query: str,
    transformed_docs: List[Dict[str, Any]],
    generate_answer: bool,
    gemini_client=None,
    constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    """Build a simple ranked HS code list as the final answer."""
    if not generate_answer:
        return {"final_answer": None, "answer_source": None}

    if not transformed_docs:
        return {
            "final_answer": "No HS code candidates found for your query.",
            "answer_source": "no_results",
        }
    # new added
    q_lower = query.lower()
    query_signals = [w for w in q_lower.split() if len(w) > 3]

    def _is_relevant(doc):
        content = str(doc.get("content", "")).lower()
        return sum(1 for signal in query_signals if signal in content) >= 1
    

    filtered_docs = [d for d in transformed_docs if _is_relevant(d)]
    # Fall back to all docs if filter is too aggressive
    if len(filtered_docs) < 3:
        filtered_docs = transformed_docs
    # Build context blocks for Gemini (allow larger candidate sets from prefix scans)
    context_blocks = []
    max_context_docs = min(len(transformed_docs), 40)
    for idx, doc in enumerate(transformed_docs[:max_context_docs], start=1):
        hs_code = doc.get("metadata", {}).get("hs_code", "N/A")
        content = str(doc.get("content", "")).strip()
        score = doc.get("score", 0.0)
        if not content:
            continue
        context_blocks.append(
            f"[{idx}] HS Code: {hs_code} | Score: {score:.2f} | Description: {content[:600]}"
        )

    if not context_blocks:
        return {
            "final_answer": "No valid HS code candidates found.",
            "answer_source": "no_results",
        }

    # Try Gemini with a strict ranking prompt
    if gemini_client is not None:
        constraint_text = ""
        if constraints:
            parts = []
            for k, v in constraints.items():
                if v is not None:
                    parts.append(f"{k}={v}")
            if parts:
                constraint_text = "Inferred constraints: " + ", ".join(parts) + "\n\n"
        prompt = (
            f"Product query: {query}\n\n"
            + constraint_text
            + "Candidates:\n"
            + "\n".join(context_blocks)
            + "\n\n"
            "Instructions:\n"
            "- Rank the most relevant HS codes from best to worst.\n"
            "- Output a simple numbered list only.\n"
            "- Use this format: 1. XXXX.XX.XX - short description\n"
            "- Keep each description short and human-readable.\n"
            "- Use only the candidate codes provided above; do not invent or add codes.\n"
            "- If the user does not explicitly mention 'CKD' or 'completely knocked down', assume imports are CBU (completely built unit) and prefer assembled/CBU wording.\n"
            "- If a candidate contains explicit CKD wording and the user did not request CKD, deprioritize it.\n"
            "- Exclude special-purpose vehicles (ambulance, hearse, prison van, motor-home, go-kart, ATV, minibus, coach, bus) unless the user explicitly requests them.\n"
            "- Focus on the key differentiator such as engine type, drive type, body type, CKD/CBU, or special purpose.\n"
            "- Review carefully: this selection is FINAL and will be used for classification; an incorrect choice may cause downstream errors. Only select codes you are confident about.\n"
            "- Ensure all selected codes share the same 6-digit HS prefix that was used to fetch these candidates.\n"
            "- Return up to 5 codes. Do not include irrelevant results.\n"
            "- Do not invent HS codes not present in the candidates."
        )
        try:
            # Pass the actual candidate documents and use the HS-candidate intent
            # so Gemini receives both the context blocks and the correct instruction set.
            raw = await gemini_client.generate_answer(
                query=prompt,
                documents=transformed_docs,
                intent="HS_CODE_CANDIDATES_EXPLAIN_ALL",
            )
            if raw and raw.strip():
                # Validate that Gemini's selections are a subset of provided candidates
                # and that they share the same 6-digit prefix used to fetch these docs.
                candidate_codes = set()
                for d in transformed_docs:
                    hc = d.get("metadata", {}).get("hs_code") or ""
                    hc_digits = re.sub(r"\D", "", str(hc))
                    if hc_digits:
                        candidate_codes.add(hc_digits)

                # derive expected prefix if candidates are homogeneous
                prefixes = {c[:6] for c in candidate_codes if len(c) >= 6}
                expected_prefix = None
                if len(prefixes) == 1:
                    expected_prefix = prefixes.pop()

                # Extract HS-like codes from Gemini's raw text
                found = re.findall(r"\b\d{2,4}(?:\.\d{2}){1,3}\b", raw)
                found_digits = [re.sub(r"\D", "", f) for f in found]

                def _valid_selection(found_digits):
                    if not found_digits:
                        return False
                    # Normalise candidate codes to raw digits for comparison
                    norm_candidates = {re.sub(r"\D", "", c) for c in candidate_codes}
                    for fd in found_digits:
                        fd_norm = re.sub(r"\D", "", fd)
                        if fd_norm in norm_candidates:
                            continue
                        if expected_prefix and fd_norm[:6] == expected_prefix:
                            continue
                        return False
                    if expected_prefix:
                        for fd in found_digits:
                            fd_norm = re.sub(r"\D", "", fd)
                            if fd_norm[:6] != expected_prefix:
                                return False
                    return True

                if _valid_selection(found_digits):
                    return {
                        "final_answer": raw.strip(),
                        "answer_source": "gemini_llm",
                    }

                # Retry once with an explicit correction if validation failed
                try:
                    retry_prompt = (
                        prompt
                        + "\n\nIMPORTANT: Your previous answer contained codes that are not in the provided candidate list or used the wrong 6-digit prefix. "
                        + "You must only select from the candidates above and ensure every selected code shares the same 6-digit HS prefix: "
                        + (expected_prefix or "(unknown)")
                        + ". Return a numbered list only. If you cannot confidently select, return an honest statement saying so."
                    )
                    raw2 = await gemini_client.generate_answer(
                        query=retry_prompt,
                        documents=transformed_docs,
                        intent="HS_CODE_CANDIDATES_EXPLAIN_ALL",
                    )
                    if raw2 and raw2.strip():
                        found2 = re.findall(r"\b\d{2,4}(?:\.\d{2}){1,3}\b", raw2)
                        found2_digits = [re.sub(r"\D", "", f) for f in found2]
                        if _valid_selection(found2_digits):
                            return {"final_answer": raw2.strip(), "answer_source": "gemini_llm"}
                        logger.warning("Gemini retry still produced invalid HS selections.")
                except Exception:
                    logger.exception("Gemini retry failed")
        except Exception as e:
            logger.warning(f"Gemini ranked answer failed: {e}")

    # Fallback: build the ranked list directly from scored docs without LLM
    ranked_text = _format_ranked_hs_lines(query, transformed_docs, limit=5)

    return {
        "final_answer": ranked_text,
        "answer_source": "extractive_ranked",
    }


def _normalize_hs_digits(value: Optional[str]) -> Optional[str]:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 6:
        return digits[:6]
    return None


def _normalize_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _hs_code_family(code: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", str(code or ""))
    if len(digits) >= 6:
        return digits[:6]
    return None


def _filter_docs_to_hs_prefix_family(docs: List[Dict[str, Any]], prefix: Optional[str]) -> List[Dict[str, Any]]:
    family = _normalize_hs_digits(prefix)
    if not family:
        return docs

    filtered: List[Dict[str, Any]] = []
    for doc in docs:
        hs_code = doc.get("metadata", {}).get("hs_code") or doc.get("hs_code")
        if _hs_code_family(hs_code) == family:
            filtered.append(doc)
    return filtered or docs


def _slim_hs_candidate_docs_for_llm(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    slim_docs: List[Dict[str, Any]] = []
    for doc in docs:
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        hs_code = metadata.get("hs_code") or doc.get("hs_code") or doc.get("metadata", {}).get("doc_id") or "N/A"
        description = (
            metadata.get("description")
            or doc.get("content")
            or doc.get("description")
            or ""
        )
        description = str(description).replace("\n", " ").strip()
        hs_prefix = metadata.get("hs_prefix") or _hs_code_family(hs_code)
        slim_docs.append(
            {
                "content": description,
                "metadata": {
                    "hs_code": hs_code,
                    "hs_prefix": hs_prefix,
                    "description": description,
                },
            }
        )
    return slim_docs


def _is_query_ambiguous(query: str) -> bool:
    """Return True when the query is too generic to select specific subheadings.

    Heuristics:
    - Very short queries (<=2 tokens)
    - No presence of typical spec keywords (cc, engine, fuel, assembly, body, drive)
    - If tokens present but none longer than 3 chars and no spec words
    """
    q = _normalize_text(query)
    if not q:
        return True
    tokens = [t for t in q.split() if t]
    if len(tokens) <= 2:
        return True

    # Named product/model queries like "lexus lx 600" should not be treated as
    # ambiguous just because they do not mention engine or drive specs.
    has_model_token = bool(re.search(r"\b[a-z]{1,4}\s*\d{2,4}\b", q))
    has_brand_like_token = bool(re.search(r"\b[a-z]+\s+[a-z]{1,4}\s*\d{2,4}\b", q))
    if has_model_token or has_brand_like_token:
        return False

    SPEC_KEYWORDS = {
        "cc",
        "engine",
        "diesel",
        "petrol",
        "gasoline",
        "electric",
        "ev",
        "hybrid",
        "phev",
        "hev",
        "plug",
        "ckd",
        "cbu",
        "completely",
        "assembled",
        "sedan",
        "hatchback",
        "suv",
        "van",
        "truck",
        "pickup",
        "ambulance",
        "hearse",
        "motorhome",
        "motor-home",
        "prison",
        "wheelchair",
        "gvw",
        "gvm",
    }

    # If any spec keyword appears, treat as specific
    for kw in SPEC_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", q):
            return False

    # If there are several reasonably long tokens, it's probably specific
    long_tokens = [t for t in tokens if len(t) > 3]
    if len(long_tokens) >= 2:
        return False

    return True


def _doc_text_for_filter(doc: Dict[str, Any]) -> str:
    parts = [
        doc.get("description"),
        doc.get("search_text"),
        doc.get("text"),
        doc.get("content"),
    ]
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    parts.extend([
        metadata.get("description"),
        metadata.get("search_text"),
        metadata.get("text"),
    ])
    return _normalize_text(" ".join(str(p or "") for p in parts))


def _candidate_support_score(query: str, doc: Dict[str, Any]) -> float:
    """Estimate how well a candidate doc matches the user's query.

    This is a lightweight guardrail used to stop the LLM from finalizing a code
    when the candidate set is semantically weak or off-target.
    """
    q = _normalize_text(query)
    text = _doc_text_for_filter(doc)
    if not q or not text:
        return 0.0

    query_tokens = [t for t in re.findall(r"[a-z0-9\.]+", q) if len(t) > 1]
    text_tokens = set(re.findall(r"[a-z0-9\.]+", text))
    overlap = [t for t in query_tokens if t in text_tokens]
    overlap_ratio = len(overlap) / max(1, len(set(query_tokens)))

    score = overlap_ratio * 0.45

    constraints = _derive_vehicle_constraints(query)
    if any(v is not None for v in constraints.values()):
        if constraints.get("assembly") == "non_ckd":
            if re.search(r"\b(cbu|assembled|completely built unit|assembled vehicle)\b", text):
                score += 0.18
            elif re.search(r"\b(ckd|completely knocked down|unassembled)\b", text):
                score -= 0.25
        elif constraints.get("assembly") == "ckd":
            if re.search(r"\b(ckd|completely knocked down|unassembled)\b", text):
                score += 0.20

        if constraints.get("fuel") == "diesel":
            if "diesel" in text or "compression-ignition" in text:
                score += 0.20
            else:
                score -= 0.20
        elif constraints.get("fuel") == "spark":
            if "spark-ignition" in text or "petrol" in text or "gasoline" in text:
                score += 0.20
            else:
                score -= 0.20
        elif constraints.get("fuel") == "hybrid":
            if "electric" in text and (
                "diesel" in text or "compression-ignition" in text or "petrol" in text or "gasoline" in text
            ):
                score += 0.22

        if constraints.get("body") == "suv":
            if re.search(r"\bsuv\b|sport utility", text):
                score += 0.20
            elif re.search(r"\b(go[- ]?kart|ambulance|hearse|prison van|atv|all[- ]terrain vehicle)\b", text):
                score -= 0.28
        elif constraints.get("body") == "sedan":
            score += 0.15 if "sedan" in text else 0.0
        elif constraints.get("body") == "pickup":
            score += 0.15 if re.search(r"\bpick\s*[- ]?up\b|\bpickup\b", text) else 0.0

        if constraints.get("drive") == "4wd":
            if re.search(r"\b(4wd|4x4|four-wheel\s+drive|all-wheel|awd)\b", text):
                score += 0.18
            else:
                score -= 0.15
        elif constraints.get("drive") == "2wd":
            if re.search(r"\b(2wd|two-wheel\s+drive)\b", text):
                score += 0.15

        cc = constraints.get("cc")
        if isinstance(cc, int):
            if _matches_cc(cc, text):
                score += 0.20
            else:
                score -= 0.10

    if any(term in q for term in ("vehicle", "car", "suv", "truck", "van")):
        if any(term in text for term in ("vehicle", "car", "suv", "truck", "van")):
            score += 0.05

    # Penalize candidates that are clearly special-purpose when the query
    # appears to target a passenger SUV (helps avoid enumerating ambulances, etc.)
    inferred = _derive_vehicle_constraints(query)
    if inferred.get("body") == "suv":
        if re.search(r"\b(ambulance|hearse|prison van|prison|motor-home|motorhome|go[- ]?kart|atv|all[- ]terrain vehicle|sedan)\b", text):
            score -= 0.35

    return max(0.0, min(1.0, score))


def _hs_result_confident(query: str, docs: List[Dict[str, Any]]) -> bool:
    if not docs:
        return False
    top_doc = docs[0]
    support = _candidate_support_score(query, top_doc)
    return support >= 0.55


def _humanize_hs_text(text: str, max_segments: int = 3) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "Short description unavailable"

    raw = re.sub(r"\s+", " ", raw)
    raw = raw.replace(" > ", "; ")
    segments = [segment.strip(" ;:-") for segment in re.split(r"[>;]", raw) if segment.strip(" ;:-")]

    parts: List[str] = []
    seen = set()
    for segment in segments:
        if segment and segment not in seen:
            seen.add(segment)
            parts.append(segment)
        if len(parts) >= max_segments:
            break

    if parts:
        leading = parts[0].lower()
        if leading.startswith("motor cars and other motor vehicles principally designed for the transport of persons"):
            parts = parts[1:] or parts[:1]
        elif leading.startswith("motor vehicles for the transport of goods"):
            parts = parts[1:] or parts[:1]

    if not parts:
        cleaned = raw.strip(" ;:-")
        return cleaned if cleaned else "Short description unavailable"

    sentence = ", ".join(parts)
    sentence = re.sub(r"\s+,", ",", sentence)
    sentence = re.sub(r",\s+,", ", ", sentence)
    return sentence[:140].rstrip()


def _summarize_candidate_explanation(query: str, doc: Dict[str, Any]) -> str:
    q = _normalize_text(query)
    text = _doc_text_for_filter(doc)
    constraints = _derive_vehicle_constraints(query)
    reasons: List[str] = []

    hs_code = str(doc.get("metadata", {}).get("hs_code") or doc.get("hs_code") or "").strip()
    short_desc = _humanize_hs_text(doc.get("content") or doc.get("description") or text, max_segments=3)

    if constraints.get("assembly") == "non_ckd":
        if re.search(r"\b(cbu|assembled|complete built unit)\b", text):
            reasons.append("matches CBU / assembled wording")
        elif re.search(r"\b(ckd|completely knocked down|unassembled)\b", text):
            reasons.append("candidate is CKD, which conflicts with the query")

    if constraints.get("fuel") == "diesel":
        if "diesel" in text or "compression-ignition" in text:
            reasons.append("matches diesel / compression-ignition")
    elif constraints.get("fuel") == "spark":
        if "spark-ignition" in text or "petrol" in text or "gasoline" in text:
            reasons.append("matches spark-ignition / petrol wording")
    elif constraints.get("fuel") == "hybrid":
        if "electric" in text and ("diesel" in text or "compression-ignition" in text or "petrol" in text or "gasoline" in text):
            reasons.append("matches hybrid / electric-motor wording")

    if constraints.get("body") == "suv" and ("suv" in text or "sport utility" in text or "passenger vehicle" in text):
        reasons.append("matches SUV / passenger-vehicle wording")
    elif constraints.get("body") == "sedan" and "sedan" in text:
        reasons.append("matches sedan wording")
    elif constraints.get("body") == "pickup" and re.search(r"\bpick\s*[- ]?up\b|\bpickup\b", text):
        reasons.append("matches pickup wording")

    if constraints.get("drive") == "4wd" and re.search(r"\b(4wd|4x4|four-wheel\s+drive|all-wheel|awd)\b", text):
        reasons.append("matches 4WD / all-wheel wording")
    elif constraints.get("drive") == "2wd" and re.search(r"\b(2wd|two-wheel\s+drive)\b", text):
        reasons.append("matches 2WD wording")

    cc = constraints.get("cc")
    if isinstance(cc, int):
        if _matches_cc(cc, text):
            reasons.append(f"matches cylinder capacity around {cc}cc")

    if not reasons:
        query_terms = [t for t in re.findall(r"[a-z0-9]+", q) if len(t) > 2]
        text_terms = set(re.findall(r"[a-z0-9]+", text))
        overlap = [t for t in query_terms if t in text_terms][:4]
        if overlap:
            reasons.append("shares query terms: " + ", ".join(overlap))

    if not reasons:
        reasons.append("closest available description in the retrieved HS corpus")

    reason_text = "; ".join(reasons)
    return f"HS {hs_code or 'N/A'}: {short_desc}. This is a plausible match because {reason_text}."


def _build_multi_candidate_hs_answer(query: str, docs: List[Dict[str, Any]], limit: int = 10) -> Dict[str, str]:
    if not docs:
        return {
            "final_answer": "No HS code candidates found for your query.",
            "answer_source": "no_results",
        }

    ranked_docs = sorted(docs, key=lambda d: _candidate_support_score(query, d), reverse=True)
    lines = ["Multiple HS codes are possible from the provided context. Here are the best matches:"]

    for idx, doc in enumerate(ranked_docs[:limit], start=1):
        lines.append(f"{idx}. {_summarize_candidate_explanation(query, doc)}")

    lines.append("")
    lines.append("If you want a single final HS code, tell me which option best matches the product or add one missing spec.")

    return {
        "final_answer": "\n".join(lines),
        "answer_source": "multi_candidate_extractive",
    }


def _format_ranked_hs_lines(query: str, docs: List[Dict[str, Any]], limit: int = 5) -> str:
    if not docs:
        return "No ranked results available."

    ranked_docs = sorted(docs, key=lambda d: _candidate_support_score(query, d), reverse=True)
    lines: List[str] = []
    for idx, doc in enumerate(ranked_docs[:limit], start=1):
        hs_code = str(doc.get("metadata", {}).get("hs_code") or doc.get("hs_code") or "N/A").strip()
        content = _humanize_hs_text(doc.get("content") or doc.get("description") or "", max_segments=3)
        lines.append(f"{idx}. HS {hs_code}: {content}")
    return "\n".join(lines)


def _derive_vehicle_constraints(query: str) -> Dict[str, Any]:
    q = _normalize_text(query)
    constraints: Dict[str, Any] = {
        "assembly": None,
        "fuel": None,
        "body": None,
        "drive": None,
        "cc": None,
    }

    if re.search(r"\b(not\s+ckd|non\s*[- ]?ckd|cbu|completely\s+built\s+unit|assembled)\b", q):
        constraints["assembly"] = "non_ckd"
    elif re.search(r"\b(ckd|completely\s+knocked\s+down|unassembled)\b", q):
        constraints["assembly"] = "ckd"

    if re.search(r"\bcompression[- ]?ignition\b|\bdiesel\b", q):
        constraints["fuel"] = "diesel"
    elif re.search(r"\bspark[- ]?ignition\b|\bpetrol\b|\bgasoline\b", q):
        constraints["fuel"] = "spark"
    elif re.search(r"\belectric\b|\bev\b", q):
        constraints["fuel"] = "electric"
    elif re.search(r"\bhybrid\b|\bhev\b|\bphev\b|plug[- ]?in", q):
        constraints["fuel"] = "hybrid"

    if re.search(r"\bsedan\b", q):
        constraints["body"] = "sedan"
    elif re.search(r"\bhatchback\b", q):
        constraints["body"] = "hatchback"
    elif re.search(r"\bsuv\b", q):
        constraints["body"] = "suv"
    elif re.search(r"\bpick\s*[- ]?up\b|\bpickup\b", q):
        constraints["body"] = "pickup"

    if re.search(r"\b2\s*[- ]?wheel\s*[- ]?drive\b|\b2wd\b|\btwo\s*[- ]?wheel\b", q):
        constraints["drive"] = "2wd"
    elif re.search(r"\b4\s*[- ]?wheel\s*[- ]?drive\b|\b4wd\b|\b4x4\b|\bawd\b|\ball\s*[- ]?wheel\b", q):
        constraints["drive"] = "4wd"

    cc_match = re.search(r"(\d{3,5})\s*cc\b", q)
    if cc_match:
        try:
            constraints["cc"] = int(cc_match.group(1))
        except Exception:
            constraints["cc"] = None

    # Heuristic: brand+model tokens (e.g., "lexus lx 600") usually indicate a
    # specific passenger model. Treat these as likely passenger SUVs unless the
    # user explicitly mentions other body types (ambulance, van, etc.). This
    # helps prefer passenger-car subheadings (e.g., 4WD variants) over utility
    # /special-purpose entries.
    has_model_token = bool(re.search(r"\b[a-z]{1,4}\s*\d{2,4}\b", q))
    has_brand_like_token = bool(re.search(r"\b[a-z]+\s+[a-z]{1,4}\s*\d{2,4}\b", q))
    if has_model_token or has_brand_like_token:
        # only set body/drive if user hasn't explicitly provided a conflicting hint
        if constraints.get("body") is None and not re.search(r"\b(ambulance|hearse|prison|motorhome|motor-home|go-kart|atv|van)\b", q):
            constraints["body"] = "suv"
        if constraints.get("drive") is None:
            constraints["drive"] = "4wd"

    return constraints


def _infer_vehicle_constraints_from_model(query: str) -> Dict[str, Any]:
    """Infer likely vehicle constraints from brand/model tokens when present.

    This is a lightweight heuristic: for queries like "lexus lx 600" we infer
    passenger SUV and 4WD as a strong prior so the pipeline can exclude
    obviously incompatible subheadings (ambulance, hearse, go-kart, etc.).
    """
    q = _normalize_text(query)
    inferred: Dict[str, Any] = {
        "assembly": None,
        "fuel": None,
        "body": None,
        "drive": None,
        "cc": None,
    }

    # Detect brand+model patterns (e.g., "lexus lx 600")
    has_model_token = bool(re.search(r"\b[a-z]{1,4}\s*\d{2,4}\b", q))
    # Specific heuristic for Lexus LX patterns which are SUVs and typically 4WD
    if re.search(r"\blexus\b.*\blx\b|\blx\s*\d{1,3}\b", q):
        inferred["body"] = "suv"
        inferred["drive"] = "4wd"
        inferred["fuel"] = "spark"

    # Generic model token heuristic: assume passenger vehicle unless keywords indicate goods
    if has_model_token and inferred["body"] is None:
        inferred["body"] = "suv"
        inferred["drive"] = "4wd"

    return inferred


def _extract_cc_ranges(text: str) -> List[tuple[Optional[int], Optional[int]]]:
    ranges: List[tuple[Optional[int], Optional[int]]] = []

    for low, high in re.findall(
        r"exceeding\s*([0-9][0-9,]*)\s*cc\s*but\s*not\s*exceeding\s*([0-9][0-9,]*)\s*cc",
        text,
    ):
        try:
            ranges.append((int(low.replace(",", "")), int(high.replace(",", ""))))
        except Exception:
            continue

    for low in re.findall(r"exceeding\s*([0-9][0-9,]*)\s*cc", text):
        try:
            low_value = int(low.replace(",", ""))
            if not any(r[0] == low_value for r in ranges):
                ranges.append((low_value, None))
        except Exception:
            continue

    for high in re.findall(r"not\s*exceeding\s*([0-9][0-9,]*)\s*cc", text):
        try:
            high_value = int(high.replace(",", ""))
            if not any(r[1] == high_value for r in ranges):
                ranges.append((None, high_value))
        except Exception:
            continue

    return ranges


def _matches_cc(cc: int, text: str) -> bool:
    ranges = _extract_cc_ranges(text)
    if not ranges:
        return True

    for low, high in ranges:
        lower_ok = True if low is None else cc > low
        upper_ok = True if high is None else cc <= high
        if lower_ok and upper_ok:
            return True
    return False


def _apply_hard_vehicle_filters(query: str, docs: List[Dict[str, Any]], constraints: Optional[Dict[str, Any]] = None) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Apply strict filters derived from vehicle constraints.

    If `constraints` is provided it will be used instead of deriving from query.
    Returns filtered docs and metadata about filtering.
    """
    if constraints is None:
        constraints = _derive_vehicle_constraints(query)
    filtered: List[Dict[str, Any]] = []

    for doc in docs:
        text = _doc_text_for_filter(doc)

        assembly = constraints.get("assembly")
        if assembly == "ckd":
            if not re.search(r"\b(ckd|completely\s+knocked\s+down|unassembled)\b", text):
                continue
        elif assembly == "non_ckd":
            if re.search(r"\b(ckd|completely\s+knocked\s+down|unassembled)\b", text):
                continue

        fuel = constraints.get("fuel")
        if fuel == "diesel":
            if not ("compression-ignition" in text or "diesel" in text):
                continue
        elif fuel == "spark":
            if not ("spark-ignition" in text or "petrol" in text or "gasoline" in text):
                continue
        elif fuel == "electric":
            if "electric motor" not in text:
                continue
        elif fuel == "hybrid":
            if "electric motor" not in text or ("spark-ignition" not in text and "compression-ignition" not in text):
                continue

        body = constraints.get("body")
        if body == "sedan" and "sedan" not in text:
            continue
        if body == "hatchback" and "hatchback" not in text:
            continue
        if body == "suv" and "suv" not in text:
            continue
        if body == "pickup" and not re.search(r"\bpick\s*[- ]?up\b|\bpickup\b", text):
            continue

        drive = constraints.get("drive")
        if drive == "2wd":
            if re.search(r"\b(4wd|4x4|four-wheel\s+drive|all-wheel|awd)\b", text):
                continue
        elif drive == "4wd":
            if not re.search(r"\b(4wd|4x4|four-wheel\s+drive|all-wheel|awd)\b", text):
                continue

        cc = constraints.get("cc")
        if isinstance(cc, int) and not _matches_cc(cc, text):
            continue

        # Exclusion rules: when the inferred body is `suv`, exclude special-purpose
        # vehicle descriptions that are mutually exclusive with passenger SUVs.
        if body == "suv":
            if re.search(r"\b(ambulance|hearse|prison van|prison|motor-home|motorhome|go[- ]?kart|atv|all[- ]terrain vehicle)\b", text):
                continue

        filtered.append(doc)

    metadata = {
        "filter_constraints": constraints,
        "filter_input_count": len(docs),
        "filter_output_count": len(filtered),
    }
    return filtered, metadata


async def _extract_hs_prefix_with_gemini(gemini_client, query: str) -> Optional[str]:
    if gemini_client is None:
        return None

    prompt = (
        "You are an HS code prefix extractor. Return exactly one 6-digit HS code "
        "for the product described by the user. This must be the parent family "
        "code used to fetch all matching 8-digit subcodes. Return digits only. "
        "Do not return multiple codes, do not explain, and do not output anything "
        "other than the 6 digits. If you are unsure, return an empty string.\n\n"
        f"Query: {query}\n"
        "6-digit HS code:"
    )

    async def _run_prompt(current_prompt: str) -> Optional[str]:
        try:
            raw = await gemini_client.generate_answer(
                query=current_prompt,
                documents=[],
                intent="EXTRACT_SPECS",
            )
        except Exception as exc:
            logger.warning(f"HS prefix extraction failed: {exc}")
            return None

        prefix = _normalize_hs_digits(raw)
        if prefix is None:
            return None

        # Guardrail: if Gemini emits something malformed, keep only the first
        # 6 digits and reject very noisy outputs.
        if not re.fullmatch(r"\d{6}", prefix):
            return None

        return prefix

    prefix = await _run_prompt(prompt)
    if prefix:
        return prefix

    retry_prompt = (
        prompt
        + "\n\nIMPORTANT: Your previous response was invalid or empty. "
        + "Return only one 6-digit HS code, with no words, punctuation, or explanation."
    )
    return await _run_prompt(retry_prompt)


async def _build_hs_candidate_documents(
    service: RetrievalService,
    query: str,
    top_k: int,
    gemini_client,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    import asyncio

    collection_name = getattr(service.config, "qdrant_hs_code_collection", "gdce_hs_code")

    # Cap fetch limit — prefix families have at most ~40 8-digit codes
    raw_limit = min(max(int(top_k or 10) * 2, 60), 100)

    # ── Run prefix extraction and semantic search IN PARALLEL ──────────────
    prefix_task = asyncio.create_task(
        _extract_hs_prefix_with_gemini(gemini_client, query)
    )
    semantic_task = asyncio.create_task(
        service.orchestrator.retrieve_semantic(
            query, top_k=20, collection_name=collection_name
        )
    )

    prefix, semantic_results = await asyncio.gather(
        prefix_task, semantic_task, return_exceptions=True
    )

    # Handle exceptions from gather
    if isinstance(prefix, Exception):
        logger.warning(f"Prefix extraction failed: {prefix}")
        prefix = None
    if isinstance(semantic_results, Exception):
        logger.warning(f"Semantic search failed: {semantic_results}")
        semantic_results = []

    raw_docs: List[Dict[str, Any]] = []
    source = None
    filter_meta: Dict[str, Any] = {}

    def get_code(d):
        m = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
        return (d.get("hs_code") or m.get("hs_code") or m.get("hscode") or m.get("tariff_code"))

    # ── Use prefix scan if we got a valid prefix ───────────────────────────
    if prefix:
        # Use the new async version so it doesn't block the event loop
        raw_docs = await service.fetch_hs_documents_by_prefix_async(
            prefix, collection_name=collection_name, limit=raw_limit
        )
        source = "structured_prefix_scan_full"

        if raw_docs:
            raw_docs = service._score_hs_candidates_by_query(
                query=query,
                documents=raw_docs,
                target_heading=prefix[:4],
            )
            
            # Supplement with semantic results if there are fewer than 3 prefix matches
            if len(raw_docs) < 3 and semantic_results:
                existing_codes = {str(get_code(d)).strip() for d in raw_docs if get_code(d)}
                added_count = 0
                for idx, doc in enumerate(semantic_results):
                    code = get_code(doc)
                    code_str = str(code).strip() if code else ""
                    if code_str and code_str not in existing_codes:
                        doc_copy = {
                            **doc,
                            "id": doc.get("id", f"sem_{idx}"),
                            "content": doc.get("content") or doc.get("description") or doc.get("text") or "",
                            "score": doc.get("score", 0.5),
                            "retrieval_source": "semantic",
                            "metadata": doc.get("metadata") or {"hs_code": code},
                        }
                        raw_docs.append(doc_copy)
                        existing_codes.add(code_str)
                        added_count += 1
                        if len(raw_docs) >= 3 or added_count >= 5:
                            break
                source = f"prefix_scan_with_semantic_fill_{added_count}"

    # ── Fall back to semantic results if prefix scan found nothing ─────────
    if not raw_docs:
        raw_docs = [
            {
                **doc,
                "id": doc.get("id", str(idx)),
                "content": doc.get("content") or doc.get("description") or doc.get("text") or "",
                "score": doc.get("score", 0.5),
                "retrieval_source": "semantic",
                "metadata": doc.get("metadata") or {"hs_code": get_code(doc)},
            }
            for idx, doc in enumerate(semantic_results or [])
        ]
        source = "semantic_fallback"

        try:
            constraints = _derive_vehicle_constraints(query)
            if any(v is not None for v in constraints.values()):
                filtered_docs, filter_meta = _apply_hard_vehicle_filters(
                    query, raw_docs, constraints
                )
                if filter_meta.get("filter_output_count", 0) > 0:
                    raw_docs = filtered_docs
                else:
                    # Relax body/cc/drive filters and retry
                    relaxed = {**constraints, "body": None, "cc": None, "drive": None}
                    relaxed_docs, relaxed_meta = _apply_hard_vehicle_filters(
                        query, raw_docs, relaxed
                    )
                    if relaxed_meta.get("filter_output_count", 0) > 0:
                        raw_docs = relaxed_docs
                        filter_meta = {
                            **relaxed_meta,
                            "filters_relaxed": [
                                k for k in ("body", "cc", "drive")
                                if constraints.get(k) is not None
                            ],
                        }
        except Exception:
            filter_meta = {}

    transformed_docs = [
        transform_document({
            **doc,
            "id": doc.get("id", str(idx)),
            "content": doc.get("content") or doc.get("description") or doc.get("text") or "",
            "score": doc.get("score", 0.5),
            "retrieval_source": doc.get(
                "retrieval_source",
                "structured_prefix_scan_full" if prefix else "semantic"
            ),
        })
        for idx, doc in enumerate(raw_docs)
    ]

    metadata = {
        "hs_prefix": prefix,
        "candidate_source": source,
        **filter_meta,
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}
    return transformed_docs, metadata

def transform_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform Qdrant/raw document to DocumentResult schema.
    
    Args:
        doc: Raw document from Qdrant or database
            Note: Qdrant payload fields are unpacked directly (not nested)
        
    Returns:
        Transformed document matching DocumentResult schema
    """
    # Try to find content in various possible field names
    # (Qdrant payload fields are already unpacked at top level)
    content = (
        doc.get("text") or 
        doc.get("content") or 
        doc.get("description") or 
        doc.get("title") or 
        ""
    )
    
    # Determine the ID (string format)  
    doc_id = str(doc.get("id") or doc.get("doc_id") or "unknown")
    
    # Get score if available
    score = doc.get("score", 0.5)
    
    # Determine source
    source = doc.get("retrieval_source", "semantic")
    
    # Collect metadata from all extra fields
    metadata = {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title"),
        "hs_code": doc.get("hs_code"),
        "source_url": doc.get("source_url"),
        "description": doc.get("description"),
    }
    # Add any other fields that might be useful from Qdrant payload
    for key, value in doc.items():
        if key not in ["id", "score", "content", "text", "retrieval_source"] and not key.startswith("_"):
            metadata[key] = value
    
    # Build transformed document
    return {
        "id": doc_id,
        "content": str(content)[:1000] if content else "",  # Limit content length
        "score": float(score) if score else 0.5,
        "source": source,
        "metadata": {k: v for k, v in metadata.items() if v is not None}  # Only include non-null metadata
    }


def _build_response_data(
    request: QueryRequest,
    result: Dict[str, Any],
    transformed_docs: List[Dict[str, Any]],
    answer_payload: Dict[str, Optional[str]],
    api_called: str,
) -> Dict[str, Any]:
    visibility = result.get("api_visibility", {})
    collection_used = visibility.get("collection_used") or request.collection or "gdce_docs"
    missing_parameters = result.get("missing_parameters")

    metadata = {
        "keywords": result.get("keywords", []),
        "heading_4_digit": result.get("heading_4_digit"),
        "hs_mode": result.get("hs_mode"),
        "clarification": result.get("clarification"),
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    return {
        "query": result.get("query", request.query),
        "status": result.get("status", "success"),
        "documents": transformed_docs,
        "total_count": len(transformed_docs),
        "semantic_count": result.get("semantic_count", 0),
        "structured_count": result.get("structured_count", 0),
        "session_id": result.get("session_id", request.session_id),
        "final_answer": (result.get("clarification") if result.get("status") == "clarification_required" else answer_payload.get("final_answer") or result.get("clarification")),
        "answer_source": answer_payload.get("answer_source"),
        "api_called": api_called,
        "collection_used": collection_used,
        "language": result.get("language"),
        "required_parameters": ["query"],
        "missing_parameters": missing_parameters,
        "metadata": metadata,
        "error": result.get("error"),
    }



# Place the /v1/hs-code-candidates endpoint after router is defined

@router.post("/hs-code-candidates", tags=["Intent: HS Code Candidates"], response_model=QueryResponse)
async def hs_code_candidates_endpoint(
    request: QueryRequest,
    service: RetrievalService = Depends(get_service)
) -> QueryResponse:
    """
    HS Code Candidates - LLM-powered candidate selection and explanation.
    Retrieves candidate HS codes for a product description, then uses Gemini LLM to select and explain the best candidates.
    """
    try:
        logger.info(f"HS Code Candidates request: {request.query[:100]}")
        gemini_client = getattr(service, "gemini_client", None)
        fetch_limit = request.top_k if request.top_k and request.top_k > 0 else 50
        transformed_docs, hs_metadata = await _build_hs_candidate_documents(
            service=service,
            query=request.query,
            top_k=fetch_limit,
            gemini_client=gemini_client,
        )

        confidence_ok = _hs_result_confident(request.query, transformed_docs)
        llm_docs = _slim_hs_candidate_docs_for_llm(transformed_docs)

        # Step 2: LLM-driven review — pass the user query and ALL prefix-derived
        # candidates to the LLM. The LLM should remove unrelated candidates,
        # rank the remaining ones and provide brief explanations. The LLM is
        # the main decider for this flow.
        intent_value = "HS_CODE_CANDIDATES_EXPLAIN_ALL"

        if request.generate_answer and transformed_docs:
            # Build explicit candidate list text for the LLM to review
            candidate_lines = []
            for idx, doc in enumerate(llm_docs[:50], start=1):
                metadata = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
                hs_code = metadata.get("hs_code") or "N/A"
                hs_prefix = metadata.get("hs_prefix") or "N/A"
                desc = (metadata.get("description") or doc.get("content") or "").strip()
                desc = desc.replace("\n", " ")
                candidate_lines.append(f"[{idx}] HS {hs_code} | Prefix {hs_prefix} | Description: {desc[:400]}")

            candidates_text = "Candidates:\n" + "\n".join(candidate_lines) + "\n\n"

            llm_prompt = (
                "You are an HS code decision assistant. You are given a set of candidate "
                "HS codes (below) with short descriptions. Review all candidates, remove any "
                "that are not related to the product in the user's query, and rank the "
                "remaining candidates from best to worst. Return a numbered list only, "
                "with each line in the format: 1. HS XXXX.XX.XX - short reason. Return up to 10 codes. "
                "Use only codes from the provided candidate list; do not invent or add codes.\n\n"
                f"User query: {request.query}\n\n"
                "Assembly rule: if the user did not explicitly state 'CKD' or 'completely knocked down', assume imports are CBU (completely built units) and prefer candidates with CBU/assembled wording. If a candidate explicitly contains CKD wording and the user did not request CKD, deprioritize it.\n\n"
                "Exclusions: exclude special-purpose vehicles (ambulance, hearse, prison van, motor-home, go-kart, ATV, minibus, coach, bus) unless the user query explicitly mentions those.\n\n"
                + candidates_text
            )

            answer_payload = await build_final_answer(
                query=llm_prompt,
                transformed_docs=llm_docs,
                generate_answer=True,
                intent=intent_value,
                status=None,
                clarification=None,
            )
        else:
            answer_payload = {"final_answer": None, "answer_source": None}

        # Step 3: Build response
        metadata = dict(hs_metadata)
        metadata["candidate_confidence"] = "high" if confidence_ok else "low"
        response_data = {
            "query": request.query,
            "status": "success",
            "documents": transformed_docs,
            "total_count": len(transformed_docs),
            "semantic_count": len(transformed_docs),
            "structured_count": 0,
            "final_answer": answer_payload.get("final_answer"),
            "answer_source": answer_payload.get("answer_source"),
            "session_id": request.session_id,
            "api_called": "/hs-code-candidates",
            "collection_used": "gdce_hs_code",
            "language": None,
            "required_parameters": ["query"],
            "missing_parameters": None,
            "metadata": metadata,
            "error": None,
        }
        return QueryResponse(**response_data)
    except Exception as e:
        logger.error(f"HS Code Candidates error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"HS Code Candidates failed: {str(e)}"
        )
@router.post("/retrieval/retrieve", tags=["Intent: General"], response_model=QueryResponse)
async def retrieve(
    request: QueryRequest,
    service: RetrievalService = Depends(get_service)
) -> QueryResponse:
    """
    Retrieve documents matching the query.
    
    Args:
        request: Query request with search parameters and optional collection
        service: Injected retrieval service
        
    Returns:
        QueryResponse with retrieved documents
    """
    try:
        logger.info(f"Retrieve request: {request.query[:100]}... (collection: {request.collection})")
        
        result = await service.retrieve(
            query=request.query,
            top_k=request.top_k,
            session_id=request.session_id,
            collection=request.collection,
            hs_mode=request.hs_mode or "best",
            selected_code=request.selected_code,
            compare_codes=request.compare_codes,
            require_period_for_trade=request.require_period_for_trade,
        )
        
        # Transform documents to match schema
        transformed_docs = []
        logger.info(f"Starting document transformation: {len(result.get('documents', []))} documents to transform")
        for i, doc in enumerate(result.get("documents", []), 1):
            try:
                logger.debug(f"Transforming document {i}: keys={list(doc.keys())}")
                transformed = transform_document(doc)
                transformed_docs.append(transformed)
                logger.debug(f"Successfully transformed document {i}: {transformed.get('id')}")
            except Exception as e:
                logger.error(f"Failed to transform document {i}: {e}", exc_info=True)
                continue
        
        logger.info(f"Transformation complete: {len(transformed_docs)} documents transformed")
        
        # Build response
        intent_value = request.intent or "general"  # Use orchestrator's intent or default
        answer_payload = await build_final_answer(
            query=request.query,
            transformed_docs=transformed_docs,
            generate_answer=request.generate_answer,
            intent=intent_value,
            status=result.get("status"),
            clarification=result.get("clarification"),
        )

        response_data = _build_response_data(
            request=request,
            result=result,
            transformed_docs=transformed_docs,
            answer_payload=answer_payload,
            api_called="/retrieval/retrieve",
        )
        
        return QueryResponse(**response_data)
        
    except Exception as e:
        logger.error(f"Retrieve error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Retrieval failed: {str(e)}"
        )


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(
    service: RetrievalService = Depends(get_service)
) -> HealthCheckResponse:
    """
    Check health of retrieval service.
    
    Returns:
        Health status of all components
    """
    try:
        status = await service.health_check()
        return HealthCheckResponse(**status)
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthCheckResponse(
            status="unhealthy",
            components={"error": {"message": str(e)}}
        )

@router.get("/", tags=["Health"], response_model=dict)
def root():
    """Root endpoint showing available endpoints."""
    return {
        "service": "Retrieval Service v2",
        "version": "2.0.0",
        "port": 8003,
        "endpoints": {
            "health": "GET /health",
            "retrieve": "POST /retrieval/retrieve",
            "hs_code_candidates": "POST /hs-code-candidates",
            "hs_code_ranked": "POST /hs-code-ranked",
            "swagger": "/docs",
            "openapi": "/openapi.json"
        },
        "description": "Routes queries to appropriate retrieval endpoints based on intent. Called by Orchestrator Service (8001)."
    }



@router.post("/hs-code-ranked", tags=["Intent: HS Code Ranked"], response_model=RankedHSResponse)
async def hs_code_ranked_endpoint(
    request: QueryRequest,
    service: RetrievalService = Depends(get_service),
) -> RankedHSResponse:
    """
    HS Code Ranked — returns a simple ranked list of HS codes with short descriptions.
    Same retrieval logic as /hs-code-candidates but final answer is a clean numbered list only.
    """
    try:
        logger.info(f"HS Code Ranked request: {request.query[:100]}")
        gemini_client = getattr(service, "gemini_client", None)
        fetch_limit = request.top_k if request.top_k and request.top_k > 0 else 50
        transformed_docs, hs_metadata = await _build_hs_candidate_documents(
            service=service,
            query=request.query,
            top_k=fetch_limit,
            gemini_client=gemini_client,
        )
        llm_docs = _slim_hs_candidate_docs_for_llm(transformed_docs)

        # Keep only the exact 6-digit family that Gemini extracted, if available.
        hs_prefix = hs_metadata.get("hs_prefix") if isinstance(hs_metadata, dict) else None
        transformed_docs = _filter_docs_to_hs_prefix_family(transformed_docs, hs_prefix)
        llm_docs = _slim_hs_candidate_docs_for_llm(transformed_docs)

        # Step 2: Build simple ranked answer
        # Prefer inferred constraints from metadata (if present)
        inferred_constraints = hs_metadata.get("inferred_constraints") if isinstance(hs_metadata, dict) else None
        if not inferred_constraints:
            inferred_constraints = _derive_vehicle_constraints(request.query)

        constraint_text = ""
        parts = [f"{k}={v}" for k, v in (inferred_constraints or {}).items() if v is not None]
        if parts:
            constraint_text = "Inferred constraints: " + ", ".join(parts) + "\n\n"

        augmented_query = constraint_text + request.query

        if hs_prefix:
            augmented_query = f"HS prefix family: {hs_prefix}\n" + augmented_query

        answer_payload = await build_ranked_hs_answer(
            query=augmented_query,
            transformed_docs=llm_docs,
            generate_answer=request.generate_answer,
            gemini_client=gemini_client,
        )

        # Step 3: Return slim response
        return RankedHSResponse(
            status="success",
            final_answer=answer_payload.get("final_answer"),
            answer_source=answer_payload.get("answer_source"),
        )

    except Exception as e:
        logger.error(f"HS Code Ranked error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"HS Code Ranked failed: {str(e)}",
        )