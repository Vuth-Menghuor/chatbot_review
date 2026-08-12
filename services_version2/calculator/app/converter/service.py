"""
GDCE Calculator Service - Currency Converter Service
======================================================
Business-logic layer for the standalone currency converter.
Wraps CurrencyHandler and exchange-rate infrastructure.
Does NOT touch import-tax calculation core.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from ..services.currency_handler import CurrencyHandler, SUPPORTED_CURRENCIES
from ..data.redis_exchange_rate_client import RedisExchangeRateClient

logger = logging.getLogger(__name__)


class CurrencyConverterService:
    """
    Service for currency conversion operations.

    Responsibilities:
    - Convert amounts between any two supported currencies
    - Retrieve exchange rates (current or historical)
    - List supported currencies with metadata

    Dependencies:
    - CurrencyHandler (for rate lookup and normalization)
    - DatabaseInterface (via CurrencyHandler, for PostgreSQL fallback)
    """

    def __init__(self, db=None):
        """
        Initialize converter service.

        Args:
            db: Database interface for exchange rate fallback (optional).
        """
        redis_client = None
        import os
        if os.getenv("REDIS_HOST"):
            try:
                redis_client = RedisExchangeRateClient()
                logger.debug("Converter: Redis client initialized")
            except Exception as e:
                logger.warning(f"Converter: Redis unavailable: {e}")

        self.currency_handler = CurrencyHandler(db, redis_client=redis_client)

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    def convert(
        self,
        amount: float,
        from_currency_raw: str,
        to_currency_raw: str,
    ) -> Dict:
        """
        Convert an amount from one currency to another using the latest rate.

        Supports flexible currency input (codes, symbols, names) via
        CurrencyHandler.parse_currency_input.

        Args:
            amount: Amount to convert
            from_currency_raw: Source currency (any parseable format)
            to_currency_raw: Target currency (any parseable format)

        Returns:
            Dict with conversion result metadata

        Raises:
            ValueError: If currency unsupported or rate unavailable
        """
        from_code = self.currency_handler.parse_currency_input(from_currency_raw)
        to_code = self.currency_handler.parse_currency_input(to_currency_raw)

        if from_code == to_code:
            return {
                "amount": amount,
                "from_currency": from_code,
                "to_currency": to_code,
                "exchange_rate": 1.0,
                "converted_amount": amount,
                "note": f"Source and target currency are the same ({from_code}). No conversion performed.",
            }

        rate = self.currency_handler.get_exchange_rate(
            from_code,
            target_currency=to_code,
            calculation_date=None,
        )

        converted = Decimal(str(amount)) * rate
        # Apply ceiling-100 rounding when converting to KHR (Cambodian customs rule)
        if to_code == "KHR":
            from ..services import formulas
            converted = formulas.round_up_to_hundred(converted)

        rate_float = float(rate)
        converted_float = float(converted)

        note = (
            f"1 {from_code} = {rate_float:,.4f} {to_code}"
            if rate_float != 1.0
            else f"No conversion needed for {from_code}."
        )

        return {
            "amount": amount,
            "from_currency": from_code,
            "to_currency": to_code,
            "exchange_rate": rate_float,
            "converted_amount": converted_float,
            "note": note,
        }

    # ------------------------------------------------------------------
    # Natural-language conversion
    # ------------------------------------------------------------------

    def convert_natural(self, query: str) -> Dict:
        """
        Parse a free-form conversion query and convert using the latest rate.

        Handles patterns like:
        - "40000usd to khr"
        - "$500 to euro"
        - "1000 THB = KHR"
        - "convert 40000 USD to KHR"

        Args:
            query: Free-form conversion string

        Returns:
            Dict with parsed fields + conversion result

        Raises:
            ValueError: If query cannot be parsed
        """
        parsed_amount, from_cur, to_cur = self._parse_natural_query(query)

        result = self.convert(
            amount=parsed_amount,
            from_currency_raw=from_cur,
            to_currency_raw=to_cur,
        )
        result["query"] = query.strip()
        result["parsed_amount"] = parsed_amount
        result["parsed_from"] = from_cur
        result["parsed_to"] = to_cur
        return result

    def _parse_natural_query(self, query: str) -> Tuple[float, str, str]:
        """
        Extract amount and two currencies from a natural-language string.

        Strategy:
        1. Find the first numeric amount (handles commas/decimals).
        2. Remove the amount text from the query.
        3. Split remaining text by separators (to, =, ->, →, into).
        4. Try to parse each side as currency using CurrencyHandler.
        5. If separator split fails, scan tokens individually.
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty.")

        text = query.strip()

        # Step 1: Find the first amount (e.g., 40000, 1,000.50)
        amount_match = re.search(r"([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)", text)
        if not amount_match:
            raise ValueError(
                f"Could not find a numeric amount in '{query}'. "
                "Example: '40000 USD to KHR'"
            )

        amount_str = amount_match.group(1).replace(",", "")
        try:
            amount = float(amount_str)
        except ValueError:
            raise ValueError(f"Could not parse amount '{amount_str}' from query.")

        # Step 2: Remove the matched amount from text
        before_amount = text[:amount_match.start()].strip()
        after_amount = text[amount_match.end():].strip()

        # Step 3: Try to find a separator in the remaining text
        separator_pattern = re.compile(r"\s+(?:to|into|=|->|→|in)\s+", re.IGNORECASE)
        combined = f"{before_amount} {after_amount}".strip()

        # Try split by separator
        parts = separator_pattern.split(combined)
        if len(parts) >= 2:
            left = parts[0].strip()
            right = parts[1].strip()

            # One side likely has the amount glued to currency
            left_candidates = self._extract_currency_candidates(left, amount_str)
            right_candidates = self._extract_currency_candidates(right, amount_str)

            # Try to get one currency from each side
            from_cur = self._try_parse_currency(left_candidates)
            to_cur = self._try_parse_currency(right_candidates)

            if from_cur and to_cur:
                return amount, from_cur, to_cur

        # Step 4: Fallback — scan entire query for any two parseable currencies
        all_candidates = self._extract_currency_candidates(text, amount_str)
        currencies_found = []
        for cand in all_candidates:
            parsed = self._try_parse_currency([cand])
            if parsed:
                currencies_found.append(parsed)

        if len(currencies_found) >= 2:
            return amount, currencies_found[0], currencies_found[1]

        raise ValueError(
            f"Could not parse currencies from '{query}'. "
            "Please use format: '<amount> <from_currency> to <to_currency>'"
        )

    def _extract_currency_candidates(self, text: str, amount_str: str) -> List[str]:
        """Return potential currency tokens from text, removing the amount."""
        # Remove the exact amount string (with and without commas)
        cleaned = text.replace(amount_str, " ")
        cleaned = cleaned.replace(amount_str.replace(",", ""), " ")
        # Normalize whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        # Split into tokens
        tokens = re.split(r"[\s/]+", cleaned)
        # Return non-empty tokens
        return [t for t in tokens if t]

    def _try_parse_currency(self, candidates: List[str]) -> Optional[str]:
        """Try to parse a currency from candidate tokens."""
        for cand in candidates:
            try:
                # Try the whole token
                return self.currency_handler.parse_currency_input(cand)
            except ValueError:
                # Try stripping punctuation
                stripped = re.sub(r"^[^\w$€£¥฿₫₩₭₱¢៛]+|[^\w$€£¥฿₫₩₭₱¢៛]+$", "", cand)
                if stripped and stripped != cand:
                    try:
                        return self.currency_handler.parse_currency_input(stripped)
                    except ValueError:
                        pass
        return None

    # ------------------------------------------------------------------
    # Supported currencies
    # ------------------------------------------------------------------

    def get_supported_currencies(self) -> List[Dict]:
        """
        Return metadata for all supported currencies.

        Returns:
            List of dicts with code, name, symbol, decimals
        """
        return [
            {
                "code": code,
                "name": info["name"],
                "symbol": info["symbol"],
                "decimals": info["decimals"],
            }
            for code, info in sorted(SUPPORTED_CURRENCIES.items())
        ]
