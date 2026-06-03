"""
GDCE Calculator Service - CSV Database Adapter
===============================================
Infrastructure adapter: reads duty_rates.csv into memory and implements
the DatabaseInterface contract from core.calculator.

Enables calculations without PostgreSQL, perfect for:
- Development and testing
- Offline/air-gapped deployments
- Simple lookup operations

For production at scale, migrate to PostgreSQL with connection pooling.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..core.calculator import DatabaseInterface
from ..config import get_settings

logger = logging.getLogger(__name__)


class CSVDatabase(DatabaseInterface):
    """CSV-based database implementation for duty rates and exchange rates."""

    def __init__(self):
        """Initialize CSV database from config."""
        settings = get_settings()
        self.csv_path = settings.duty_rates_csv_path
        self.rates_cache: Dict[str, Dict[str, float]] = {}
        self.hs_code_cache: Dict[str, Dict[str, str]] = {}
        self._load_csv()
        if self.csv_path:
            logger.info(f"CSV Database initialized from {self.csv_path}")
        else:
            logger.info("CSV Database initialized (no CSV path configured — using empty cache)")

    def _load_csv(self) -> None:
        """Load duty rates from CSV file into memory."""
        try:
            if not self.csv_path:
                logger.debug("No CSV path configured (DUTY_RATES_CSV_PATH not set)")
                return

            if not self.csv_path.exists():
                logger.error(f"CSV file not found at: {self.csv_path}")
                logger.error(f"Current working directory: {Path.cwd()}")
                return

            logger.info(f"Loading CSV from: {self.csv_path}")
            loaded_count = 0
            error_count = 0

            with open(self.csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                for line_num, row in enumerate(reader, 1):
                    # Skip empty rows or rows with insufficient columns
                    if not row or len(row) < 7:
                        continue

                    hs_code = row[0].strip()
                    if not hs_code:
                        continue

                    description = row[1].strip() if len(row) > 1 else ""
                    unit = row[2].strip() if len(row) > 2 else "u"

                    try:
                        cd_rate = float(row[3] if row[3] else 0) / 100  # Convert % to decimal
                        st_rate = float(row[4] if row[4] else 0) / 100
                        vat_rate = float(row[5] if row[5] else 0) / 100
                        et_rate = float(row[6] if row[6] else 0) / 100
                    except (ValueError, IndexError) as e:
                        error_count += 1
                        logger.debug(f"Row {line_num} parse error: {e}")
                        continue

                    # Cache rates by HS code (for all countries)
                    if hs_code not in self.rates_cache:
                        self.rates_cache[hs_code] = {
                            "cd_rate": cd_rate,
                            "st_rate": st_rate,
                            "vat_rate": vat_rate,
                            "et_rate": et_rate,
                        }
                        loaded_count += 1

                    # Cache HS code info
                    if hs_code not in self.hs_code_cache:
                        self.hs_code_cache[hs_code] = {
                            "description": description,
                            "unit": unit,
                        }

            logger.info(
                f"CSV loaded successfully: {loaded_count} HS codes, {error_count} errors"
            )

            # Log sample codes for debugging
            sample_codes = list(self.rates_cache.keys())[:10]
            logger.debug(f"Sample HS codes loaded: {sample_codes}")

        except Exception as e:
            logger.error(f"Error loading CSV: {e}", exc_info=True)

    def connect(self) -> None:
        """No-op for CSV implementation."""
        pass

    def close(self) -> None:
        """No-op for CSV implementation."""
        pass

    def check_health(self) -> Dict[str, Any]:
        """Check if CSV is loaded and accessible."""
        return {
            "ok": len(self.rates_cache) > 0,
            "database": "CSV",
            "loaded_hs_codes": len(self.rates_cache),
        }

    def get_duty_rates(
        self, hs_code: str, origin_country: str, effective_date: str, agreement_code: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get duty rates from CSV by HS code."""
        # Try exact match first
        if hs_code in self.rates_cache:
            rates = self.rates_cache[hs_code]
            logger.debug(f"Found duty rates for HS code: {hs_code}")
            return {
                "cd_rate": rates["cd_rate"],
                "st_rate": rates["st_rate"],
                "vat_rate": rates["vat_rate"],
                "et_rate": rates["et_rate"],
                "preferential_agreement": None,
            }

        # Try normalized version (remove dots)
        hs_normalized = hs_code.replace(".", "")
        for cached_hs, rates in self.rates_cache.items():
            if cached_hs.replace(".", "") == hs_normalized:
                logger.debug(f"Found duty rates for HS code (normalized): {cached_hs}")
                return {
                    "cd_rate": rates["cd_rate"],
                    "st_rate": rates["st_rate"],
                    "vat_rate": rates["vat_rate"],
                    "et_rate": rates["et_rate"],
                    "preferential_agreement": None,
                }

        logger.warning(f"HS code not found in CSV: {hs_code}")
        return None

    def get_exchange_rate(
        self, currency_code: str, effective_date: str
    ) -> Optional[float]:
        """Get exchange rate to KHR (hardcoded for common currencies)."""
        currency_code = (currency_code or "").upper()

        # Default exchange rates to KHR
        rates = {
            "KHR": 1.0,
            "EUR": 4400.0,
            "THB": 115.0,
            "VND": 0.158,
            "CNY": 560.0,
            "JPY": 27.5,
            "KRW": 3.1,
        }

        return rates.get(currency_code)

    def get_hs_code_info(self, hs_code: str) -> Optional[Dict[str, Any]]:
        """Get HS code description and unit from CSV."""
        # Try exact match
        if hs_code in self.hs_code_cache:
            return self.hs_code_cache[hs_code]

        # Try normalized version
        hs_normalized = hs_code.replace(".", "")
        for cached_hs, info in self.hs_code_cache.items():
            if cached_hs.replace(".", "") == hs_normalized:
                return info

        return None

    def search_by_description(self, query: str) -> Optional[Tuple[str, float]]:
        """
        Simple fallback search through CSV descriptions.
        Returns (hs_code, confidence_score) for best match or None.
        """
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        best_match = None
        best_score = 0

        for hs_code, info in self.hs_code_cache.items():
            desc = info.get("description", "").lower()
            if not desc:
                continue

            # Simple scoring: count matching tokens
            desc_tokens = set(desc.split())
            matching_tokens = len(query_tokens & desc_tokens)

            if matching_tokens > 0:
                # Score: percentage of query tokens found in description
                score = (
                    matching_tokens / len(query_tokens) if query_tokens else 0
                )

                if score > best_score:
                    best_score = score
                    best_match = (hs_code, score)

        if best_match:
            logger.debug(
                f"CSV description search found: {best_match[0]} (score: {best_match[1]:.2f})"
            )
            return best_match

        logger.debug(f"CSV description search found no matches for: {query}")
        return None

    def get_hs_code_candidates(
        self, query: str, limit: int = 5, fuzzy: bool = True
    ) -> list[Dict[str, Any]]:
        """
        Get candidate HS codes matching a query (description or code snippet).
        
        Used for fallback scenarios where HS code is not provided.
        Searches descriptions for keyword matches and returns top candidates.
        
        Args:
            query: Search query (description or partial HS code)
            limit: Maximum number of candidates to return
            fuzzy: Enable fuzzy matching (currently uses basic token matching)
            
        Returns:
            List of dicts with keys: hs_code, description, score
            Sorted by score (highest first)
        """
        if not query or not isinstance(query, str):
            return []
        
        query_lower = query.lower().strip()
        if len(query_lower) < 2:
            return []
        
        query_tokens = set(query_lower.split())
        candidates = []

        for hs_code, info in self.hs_code_cache.items():
            desc = info.get("description", "").lower()
            if not desc:
                continue

            # Skip if no matching tokens
            desc_tokens = set(desc.split())
            matching_tokens = query_tokens & desc_tokens
            if not matching_tokens:
                continue

            # Calculate score based on matching tokens
            score = len(matching_tokens) / len(query_tokens) if query_tokens else 0

            candidates.append({
                "hs_code": hs_code,
                "description": info.get("description", ""),
                "score": float(score),
            })

        # Sort by score (highest first) and limit results
        candidates.sort(key=lambda x: x["score"], reverse=True)
        result = candidates[:limit]

        if result:
            logger.debug(
                f"Found {len(result)} HS code candidates for query '{query}' "
                f"(top score: {result[0]['score']:.2f})"
            )
        else:
            logger.debug(f"No HS code candidates found for query: '{query}'")

        return result

    def search_hs_codes(self, query: str, limit: int = 5) -> list[Dict[str, Any]]:
        """
        Search HS codes by query string.
        Alias for get_hs_code_candidates for backward compatibility.
        """
        return self.get_hs_code_candidates(query, limit=limit)

    def save_calculation(self, calculation_result: Any) -> None:
        """No-op for CSV implementation (audit logging not needed)."""
        pass
