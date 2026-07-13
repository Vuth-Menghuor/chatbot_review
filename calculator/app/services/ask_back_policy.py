"""
GDCE Calculator Service — Ask-Back / Conflict Detector
========================================================
Lightweight policy engine that detects when a user's natural-language
query contains *both* an explicit HS code *and* a product description
that map to **different HS chapters**.

In that case the calculator cannot know which one the user intended, so
it returns a clarifying message and asks the user to rewrite the question.

Usage (inside the /query endpoint):
    detector = ConflictDetector(calculator)
    conflict = detector.check(intent_result)
    if conflict:
        return DirectQueryResponse(..., needs_clarification=True)

The detector is **stateless** — the user must send a brand-new complete
query after clarification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HSConflict:
    """Structured representation of a description-vs-HS mismatch."""

    provided_hs: str
    provided_hs_description: Optional[str]
    resolved_hs: str
    resolved_hs_description: Optional[str]
    provided_chapter: str
    resolved_chapter: str
    message: str


class ConflictDetector:
    """
    Detect conflicts between an explicit HS code and a product description.

    Rules
    -----
    1. Both hs_code and description must be present in the extracted intent.
    2. The description must be "real" (not auto-generated fallbacks like
       "General merchandise").
    3. Resolve the description to its natural HS code via semantic search.
    4. Compare chapters (first 2 digits of the 4-digit section code).
    5. If chapters differ → conflict → ask user to rewrite.
    """

    # Descriptions that are too generic to resolve meaningfully
    _GENERIC_DESCRIPTIONS: frozenset = frozenset({
        "general merchandise",
        "petroleum products",
        "rubber products",
        "goods",
        "product",
        "items",
        "",
    })

    def __init__(self, calculator):
        """
        Args:
            calculator: An ImportTaxCalculator instance (has hs_code_handler
                        and resolve_hs_from_description).
        """
        self.calculator = calculator

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self, intent_result) -> Optional[HSConflict]:
        """
        Check whether the extracted intent contains a description/HS mismatch.

        Args:
            intent_result: IntentResult (or any object with .goods dict).

        Returns:
            HSConflict if a mismatch is detected, otherwise None.
        """
        goods = getattr(intent_result, "goods", None) or {}
        hs_code = goods.get("hs_code")
        description = (goods.get("description") or "").strip()

        # --- 1. Need both fields ---
        if not hs_code or not description:
            return None

        # --- 2. Skip generic / auto-fallback descriptions ---
        if description.lower() in self._GENERIC_DESCRIPTIONS:
            return None

        # --- 3. Resolve description → natural HS code ---
        resolved_hs, resolved_source, _ = self.calculator.resolve_hs_from_description(
            description, top_k=1
        )
        if not resolved_hs:
            logger.debug(
                "ConflictDetector: could not resolve description '%s' — no conflict",
                description,
            )
            return None

        # --- 4. Compare chapters ---
        provided_chapter = self._extract_chapter(hs_code)
        resolved_chapter = self._extract_chapter(resolved_hs)

        if not provided_chapter or not resolved_chapter:
            return None

        if provided_chapter == resolved_chapter:
            logger.debug(
                "ConflictDetector: chapters match (%s) — no conflict",
                provided_chapter,
            )
            return None

        # --- 5. Build conflict with human-readable descriptions ---
        provided_desc = self._lookup_hs_description(hs_code)
        resolved_desc = self._lookup_hs_description(resolved_hs)

        message = self._build_message(
            description=description,
            provided_hs=hs_code,
            provided_desc=provided_desc,
            resolved_hs=resolved_hs,
            resolved_desc=resolved_desc,
        )

        logger.info(
            "ConflictDetector: CONFLICT detected — description '%s' → HS %s (ch %s), "
            "but user provided HS %s (ch %s)",
            description, resolved_hs, resolved_chapter, hs_code, provided_chapter,
        )

        return HSConflict(
            provided_hs=hs_code,
            provided_hs_description=provided_desc,
            resolved_hs=resolved_hs,
            resolved_hs_description=resolved_desc,
            provided_chapter=provided_chapter,
            resolved_chapter=resolved_chapter,
            message=message,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_chapter(hs_code: str) -> Optional[str]:
        """Extract the 2-digit chapter from an HS code (first 2 digits)."""
        clean = hs_code.replace(".", "")
        if len(clean) >= 2 and clean.isdigit():
            return clean[:2]
        return None

    def _lookup_hs_description(self, hs_code: str) -> Optional[str]:
        """Try to get the official description for an HS code from the DB."""
        try:
            info = self.calculator.hs_code_handler.get_code_info(hs_code)
            if info and info.get("description"):
                return info["description"]
        except Exception as e:
            logger.debug("Failed to lookup HS description for %s: %s", hs_code, e)
        return None

    @staticmethod
    def _build_message(
        description: str,
        provided_hs: str,
        provided_desc: Optional[str],
        resolved_hs: str,
        resolved_desc: Optional[str],
    ) -> str:
        """Build a user-friendly clarification message."""
        lines: List[str] = [
            "There seems to be a mismatch in your request.",
            "",
        ]

        # Description side
        if resolved_desc:
            lines.append(
                f"You described the product as '{description}', which typically matches "
                f"HS {resolved_hs} ({resolved_desc})."
            )
        else:
            lines.append(
                f"You described the product as '{description}', which typically matches "
                f"HS {resolved_hs}."
            )

        # Provided HS side
        if provided_desc:
            lines.append(
                f"But you also provided HS {provided_hs}, which is for {provided_desc}."
            )
        else:
            lines.append(
                f"But you also provided HS {provided_hs}."
            )

        lines.extend([
            "",
            "These are different product categories, so I cannot determine which one you want to calculate taxes for.",
            "",
            "Please rewrite your question with either:",
            "  1) the correct product description, or",
            "  2) the correct HS code.",
        ])

        return "\n".join(lines)


__all__ = ["ConflictDetector", "HSConflict"]
