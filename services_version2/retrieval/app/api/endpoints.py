"""
Endpoints for the retrieval service — HS code classification only.

Exposes:
  - POST /hs-code-candidates
  - POST /hs-code-ranked
  - GET  /health
  - GET  /
"""

import logging
import re
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, Any, List

from .schemas import QueryRequest, QueryResponse, HealthCheckResponse
from prompts import render_prompt

try:
    from ..rag.service import RetrievalService
except ImportError:
    from rag.service import RetrievalService

from pydantic import BaseModel
import json


class RankedHSResponse(BaseModel):
    status: str
    final_answer: Optional[str]
    answer_source: Optional[str]
    is_generic: bool = False
    clarifying_note: Optional[str] = None
    clarifying_questions: Optional[List[str]] = None


logger = logging.getLogger(__name__)

router = APIRouter(tags=["retrieval"])

_service: Optional[RetrievalService] = None


def set_service(service: RetrievalService):
    global _service
    _service = service


def get_service() -> RetrievalService:
    if _service is None:
        raise RuntimeError("Retrieval service not initialized")
    return _service


# ==================== HS candidate helpers ====================




async def build_ranked_hs_answer(
    query: str,
    transformed_docs: List[Dict[str, Any]],
    generate_answer: bool,
    gemini_client=None,
    constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns:
      {
        "final_answer": str | None,           # ranked codes + summary, always populated if candidates exist
        "answer_source": str | None,
        "is_generic": bool,
        "clarifying_note": str | None,
        "clarifying_questions": list[str] | None,
      }
    """
    empty = {
        "final_answer": None, "answer_source": None,
        "is_generic": False, "clarifying_note": None, "clarifying_questions": None,
    }
    if not generate_answer:
        return empty

    if not transformed_docs:
        return {
            **empty,
            "final_answer": "No HS code candidates found for your query.",
            "answer_source": "no_results",
        }

    context_blocks = []
    max_context_docs = min(len(transformed_docs), 40)
    for idx, doc in enumerate(transformed_docs[:max_context_docs], start=1):
        hs_code = doc.get("metadata", {}).get("hs_code", "N/A")
        content = str(doc.get("content", "")).strip()
        score = doc.get("score", 0.0)
        if not content:
            continue
        context_blocks.append(f"[{idx}] HS Code: {hs_code} | Score: {score:.2f} | Description: {content[:600]}")

    if not context_blocks:
        return {
            **empty,
            "final_answer": "No valid HS code candidates found.",
            "answer_source": "no_results",
        }

    candidate_codes = set()
    for d in transformed_docs:
        hc = d.get("metadata", {}).get("hs_code") or ""
        hc_digits = re.sub(r"\D", "", str(hc))
        if hc_digits:
            candidate_codes.add(hc_digits)
    norm_candidates = {re.sub(r"\D", "", c) for c in candidate_codes}
    prefixes = {c[:6] for c in norm_candidates if len(c) >= 6}
    expected_prefix = prefixes.pop() if len(prefixes) == 1 else None

    def _parse_gemini_json(raw: str) -> Optional[dict]:
        if not raw:
            return None
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return None
            return None

    def _valid_codes(parsed: dict) -> bool:
        codes = parsed.get("codes") or []
        if not codes:
            return False
        for c in codes:
            fd = re.sub(r"\D", "", str(c.get("hs_code", "")))
            if fd in norm_candidates:
                continue
            if expected_prefix and fd[:6] == expected_prefix:
                continue
            return False
        return True

    def _format_message(parsed: dict) -> str:
        lines = [parsed.get("message", "").strip()] if parsed.get("message") else []
        for i, c in enumerate(parsed.get("codes", []), 1):
            lines.append(f"{i}. {c.get('hs_code', 'N/A')} - {c.get('description', '').strip()}")
        if parsed.get("is_generic") and parsed.get("clarifying_note"):
            lines.append("")
            lines.append(parsed["clarifying_note"].strip())
        for q in (parsed.get("questions") or []):
            lines.append(f"- {q}")
        return "\n".join(lines).strip()

    if gemini_client is not None:
        prompt = render_prompt(
            "gemini_ranked_hs.txt",
            query=query, constraint_text="",
            candidates="\n".join(context_blocks), limit=5,
        )
        for _ in range(2):  # one retry on malformed/invalid output
            try:
                raw = await gemini_client.generate_answer(
                    query=query, documents=transformed_docs, intent="HS_LOOKUP", prompt_override=prompt,
                )
            except Exception:
                logger.exception("Gemini ranked answer call failed")
                break

            parsed = _parse_gemini_json(raw) if raw else None
            if not parsed:
                prompt += "\n\nYour previous response was not valid JSON. Return ONLY the JSON object, nothing else."
                continue

            if not _valid_codes(parsed):
                prompt += (
                    f"\n\nYour previous selection used codes not in the candidate list or the wrong prefix "
                    f"({expected_prefix or 'unknown'}). Only use candidates listed above."
                )
                continue

            is_generic = bool(parsed.get("is_generic"))
            questions = parsed.get("questions") or []
            return {
                "final_answer": _format_message(parsed),
                "answer_source": "gemini_llm",
                "is_generic": is_generic,
                "clarifying_note": parsed.get("clarifying_note") if is_generic else None,
                "clarifying_questions": questions if is_generic and questions else None,
            }

        logger.warning("Gemini structured ranking failed after retries; falling back to extractive ranking.")

    ranked_text = _format_ranked_hs_lines(query, transformed_docs, limit=5)
    return {
        "final_answer": ranked_text,
        "answer_source": "extractive_ranked",
        "is_generic": False,
        "clarifying_note": None,
        "clarifying_questions": None,
    }
    
def _normalize_hs_digits(value: Optional[str]) -> Optional[str]:
    digits = re.sub(r"\D", "", str(value or ""))
    return digits[:6] if len(digits) >= 6 else None


def _normalize_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _hs_code_family(code: Any) -> Optional[str]:
    digits = re.sub(r"\D", "", str(code or ""))
    return digits[:6] if len(digits) >= 6 else None


def _filter_docs_to_hs_prefix_family(docs: List[Dict[str, Any]], prefix: Optional[str]) -> List[Dict[str, Any]]:
    family = _normalize_hs_digits(prefix)
    if not family:
        return docs
    filtered = [d for d in docs if _hs_code_family(d.get("metadata", {}).get("hs_code") or d.get("hs_code")) == family]
    return filtered or docs


def _slim_hs_candidate_docs_for_llm(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    slim_docs = []
    for doc in docs:
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        hs_code = metadata.get("hs_code") or doc.get("hs_code") or "N/A"
        description = (metadata.get("description") or doc.get("content") or doc.get("description") or "")
        description = str(description).replace("\n", " ").strip()
        hs_prefix = metadata.get("hs_prefix") or _hs_code_family(hs_code)
        slim_docs.append({
            "content": description,
            "metadata": {"hs_code": hs_code, "hs_prefix": hs_prefix, "description": description},
        })
    return slim_docs


def _doc_text_for_filter(doc: Dict[str, Any]) -> str:
    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    parts = [
        doc.get("description"), doc.get("search_text"), doc.get("text"), doc.get("content"),
        metadata.get("description"), metadata.get("search_text"), metadata.get("text"),
    ]
    return _normalize_text(" ".join(str(p or "") for p in parts))


def _extract_cc_ranges(text: str) -> List[tuple]:
    ranges = []
    for low, high in re.findall(
        r"exceeding\s*([0-9][0-9,]*)\s*cc\s*but\s*not\s*exceeding\s*([0-9][0-9,]*)\s*cc", text
    ):
        try:
            ranges.append((int(low.replace(",", "")), int(high.replace(",", ""))))
        except Exception:
            continue
    for low in re.findall(r"exceeding\s*([0-9][0-9,]*)\s*cc", text):
        try:
            v = int(low.replace(",", ""))
            if not any(r[0] == v for r in ranges):
                ranges.append((v, None))
        except Exception:
            continue
    for high in re.findall(r"not\s*exceeding\s*([0-9][0-9,]*)\s*cc", text):
        try:
            v = int(high.replace(",", ""))
            if not any(r[1] == v for r in ranges):
                ranges.append((None, v))
        except Exception:
            continue
    return ranges


def _matches_cc(cc: int, text: str) -> bool:
    ranges = _extract_cc_ranges(text)
    if not ranges:
        return True
    for low, high in ranges:
        if (low is None or cc > low) and (high is None or cc <= high):
            return True
    return False


def _derive_vehicle_constraints(query: str) -> Dict[str, Any]:
    q = _normalize_text(query)
    c: Dict[str, Any] = {"assembly": None, "fuel": None, "body": None, "drive": None, "cc": None}

    if re.search(r"\b(not\s+ckd|non\s*[- ]?ckd|cbu|completely\s+built\s+unit|assembled)\b", q):
        c["assembly"] = "non_ckd"
    elif re.search(r"\b(ckd|completely\s+knocked\s+down|unassembled)\b", q):
        c["assembly"] = "ckd"

    if re.search(r"\bcompression[- ]?ignition\b|\bdiesel\b", q):
        c["fuel"] = "diesel"
    elif re.search(r"\bspark[- ]?ignition\b|\bpetrol\b|\bgasoline\b", q):
        c["fuel"] = "spark"
    elif re.search(r"\belectric\b|\bev\b", q):
        c["fuel"] = "electric"
    elif re.search(r"\bhybrid\b|\bhev\b|\bphev\b|plug[- ]?in", q):
        c["fuel"] = "hybrid"

    if re.search(r"\bsedan\b", q):
        c["body"] = "sedan"
    elif re.search(r"\bhatchback\b", q):
        c["body"] = "hatchback"
    elif re.search(r"\bsuv\b", q):
        c["body"] = "suv"
    elif re.search(r"\bpick\s*[- ]?up\b|\bpickup\b", q):
        c["body"] = "pickup"

    if re.search(r"\b2\s*[- ]?wheel\s*[- ]?drive\b|\b2wd\b|\btwo\s*[- ]?wheel\b", q):
        c["drive"] = "2wd"
    elif re.search(r"\b4\s*[- ]?wheel\s*[- ]?drive\b|\b4wd\b|\b4x4\b|\bawd\b|\ball\s*[- ]?wheel\b", q):
        c["drive"] = "4wd"

    m = re.search(r"(\d{3,5})\s*cc\b", q)
    if m:
        try:
            c["cc"] = int(m.group(1))
        except Exception:
            pass

    has_model = bool(re.search(r"\b[a-z]{1,4}\s*\d{2,4}\b", q)) or bool(re.search(r"\b[a-z]+\s+[a-z]{1,4}\s*\d{2,4}\b", q))
    if has_model:
        if c["body"] is None and not re.search(r"\b(ambulance|hearse|prison|motorhome|motor-home|go-kart|atv|van)\b", q):
            c["body"] = "suv"
        if c["drive"] is None:
            c["drive"] = "4wd"

    return c


def _candidate_support_score(query: str, doc: Dict[str, Any]) -> float:
    q = _normalize_text(query)
    text = _doc_text_for_filter(doc)
    if not q or not text:
        return 0.0

    query_tokens = [t for t in re.findall(r"[a-z0-9\.]+", q) if len(t) > 1]
    text_tokens = set(re.findall(r"[a-z0-9\.]+", text))
    overlap_ratio = len([t for t in query_tokens if t in text_tokens]) / max(1, len(set(query_tokens)))
    score = overlap_ratio * 0.45

    constraints = _derive_vehicle_constraints(query)
    if any(v is not None for v in constraints.values()):
        if constraints.get("assembly") == "non_ckd":
            if re.search(r"\b(cbu|assembled|completely built unit)\b", text):
                score += 0.18
            elif re.search(r"\b(ckd|completely knocked down|unassembled)\b", text):
                score -= 0.25
        elif constraints.get("assembly") == "ckd":
            if re.search(r"\b(ckd|completely knocked down|unassembled)\b", text):
                score += 0.20

        if constraints.get("fuel") == "diesel":
            score += 0.20 if ("diesel" in text or "compression-ignition" in text) else -0.20
        elif constraints.get("fuel") == "spark":
            score += 0.20 if ("spark-ignition" in text or "petrol" in text or "gasoline" in text) else -0.20
        elif constraints.get("fuel") == "hybrid":
            if "electric" in text and ("diesel" in text or "compression-ignition" in text or "petrol" in text or "gasoline" in text):
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
            score += 0.18 if re.search(r"\b(4wd|4x4|four-wheel\s+drive|all-wheel|awd)\b", text) else -0.15
        elif constraints.get("drive") == "2wd":
            score += 0.15 if re.search(r"\b(2wd|two-wheel\s+drive)\b", text) else 0.0

        cc = constraints.get("cc")
        if isinstance(cc, int):
            score += 0.20 if _matches_cc(cc, text) else -0.10

    if any(t in q for t in ("vehicle", "car", "suv", "truck", "van")):
        if any(t in text for t in ("vehicle", "car", "suv", "truck", "van")):
            score += 0.05

    if _derive_vehicle_constraints(query).get("body") == "suv":
        if re.search(r"\b(ambulance|hearse|prison van|prison|motor-home|motorhome|go[- ]?kart|atv|all[- ]terrain vehicle|sedan)\b", text):
            score -= 0.35

    return max(0.0, min(1.0, score))


def _hs_result_confident(query: str, docs: List[Dict[str, Any]]) -> bool:
    if not docs:
        return False
    return _candidate_support_score(query, docs[0]) >= 0.55


def _humanize_hs_text(text: str, max_segments: int = 3) -> str:
    raw = re.sub(r"\s+", " ", str(text or "").strip())
    if not raw:
        return "Short description unavailable"
    raw = raw.replace(" > ", "; ")
    segments = [s.strip(" ;:-") for s in re.split(r"[>;]", raw) if s.strip(" ;:-")]
    parts, seen = [], set()
    for s in segments:
        if s and s not in seen:
            seen.add(s)
            parts.append(s)
        if len(parts) >= max_segments:
            break
    if parts:
        leading = parts[0].lower()
        if leading.startswith("motor cars and other motor vehicles principally designed for the transport of persons"):
            parts = parts[1:] or parts[:1]
        elif leading.startswith("motor vehicles for the transport of goods"):
            parts = parts[1:] or parts[:1]
    if not parts:
        return raw.strip(" ;:-") or "Short description unavailable"
    sentence = re.sub(r",\s+,", ", ", re.sub(r"\s+,", ",", ", ".join(parts)))
    return sentence[:140].rstrip()


def _format_ranked_hs_lines(query: str, docs: List[Dict[str, Any]], limit: int = 5) -> str:
    if not docs:
        return "No ranked results available."
    ranked = sorted(docs, key=lambda d: _candidate_support_score(query, d), reverse=True)
    return "\n".join(
        f"{i}. HS {str(d.get('metadata', {}).get('hs_code') or d.get('hs_code') or 'N/A').strip()}: {_humanize_hs_text(d.get('content') or d.get('description') or '', max_segments=3)}"
        for i, d in enumerate(ranked[:limit], 1)
    )


def _apply_hard_vehicle_filters(
    query: str, docs: List[Dict[str, Any]], constraints: Optional[Dict[str, Any]] = None
) -> tuple:
    if constraints is None:
        constraints = _derive_vehicle_constraints(query)
    filtered = []
    for doc in docs:
        text = _doc_text_for_filter(doc)
        assembly = constraints.get("assembly")
        if assembly == "ckd" and not re.search(r"\b(ckd|completely\s+knocked\s+down|unassembled)\b", text):
            continue
        if assembly == "non_ckd" and re.search(r"\b(ckd|completely\s+knocked\s+down|unassembled)\b", text):
            continue
        fuel = constraints.get("fuel")
        if fuel == "diesel" and not ("compression-ignition" in text or "diesel" in text):
            continue
        if fuel == "spark" and not ("spark-ignition" in text or "petrol" in text or "gasoline" in text):
            continue
        if fuel == "electric" and "electric motor" not in text:
            continue
        if fuel == "hybrid" and ("electric motor" not in text or ("spark-ignition" not in text and "compression-ignition" not in text)):
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
        if drive == "2wd" and re.search(r"\b(4wd|4x4|four-wheel\s+drive|all-wheel|awd)\b", text):
            continue
        if drive == "4wd" and not re.search(r"\b(4wd|4x4|four-wheel\s+drive|all-wheel|awd)\b", text):
            continue
        cc = constraints.get("cc")
        if isinstance(cc, int) and not _matches_cc(cc, text):
            continue
        if body == "suv" and re.search(r"\b(ambulance|hearse|prison van|prison|motor-home|motorhome|go[- ]?kart|atv|all[- ]terrain vehicle)\b", text):
            continue
        filtered.append(doc)
    return filtered, {"filter_constraints": constraints, "filter_input_count": len(docs), "filter_output_count": len(filtered)}


async def _extract_hs_prefix_with_gemini(gemini_client, query: str) -> Optional[str]:
    if gemini_client is None:
        return None
    prompt = render_prompt("gemini_extract_specs.txt", query=query)

    async def _run(p: str) -> Optional[str]:
        try:
            raw = await gemini_client.generate_answer(query=p, documents=[], intent="EXTRACT_SPECS")
        except Exception as exc:
            logger.warning(f"HS prefix extraction failed: {exc}")
            return None
        prefix = _normalize_hs_digits(raw)
        return prefix if prefix and re.fullmatch(r"\d{6}", prefix) else None

    prefix = await _run(prompt)
    if prefix:
        return prefix
    return await _run(render_prompt("gemini_extract_specs_retry.txt", query=query))


async def _build_hs_candidate_documents(
    service: RetrievalService, query: str, top_k: int, gemini_client,
) -> tuple:
    import asyncio
    collection_name = getattr(service.config, "qdrant_hs_code_collection", "gdce_hs_code")
    raw_limit = min(max(int(top_k or 27) * 2, 60), 100)

    prefix, semantic_results = await asyncio.gather(
        asyncio.create_task(_extract_hs_prefix_with_gemini(gemini_client, query)),
        asyncio.create_task(service.orchestrator.retrieve_semantic(query, top_k=27, collection_name=collection_name)),
        return_exceptions=True,
    )

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
        return d.get("hs_code") or m.get("hs_code") or m.get("hscode") or m.get("tariff_code")

    if prefix:
        raw_docs = await service.fetch_hs_documents_by_prefix_async(prefix, collection_name=collection_name, limit=raw_limit)
        source = "structured_prefix_scan_full"
        if raw_docs:
            raw_docs = service._score_hs_candidates_by_query(query=query, documents=raw_docs, target_heading=prefix[:4])
            constraints = _derive_vehicle_constraints(query)
            if any(v is not None for v in constraints.values()):
                filtered_docs, filter_meta = _apply_hard_vehicle_filters(query, raw_docs, constraints)
                if filter_meta.get("filter_output_count", 0) > 0:
                    raw_docs = filtered_docs
                    logger.info(f"Hard filters applied after prefix scan: {filter_meta['filter_input_count']} → {filter_meta['filter_output_count']} docs")
                else:
                    relaxed = {**constraints, "body": None, "cc": None, "drive": None}
                    relaxed_docs, relaxed_meta = _apply_hard_vehicle_filters(query, raw_docs, relaxed)
                    if relaxed_meta.get("filter_output_count", 0) > 0:
                        raw_docs = relaxed_docs
                        filter_meta = {**relaxed_meta, "filters_relaxed": [k for k in ("body", "cc", "drive") if constraints.get(k) is not None]}
                        logger.info(f"Relaxed filters applied after prefix scan: {relaxed_meta['filter_input_count']} → {relaxed_meta['filter_output_count']} docs")

            if len(raw_docs) < 3 and semantic_results:
                existing_codes = {str(get_code(d)).strip() for d in raw_docs if get_code(d)}
                added_count = 0
                for idx, doc in enumerate(semantic_results):
                    code = get_code(doc)
                    code_str = str(code).strip() if code else ""
                    if code_str and code_str not in existing_codes:
                        raw_docs.append({**doc, "id": doc.get("id", f"sem_{idx}"), "content": doc.get("content") or doc.get("description") or doc.get("text") or "", "score": doc.get("score", 0.5), "retrieval_source": "semantic", "metadata": doc.get("metadata") or {"hs_code": code}})
                        existing_codes.add(code_str)
                        added_count += 1
                        if len(raw_docs) >= 3 or added_count >= 5:
                            break
                source = f"prefix_scan_with_semantic_fill_{added_count}"

    if not raw_docs:
        raw_docs = [{**doc, "id": doc.get("id", str(idx)), "content": doc.get("content") or doc.get("description") or doc.get("text") or "", "score": doc.get("score", 0.5), "retrieval_source": "semantic", "metadata": doc.get("metadata") or {"hs_code": get_code(doc)}} for idx, doc in enumerate(semantic_results or [])]
        source = "semantic_fallback"
        try:
            constraints = _derive_vehicle_constraints(query)
            if any(v is not None for v in constraints.values()):
                filtered_docs, filter_meta = _apply_hard_vehicle_filters(query, raw_docs, constraints)
                if filter_meta.get("filter_output_count", 0) > 0:
                    raw_docs = filtered_docs
                else:
                    relaxed = {**constraints, "body": None, "cc": None, "drive": None}
                    relaxed_docs, relaxed_meta = _apply_hard_vehicle_filters(query, raw_docs, relaxed)
                    if relaxed_meta.get("filter_output_count", 0) > 0:
                        raw_docs = relaxed_docs
                        filter_meta = {**relaxed_meta, "filters_relaxed": [k for k in ("body", "cc", "drive") if constraints.get(k) is not None]}
        except Exception:
            filter_meta = {}

    transformed_docs = [
        transform_document({**doc, "id": doc.get("id", str(idx)), "content": doc.get("content") or doc.get("description") or doc.get("text") or "", "score": doc.get("score", 0.5), "retrieval_source": doc.get("retrieval_source", "structured_prefix_scan_full" if prefix else "semantic")})
        for idx, doc in enumerate(raw_docs)
    ]

    metadata = {k: v for k, v in {"hs_prefix": prefix, "candidate_source": source, **filter_meta}.items() if v is not None}
    return transformed_docs, metadata


def transform_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    content = doc.get("text") or doc.get("content") or doc.get("description") or doc.get("title") or ""
    doc_id = str(doc.get("id") or doc.get("doc_id") or "unknown")
    score = doc.get("score", 0.5)
    source = doc.get("retrieval_source", "semantic")
    metadata = {"doc_id": doc.get("doc_id"), "title": doc.get("title"), "hs_code": doc.get("hs_code"), "source_url": doc.get("source_url"), "description": doc.get("description")}
    for key, value in doc.items():
        if key not in ["id", "score", "content", "text", "retrieval_source"] and not key.startswith("_"):
            metadata[key] = value
    return {"id": doc_id, "content": str(content)[:1000] if content else "", "score": float(score) if score else 0.5, "source": source, "metadata": {k: v for k, v in metadata.items() if v is not None}}


# ==================== Endpoints ====================

@router.post("/hs-code-candidates", tags=["Intent: HS Code Candidates"], response_model=QueryResponse)
async def hs_code_candidates_endpoint(
    request: QueryRequest,
    service: RetrievalService = Depends(get_service),
) -> QueryResponse:
    """HS Code Candidates - LLM-powered candidate selection and explanation."""
    try:
        logger.info(f"HS Code Candidates request: {request.query[:100]}")
        gemini_client = getattr(service, "gemini_client", None)
        fetch_limit = request.top_k if request.top_k and request.top_k > 0 else 50

        transformed_docs, hs_metadata = await _build_hs_candidate_documents(service=service, query=request.query, top_k=fetch_limit, gemini_client=gemini_client)
        confidence_ok = _hs_result_confident(request.query, transformed_docs)
        llm_docs = _slim_hs_candidate_docs_for_llm(transformed_docs)

        if request.generate_answer and transformed_docs:
            candidate_lines = []
            for idx, doc in enumerate(llm_docs[:50], start=1):
                md = doc.get("metadata", {}) if isinstance(doc.get("metadata"), dict) else {}
                hs_code = md.get("hs_code") or "N/A"
                hs_prefix = md.get("hs_prefix") or "N/A"
                desc = (md.get("description") or doc.get("content") or "").strip().replace("\n", " ")
                candidate_lines.append(f"[{idx}] HS {hs_code} | Prefix {hs_prefix} | Description: {desc[:400]}")

            candidates_text = "Candidates:\n" + "\n".join(candidate_lines) + "\n\n"
            llm_prompt = render_prompt(
                "gemini_ranked_hs.txt",
                query=request.query,
                constraint_text="",
                candidates=candidates_text,
                limit=5,
            )
            answer_payload = await build_ranked_hs_answer(
                query=llm_prompt, transformed_docs=llm_docs, generate_answer=True, gemini_client=gemini_client
            )
        else:
            answer_payload = {"final_answer": None, "answer_source": None}

        metadata = {**hs_metadata, "candidate_confidence": "high" if confidence_ok else "low"}
        return QueryResponse(**{
            "query": request.query, "status": "success",
            "documents": transformed_docs, "total_count": len(transformed_docs),
            "semantic_count": len(transformed_docs), "structured_count": 0,
            "final_answer": answer_payload.get("final_answer"),
            "answer_source": answer_payload.get("answer_source"),
            "is_generic": answer_payload.get("is_generic", False),
            "clarifying_note": answer_payload.get("clarifying_note"),
            "clarifying_questions": answer_payload.get("clarifying_questions"),
            
            "clarification_needed": answer_payload.get("clarification_needed", False),
            "clarifying_questions": answer_payload.get("clarifying_questions"),
            "session_id": request.session_id, "api_called": "/v1/hs-code-candidates",
            "collection_used": "gdce_hs_code", "language": None,
            "required_parameters": ["query"], "missing_parameters": None,
            "metadata": metadata, "error": None,
        })
    except Exception as e:
        logger.error(f"HS Code Candidates error: {e}")
        raise HTTPException(status_code=500, detail=f"HS Code Candidates failed: {str(e)}")


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(service: RetrievalService = Depends(get_service)) -> HealthCheckResponse:
    """Check health of retrieval service."""
    try:
        return HealthCheckResponse(**(await service.health_check()))
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthCheckResponse(status="unhealthy", components={"error": {"message": str(e)}})


@router.get("/", tags=["Health"], response_model=dict)
def root():
    """Root endpoint."""
    return {
        "service": "Retrieval Service v2 (HS Code Classification)",
        "version": "2.0.0",
        "port": 8003,
        "scope": "HS code classification only — general/FAQ/policy queries handled by general service (port 8005)",
        "endpoints": {
            "health": "GET /health",
            "hs_code_candidates": "POST /hs-code-candidates",
            "hs_code_ranked": "POST /hs-code-ranked",
            "swagger": "/docs",
            "openapi": "/openapi.json",
        },
    }


@router.post("/hs-code-ranked", tags=["Intent: HS Code Ranked"], response_model=RankedHSResponse)
async def hs_code_ranked_endpoint(
    request: QueryRequest,
    service: RetrievalService = Depends(get_service),
) -> RankedHSResponse:
    """HS Code Ranked — returns a simple ranked list of HS codes with short descriptions."""
    try:
        logger.info(f"HS Code Ranked request: {request.query[:100]}")
        gemini_client = getattr(service, "gemini_client", None)
        fetch_limit = request.top_k if request.top_k and request.top_k > 0 else 50

        transformed_docs, hs_metadata = await _build_hs_candidate_documents(service=service, query=request.query, top_k=fetch_limit, gemini_client=gemini_client)
        hs_prefix = hs_metadata.get("hs_prefix") if isinstance(hs_metadata, dict) else None
        transformed_docs = _filter_docs_to_hs_prefix_family(transformed_docs, hs_prefix)
        llm_docs = _slim_hs_candidate_docs_for_llm(transformed_docs)

        inferred_constraints = hs_metadata.get("inferred_constraints") if isinstance(hs_metadata, dict) else None
        if not inferred_constraints:
            inferred_constraints = _derive_vehicle_constraints(request.query)

        parts = [f"{k}={v}" for k, v in (inferred_constraints or {}).items() if v is not None]
        constraint_text = ("Inferred constraints: " + ", ".join(parts) + "\n\n") if parts else ""
        augmented_query = (f"HS prefix family: {hs_prefix}\n" if hs_prefix else "") + constraint_text + request.query

        answer_payload = await build_ranked_hs_answer(
            query=augmented_query, transformed_docs=llm_docs, generate_answer=request.generate_answer, gemini_client=gemini_client
        )
        return RankedHSResponse(
            status="success",
            final_answer=answer_payload.get("final_answer"),
            answer_source=answer_payload.get("answer_source"),
            is_generic=answer_payload.get("is_generic", False),
            clarifying_note=answer_payload.get("clarifying_note"),
            clarifying_questions=answer_payload.get("clarifying_questions"),
        )
    except Exception as e:
        logger.error(f"HS Code Ranked error: {e}")
        raise HTTPException(status_code=500, detail=f"HS Code Ranked failed: {str(e)}")