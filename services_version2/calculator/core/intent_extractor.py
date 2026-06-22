"""
GDCE Calculator Service - LLM Intent Extractor
===============================================
Extracts structured calculation parameters from natural-language user queries.

Uses an LLM (Ollama/Gemini) as the primary extractor, with a deterministic
regex fallback for speed and reliability when the LLM is unavailable.

Output: IntentResult dataclass containing case_type, goods, valuation, flags,
and extraction metadata.

Usage:
    extractor = IntentExtractor()
    result = await extractor.extract("calculate import tax for HS 2710.12.26 ...")
    # result.case_type -> "petroleum"
    # result.goods -> {"hs_code": "2710.12.26", ...}
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Country name → ISO code mapping (same as calculator_chat_v3.py)
# ---------------------------------------------------------------------------
_COUNTRY_MAP: Dict[str, str] = {
    "china": "CN", "chinese": "CN", "prc": "CN",
    "thailand": "TH", "thai": "TH",
    "vietnam": "VN", "vietnamese": "VN", "viet nam": "VN",
    "usa": "US", "united states": "US", "america": "US", "us": "US",
    "cambodia": "KH", "kampuchea": "KH",
    "japan": "JP", "korea": "KR", "south korea": "KR",
    "malaysia": "MY", "singapore": "SG", "indonesia": "ID",
    "philippines": "PH", "laos": "LA", "myanmar": "MM", "burma": "MM",
    "india": "IN", "australia": "AU", "new zealand": "NZ",
    "germany": "DE", "france": "FR", "uk": "GB", "united kingdom": "GB",
    "russia": "RU", "canada": "CA", "mexico": "MX", "brazil": "BR",
}


# ---------------------------------------------------------------------------
# Regex patterns (ported from calculator_chat_v3.py for fallback)
# ---------------------------------------------------------------------------
_HS_RE = re.compile(r"\b(\d{4}(?:\.\d{2}){1,2}|\d{6}|\d{8})\b")
_VOL_RE = re.compile(r"(\d[\d,.]*)\s*(?:L|l|liters?|litres?)\b")
_MASS_RE = re.compile(r"(\d[\d,.]*)\s*(?:kg|kgs|kilos?|kilograms?)\b")
_TON_RE = re.compile(r"(\d[\d,.]*)\s*(?:tons?|tonnes?)\b")
_DV_RE = re.compile(r"DV\s*=\s*([\d,.]+)", re.IGNORECASE)
_DQ_RE = re.compile(r"DQ\s*(?:factor|percentage|percent|pct)?\s*[:=]?\s*([\d,.]+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# IntentResult
# ---------------------------------------------------------------------------
@dataclass
class IntentResult:
    """Structured extraction result."""

    case_type: str = "normal"          # petroleum | rubber | fta_dv | fta_dv_dq | normal
    regime: str = "import"             # import | export
    goods: Dict[str, Any] = field(default_factory=dict)
    valuation: Dict[str, Any] = field(default_factory=dict)
    flags: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    reasoning: str = ""
    source: str = ""                     # "llm" | "regex" | "none"


# ---------------------------------------------------------------------------
# IntentExtractor
# ---------------------------------------------------------------------------
class IntentExtractor:
    """
    Extract calculation intent from natural language.

    Primary: LLM (Ollama / Gemini)
    Fallback: deterministic regex (same logic as calculator_chat_v3)
    """

    def __init__(
        self,
        llm_host: Optional[str] = None,
        llm_port: Optional[int] = None,
        llm_model: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout: Optional[float] = None,
    ):
        settings = get_settings()
        self.llm_host = llm_host or getattr(settings, "llm_host", None) or "127.0.0.1"
        self.llm_port = llm_port or getattr(settings, "llm_port", None) or 11434
        self.llm_url = f"http://{self.llm_host}:{self.llm_port}"
        self.model = llm_model or getattr(settings, "intent_llm_model", None) or "llama3.2:3b"
        self.enabled = enabled if enabled is not None else getattr(settings, "intent_llm_enabled", True)
        self.timeout = timeout or getattr(settings, "intent_llm_timeout", 10.0)
        self.gemini_api_key = getattr(settings, "gemini_api_key", "").strip()
        self._prompt_template = self._build_prompt_template()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract(self, text: str) -> IntentResult:
        """
        Extract intent from user text.

        Priority:
          1. LLM extraction (if enabled and available)
          2. Regex fallback
          3. Return empty IntentResult with source="none"
        """
        if self.enabled:
            try:
                llm_result = await self._extract_llm(text)
                if llm_result and llm_result.confidence >= 0.5:
                    logger.info(f"LLM intent extraction succeeded (confidence={llm_result.confidence})")
                    return llm_result
            except Exception as e:
                logger.warning(f"LLM intent extraction failed: {e}")

        # Regex fallback
        regex_result = self._extract_regex(text)
        if regex_result:
            logger.info(f"Regex intent extraction succeeded (case={regex_result.case_type})")
            return regex_result

        logger.warning("Intent extraction failed: both LLM and regex returned nothing")
        return IntentResult(source="none", reasoning="Could not parse query")

    def extract_sync(self, text: str) -> IntentResult:
        """Synchronous wrapper."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is None:
            return asyncio.run(self.extract(text))
        # Inside running loop — schedule but return regex immediately to avoid blocking
        return self._extract_regex(text) or IntentResult(source="none")

    # ------------------------------------------------------------------
    # LLM extraction
    # ------------------------------------------------------------------

    async def _extract_llm(self, text: str) -> Optional[IntentResult]:
        prompt = self._prompt_template.replace("{USER_QUERY}", text)

        raw = await self._call_llm(prompt)
        if not raw:
            return None

        # Strip markdown fences if present
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"LLM returned invalid JSON: {e}\nRaw: {raw[:200]}")
            return None

        return self._map_llm_response(data)

    def _map_llm_response(self, data: Dict[str, Any]) -> Optional[IntentResult]:
        """Validate and map LLM JSON into IntentResult."""
        if not isinstance(data, dict):
            return None

        case_type = (data.get("case_type") or "normal").lower()
        regime = (data.get("regime") or "import").lower()

        goods = data.get("goods") or {}
        valuation = data.get("valuation") or {}
        flags = data.get("flags") or {}

        # Normalize HS code
        hs = goods.get("hs_code")
        if hs:
            goods["hs_code"] = self._normalize_hs_code(str(hs))

        # Normalize origin
        origin = goods.get("origin_country")
        if origin and len(origin) != 2:
            goods["origin_country"] = self._normalize_origin(str(origin))

        # Ensure description is present (required by GoodsModel)
        if not goods.get("description"):
            hs = goods.get("hs_code", "")
            if hs and str(hs).startswith("27"):
                goods["description"] = "Petroleum products"
            elif hs and str(hs).startswith("40"):
                goods["description"] = "Rubber products"
            elif case_type == "petroleum":
                goods["description"] = "Petroleum products"
            elif case_type == "rubber":
                goods["description"] = "Rubber products"
            else:
                goods["description"] = "General merchandise"

        # Ensure declared_value_basis for petroleum
        if case_type == "petroleum" and valuation.get("declared_value") is not None:
            valuation["declared_value_basis"] = valuation.get("declared_value_basis", "per_ton")

        # Normalize dq_factor: if LLM returns 40 instead of 0.4, convert it
        dq = valuation.get("dq_factor")
        if dq is not None:
            try:
                dq_val = float(dq)
                if dq_val > 1:
                    dq_val = dq_val / 100
                valuation["dq_factor"] = dq_val
            except (ValueError, TypeError):
                pass
            flags["dq_applicable"] = True
            case_type = "fta_dv_dq"

        confidence = float(data.get("confidence", 0.5))
        reasoning = str(data.get("reasoning", ""))

        return IntentResult(
            case_type=case_type,
            regime=regime,
            goods=goods,
            valuation=valuation,
            flags=flags,
            confidence=confidence,
            reasoning=reasoning,
            source="llm",
        )

    async def _call_llm(self, prompt: str) -> str:
        """
        Call LLM endpoint.
        Routes to Gemini API when model starts with 'gemini',
        otherwise calls Ollama-style /api/generate.
        """
        if self.model.lower().startswith("gemini"):
            return await self._call_gemini(prompt)
        return await self._call_ollama(prompt)

    async def _call_ollama(self, prompt: str) -> str:
        """Call Ollama-style /api/generate endpoint."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.llm_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.1,
                    "format": "json",
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()

    async def _call_gemini(self, prompt: str) -> str:
        """Call Gemini REST API directly via httpx."""
        if not self.gemini_api_key:
            raise RuntimeError("Gemini API key not configured (set GEMINI_API_KEY)")

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.gemini_api_key}"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "responseMimeType": "application/json",
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return ""
            parts = candidates[0].get("content", {}).get("parts", [])
            return parts[0].get("text", "").strip() if parts else ""

    # ------------------------------------------------------------------
    # Regex fallback (ported from calculator_chat_v3.py)
    # ------------------------------------------------------------------

    def _extract_regex(self, text: str) -> Optional[IntentResult]:
        lowered = text.lower()

        # HS code
        hs = self._extract_hs(text)

        # Money
        val, cur = self._extract_money(text)

        # Origin
        origin = self._normalize_origin(text)

        # Volume / mass
        vol = self._extract_volume(text)
        mass = self._extract_mass(text)

        # DV
        dv = self._extract_dv(text)

        # DQ factor
        dq_factor = self._extract_dq_factor(text)

        # Description (strip known tokens)
        desc = self._extract_description(text, hs)

        # Flags / case detection
        flags: Dict[str, Any] = {}
        case_type = "normal"

        # Petroleum
        is_petroleum = False
        if hs and hs.startswith("27"):
            is_petroleum = True
        if any(k in lowered for k in ("petroleum", "gasoline", "diesel", "fuel", "motor spirit")):
            is_petroleum = True
        if is_petroleum:
            flags["petroleum_case"] = True
            case_type = "petroleum"

        # Rubber
        is_rubber = False
        if hs and hs.startswith("40"):
            is_rubber = True
        if "rubber" in lowered:
            is_rubber = True
        if is_rubber:
            flags["rubber_case"] = True
            case_type = "rubber"

        # FTA
        if any(k in lowered for k in ("fta", "preferential", "acfta", "asean", "aanzfta", "ajcep", "akfta")):
            flags["fta_applicable"] = True
            case_type = "fta_dv"
            if "acfta" in lowered:
                flags["fta_certificate_type"] = "ACFTA"
            elif "asean" in lowered:
                flags["fta_certificate_type"] = "ASEAN"
            elif "aanzfta" in lowered:
                flags["fta_certificate_type"] = "AANZFTA"

        # DQ
        if "dq" in lowered or (flags.get("fta_applicable") and "quota" in lowered):
            flags["dq_applicable"] = True
            case_type = "fta_dv_dq"

        # QIP / SEZ
        if "qip" in lowered:
            flags["qip_exemption"] = True
        if "sez" in lowered:
            flags["sez_applicable"] = True

        # Regime
        regime = "export" if "export" in lowered else "import"
        if is_rubber:
            regime = "export"

        # If we have no value, no HS code, AND no description, fail
        # Allow description-only queries — the calculator will resolve HS code from description
        has_desc = bool(desc and desc not in ("General merchandise", "Petroleum products", "Rubber products"))
        if val is None and not hs and not has_desc:
            return None

        # Default CIF to 8000 when user does not provide a value
        cif_defaulted = val is None
        customs_value = val if val is not None else 8000.0

        goods: Dict[str, Any] = {"description": desc}
        if hs:
            goods["hs_code"] = hs
        if origin:
            goods["origin_country"] = origin
        if mass:
            goods["net_mass_kg"] = mass
        if vol:
            goods["volume_liter"] = vol

        valuation: Dict[str, Any] = {
            "customs_value": customs_value,
            "currency": (cur or "USD").upper(),
            "declared_value_basis": "total",
        }
        if dv is not None:
            valuation["declared_value"] = dv
            if case_type == "petroleum":
                valuation["declared_value_basis"] = "per_ton"
        if dq_factor is not None:
            valuation["dq_factor"] = dq_factor

        reasoning_parts = ["Extracted via deterministic regex fallback"]
        if cif_defaulted:
            reasoning_parts.append("CIF value defaulted to 8000 USD (user did not provide)")

        return IntentResult(
            case_type=case_type,
            regime=regime,
            goods=goods,
            valuation=valuation,
            flags=flags,
            confidence=0.6,
            reasoning="; ".join(reasoning_parts),
            source="regex",
        )

    # ------------------------------------------------------------------
    # Helpers (ported from calculator_chat_v3.py)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_hs_code(raw: str) -> str:
        clean = raw.replace(".", "")
        if len(clean) == 8:
            return f"{clean[:4]}.{clean[4:6]}.{clean[6:8]}"
        elif len(clean) == 6:
            return f"{clean[:4]}.{clean[4:6]}"
        return raw

    @staticmethod
    def _normalize_origin(text: str) -> Optional[str]:
        lowered = text.lower()
        for name, code in _COUNTRY_MAP.items():
            if name in lowered:
                return code
        # 2-letter codes
        for w in re.findall(r"\b([A-Za-z]{2})\b", text):
            wu = w.upper()
            if wu in set(_COUNTRY_MAP.values()):
                return wu
        return text.upper() if len(text) == 2 else None

    @staticmethod
    def _extract_hs(text: str) -> Optional[str]:
        m = _HS_RE.search(text)
        return IntentExtractor._normalize_hs_code(m.group(1)) if m else None

    @staticmethod
    def _extract_money(text: str) -> tuple[Optional[float], Optional[str]]:
        for pat in [
            r"[\$\€\£\¥]\s*([\d,.]+(?:\s*[KkMmBb])?)\s*(?:USD|usd)?",
            r"([\d,.]+(?:\s*[KkMmBb])?)\s*(?:USD|usd)",
        ]:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return IntentExtractor._expand_number(m.group(1)), "USD"
        m = re.search(r"([\d,.]+(?:\s*[KkMmBb])?)\s*(KHR|khr|EUR|eur)", text, re.IGNORECASE)
        if m:
            return IntentExtractor._expand_number(m.group(1)), m.group(2).upper()
        m = re.search(r"\b([\d,.]+(?:\s*[KkMmBb])?)\b", text)
        if m:
            return IntentExtractor._expand_number(m.group(1)), None
        return None, None

    @staticmethod
    def _expand_number(s: str) -> float:
        s = s.strip().upper().replace(",", "")
        mult = 1.0
        if s.endswith("K"):
            mult = 1_000
            s = s[:-1]
        elif s.endswith("M"):
            mult = 1_000_000
            s = s[:-1]
        elif s.endswith("B"):
            mult = 1_000_000_000
            s = s[:-1]
        return float(s) * mult

    @staticmethod
    def _extract_volume(text: str) -> Optional[float]:
        m = _VOL_RE.search(text)
        return float(m.group(1).replace(",", "")) if m else None

    @staticmethod
    def _extract_mass(text: str) -> Optional[float]:
        m = _MASS_RE.search(text)
        if m:
            return float(m.group(1).replace(",", ""))
        m = _TON_RE.search(text)
        if m:
            return float(m.group(1).replace(",", "")) * 1000
        return None

    @staticmethod
    def _extract_dv(text: str) -> Optional[float]:
        m = _DV_RE.search(text)
        return float(m.group(1).replace(",", "")) if m else None

    @staticmethod
    def _extract_dq_factor(text: str) -> Optional[float]:
        m = _DQ_RE.search(text)
        if m:
            val = float(m.group(1).replace(",", ""))
            # DQ may be expressed as percentage (40 → 0.4) or decimal (0.4 → 0.4)
            if val > 1:
                val = val / 100
            return val
        return None

    @staticmethod
    def _extract_description(text: str, hs_code: Optional[str]) -> str:
        desc = text
        if hs_code:
            desc = desc.replace(hs_code, "")
        desc = re.sub(r"DV\s*=\s*[\d,.]+", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"[\$\€\£\¥]?\s*[\d,.]+(?:\s*[KkMmBb])?\s*(?:USD|usd|\$)?", "", desc)
        desc = re.sub(r"\d[\d,.]*\s*(?:kg|kgs|kilos?|kilograms?|liters?|litres?|tons?|tonnes?|L)\b", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\b[\d,.]+(?:\s*[KkMmBb])?\b", "", desc)
        fluff = [
            "calculate", "import", "tax", "duty", "for", "hs", "code", "cif",
            "from", "with", "and", "the", "of", "net", "mass", "volume",
            "product", "goods", "item", "consignment", "to", "pay", "value",
        ]
        for word in fluff:
            desc = re.sub(rf"\b{word}\b", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\s+", " ", desc).strip(",. ")
        if len(desc) < 3 or any(bad in desc.lower() for bad in ("massgl", "gkg", "kgl", "ll", "kgkg")):
            if hs_code and hs_code.startswith("27"):
                return "Petroleum products"
            if hs_code and hs_code.startswith("40"):
                return "Rubber products"
            return "General merchandise"
        return desc

    # ------------------------------------------------------------------
    # Prompt template
    # ------------------------------------------------------------------

    def _build_prompt_template(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""You are a Cambodian customs intent extractor.
Your job: read the user's natural-language query and output a JSON object
that exactly matches the calculator request schema.

Supported cases:
- normal: standard import (CIF + duty + VAT)
- petroleum: HS 27xx + volume (liters) + net mass (kg) + DV per metric ton
- rubber: export regime + HS 40xx + net mass (kg)
- fta_dv: import with FTA certificate (Form D, E, AK, AJ, RCEP, AANZ)
- fta_dv_dq: FTA case + DQ factor

Schema fields you MUST extract:
- hs_code: normalize bare 8-digit → dotted (e.g. 27101229 → 2710.12.29)
- customs_value: CIF value (number only)
- currency: USD, KHR, or symbol ($ → USD, ៛ → KHR)
- origin_country: 2-letter ISO code (e.g. VN, CN, TH, US)
- net_mass_kg: weight in kilograms
- volume_liter: volume in liters (only for petroleum)
- declared_value + declared_value_basis: per_ton for petroleum, total otherwise
- dq_factor: decimal 0-1 (e.g. 0.4 for 40% DQ). If user says "DQ=40%" output 0.4.
- regime: import or export
- flags:
  - petroleum_case: true if HS 27xx or keywords (petroleum, gasoline, diesel, fuel, motor spirit)
  - rubber_case: true if HS 40xx or keyword "rubber"
  - fta_applicable: true if FTA/ASEAN/ACFTA/preferential mentioned
  - fta_certificate_type: ACFTA, ASEAN, AANZFTA, AJCEP, AKFTA, RCEP
  - dq_applicable: true if DQ or quota mentioned
  - qip_exemption: true if QIP mentioned
  - sez_applicable: true if SEZ mentioned

Rules:
1. Return ONLY a JSON object. No markdown, no explanation outside JSON.
2. If a field is missing in the text, omit it from the JSON (do not guess).
3. For currency, default to USD if not specified.
4. For origin, default to General (omit) if not specified.
5. For regime, default to import unless "export" is explicitly stated.
6. For numbers with K/M/B suffixes, expand them (2.2M → 2200000).
7. HS CODE NORMALIZATION IS CRITICAL:
   - If the user types a bare 8-digit number like "12345678", you MUST output "1234.56.78".
   - If the user types a bare 6-digit number like "123456", you MUST output "1234.56".
   - If the user already typed dots ("1234.56.78"), keep it exactly as-is.
   - Never return a bare number without dots in the hs_code field.
8. If the query mentions "DV = 700" for petroleum, set declared_value=700 and declared_value_basis="per_ton".
9. If the query mentions "DV = 5" for a normal/FTA case, set declared_value=5 and declared_value_basis="total" (DV is the COP rate percentage).
10. If the user does NOT provide a CIF value (no price, no amount, no money mentioned), you MUST set customs_value = 8000 and add "CIF value defaulted to 8000 USD (user did not provide)" to your reasoning. Do NOT set customs_value to 0.
11. COMMERCIAL DESCRIPTIONS ARE VALID INPUT: If the user provides a product description but NO explicit HS code (e.g., "iphone 15 from china", "toyota camry 2024", "rice from thailand"), you MUST extract the description into goods.description and leave hs_code null. Do NOT fail or return an error. The calculator will resolve the HS code automatically from the description. Always include the description field when the user mentions a product name.
12. Be robust to typos, misspellings, and noisy input (e.g. "ciiif valueb umport vietmam" → infer CIF value, import, Vietnam). Do NOT fail just because words are misspelled.

Today's date: {today}

User query: "{{USER_QUERY}}"

Return ONLY JSON:
{{
  "case_type": "...",
  "regime": "...",
  "goods": {{
    "hs_code": "1234.56.78",
    "description": "...",
    "origin_country": "...",
    "net_mass_kg": 0,
    "volume_liter": 0
  }},
  "valuation": {{
    "customs_value": 0,
    "currency": "USD",
    "declared_value": null,
    "declared_value_basis": "total",
    "dq_factor": null
  }},
  "flags": {{
    "petroleum_case": false,
    "rubber_case": false,
    "fta_applicable": false,
    "fta_certificate_type": null,
    "dq_applicable": false,
    "qip_exemption": false,
    "sez_applicable": false
  }},
  "confidence": 0.95,
  "reasoning": "..."
}}

Example: if the user query contains "HS 27101229", the JSON must contain "hs_code": "2710.12.29".
"""


__all__ = ["IntentExtractor", "IntentResult"]
