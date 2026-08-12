"""
GDCE Calculator Service - Unified Database Adapter (Standalone)
================================================================
Data access layer for the standalone calculator.

Primary source:
    Calculator PostgreSQL (gdce_calculator) — own DB, full ACID, source of truth

No fallback chain: if the calculator DB is down, requests fail fast.

Qdrant remains available ONLY for semantic search endpoints:
    - search_hs_by_description(query)
    - get_hs_candidates(query)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from decimal import Decimal
from datetime import datetime

from .calculator_db import CalculatorDatabaseAdapter
from .qdrant_client import QdrantClientAdapter
from .exchange_rate_adapter import PostgreSQLExchangeRateAdapter
from ..services.calculator import DatabaseInterface

logger = logging.getLogger(__name__)


# Mapping from common country names to ISO alpha-2 codes
_COUNTRY_NAME_TO_CODE: Dict[str, str] = {
    "CHINA": "CN", "THAILAND": "TH", "VIETNAM": "VN", "MALAYSIA": "MY",
    "SINGAPORE": "SG", "INDONESIA": "ID", "PHILIPPINES": "PH", "BRUNEI": "BN",
    "MYANMAR": "MM", "LAOS": "LA", "CAMBODIA": "KH", "KOREA": "KR",
    "SOUTH KOREA": "KR", "JAPAN": "JP", "AUSTRALIA": "AU", "NEW ZEALAND": "NZ",
    "INDIA": "IN", "UNITED STATES": "US", "USA": "US", "UNITED KINGDOM": "GB",
    "UK": "GB", "GERMANY": "DE", "FRANCE": "FR", "ITALY": "IT", "SPAIN": "ES",
    "NETHERLANDS": "NL", "BELGIUM": "BE", "SWITZERLAND": "CH", "RUSSIA": "RU",
    "CANADA": "CA", "MEXICO": "MX", "BRAZIL": "BR", "ARGENTINA": "AR",
    "SOUTH AFRICA": "ZA", "TURKEY": "TR", "PAKISTAN": "PK", "BANGLADESH": "BD",
    "SRI LANKA": "LK", "NEPAL": "NP", "BHUTAN": "BT", "MALDIVES": "MV",
    "AFGHANISTAN": "AF", "IRAN": "IR", "IRAQ": "IQ", "SYRIA": "SY",
    "LEBANON": "LB", "ISRAEL": "IL", "JORDAN": "JO", "SAUDI ARABIA": "SA",
    "UAE": "AE", "UNITED ARAB EMIRATES": "AE", "QATAR": "QA", "KUWAIT": "KW",
    "BAHRAIN": "BH", "OMAN": "OM", "YEMEN": "YE", "EGYPT": "EG",
    "LIBYA": "LY", "TUNISIA": "TN", "ALGERIA": "DZ", "MOROCCO": "MA",
    "SUDAN": "SD", "ETHIOPIA": "ET", "KENYA": "KE", "TANZANIA": "TZ",
    "UGANDA": "UG", "RWANDA": "RW", "BURUNDI": "BI", "CONGO": "CG",
    "DEMOCRATIC REPUBLIC OF THE CONGO": "CD", "DRC": "CD", "ZAMBIA": "ZM",
    "ZIMBABWE": "ZW", "BOTSWANA": "BW", "NAMIBIA": "NA", "ANGOLA": "AO",
    "MOZAMBIQUE": "MZ", "MADAGASCAR": "MG", "MAURITIUS": "MU",
    "SEYCHELLES": "SC", "NIGERIA": "NG", "GHANA": "GH", "IVORY COAST": "CI",
    "SENEGAL": "SN", "MALI": "ML", "BURKINA FASO": "BF", "NIGER": "NE",
    "CHAD": "TD", "CENTRAL AFRICAN REPUBLIC": "CF", "CAMEROON": "CM",
    "GABON": "GA", "EQUATORIAL GUINEA": "GQ", "SAO TOME AND PRINCIPE": "ST",
    "CAPE VERDE": "CV", "GAMBIA": "GM", "GUINEA": "GN", "GUINEA BISSAU": "GW",
    "SIERRA LEONE": "SL", "LIBERIA": "LR", "TOGO": "TG", "BENIN": "BJ",
    "MAURITANIA": "MR", "WESTERN SAHARA": "EH", "SOMALIA": "SO",
    "DJIBOUTI": "DJ", "ERITREA": "ER", "TAIWAN": "TW", "HONG KONG": "HK",
    "MACAU": "MO", "MONGOLIA": "MN", "KAZAKHSTAN": "KZ", "UZBEKISTAN": "UZ",
    "TURKMENISTAN": "TM", "TAJIKISTAN": "TJ", "KYRGYZSTAN": "KG",
    "GEORGIA": "GE", "ARMENIA": "AM", "AZERBAIJAN": "AZ", "UKRAINE": "UA",
    "BELARUS": "BY", "MOLDOVA": "MD", "ESTONIA": "EE", "LATVIA": "LV",
    "LITHUANIA": "LT", "POLAND": "PL", "CZECH REPUBLIC": "CZ",
    "CZECHIA": "CZ", "SLOVAKIA": "SK", "HUNGARY": "HU", "ROMANIA": "RO",
    "BULGARIA": "BG", "CROATIA": "HR", "SLOVENIA": "SI", "SERBIA": "RS",
    "MONTENEGRO": "ME", "NORTH MACEDONIA": "MK", "MACEDONIA": "MK",
    "ALBANIA": "AL", "BOSNIA AND HERZEGOVINA": "BA", "KOSOVO": "XK",
    "GREECE": "GR", "CYPRUS": "CY", "MALTA": "MT", "ICELAND": "IS",
    "NORWAY": "NO", "SWEDEN": "SE", "FINLAND": "FI", "DENMARK": "DK",
    "IRELAND": "IE", "PORTUGAL": "PT", "LUXEMBOURG": "LU", "MONACO": "MC",
    "ANDORRA": "AD", "LIECHTENSTEIN": "LI", "SAN MARINO": "SM",
    "VATICAN": "VA", "CHILE": "CL", "PERU": "PE", "ECUADOR": "EC",
    "COLOMBIA": "CO", "VENEZUELA": "VE", "BOLIVIA": "BO", "PARAGUAY": "PY",
    "URUGUAY": "UY", "GUYANA": "GY", "SURINAME": "SR", "FRENCH GUIANA": "GF",
    "PANAMA": "PA", "COSTA RICA": "CR", "NICARAGUA": "NI", "HONDURAS": "HN",
    "EL SALVADOR": "SV", "GUATEMALA": "GT", "BELIZE": "BZ", "CUBA": "CU",
    "JAMAICA": "JM", "HAITI": "HT", "DOMINICAN REPUBLIC": "DO",
    "TRINIDAD AND TOBAGO": "TT", "BARBADOS": "BB", "SAINT LUCIA": "LC",
    "GRENADA": "GD", "SAINT VINCENT AND THE GRENADINES": "VC",
    "ANTIGUA AND BARBUDA": "AG", "DOMINICA": "DM",
    "SAINT KITTS AND NEVIS": "KN", "BAHAMAS": "BS", "FIJI": "FJ",
    "PAPUA NEW GUINEA": "PG", "SOLOMON ISLANDS": "SB", "VANUATU": "VU",
    "SAMOA": "WS", "TONGA": "TO", "KIRIBATI": "KI", "TUVALU": "TV",
    "NAURU": "NR", "PALAU": "PW", "MARSHALL ISLANDS": "MH",
    "MICRONESIA": "FM", "GUAM": "GU", "AMERICAN SAMOA": "AS",
    "COOK ISLANDS": "CK", "NIUE": "NU", "TOKELAU": "TK", "PITCAIRN": "PN",
    "WALLIS AND FUTUNA": "WF", "FRENCH POLYNESIA": "PF",
    "NEW CALEDONIA": "NC", "TIMOR LESTE": "TL", "EAST TIMOR": "TL",
}


class UnifiedDatabase(DatabaseInterface):
    """
    Unified database adapter — calculator PostgreSQL only.

    No fallback chain: if the calculator DB is down, requests fail.
    Qdrant is kept only for semantic search endpoints.
    """

    def __init__(
        self,
        enable_calculator_db: bool = True,
        enable_qdrant: bool = True,
        enable_postgres: bool = False,
        enable_csv: bool = False,
        legacy_mode: bool = False,
    ):
        self.legacy_mode = legacy_mode
        if self.legacy_mode:
            logger.info(" LEGACY MODE enabled: shared PG is PRIMARY, calculator DB is fallback")

        self.calculator_db: Optional[CalculatorDatabaseAdapter] = None
        self.qdrant: Optional[QdrantClientAdapter] = None
        self.postgres: Optional[PostgreSQLExchangeRateAdapter] = None
        self.rules_db = None

        # 1. Calculator DB — PRIMARY source of truth (standalone)
        if enable_calculator_db:
            try:
                self.calculator_db = CalculatorDatabaseAdapter()
                logger.info(" CalculatorDB adapter initialized (%s)",
                            "FALLBACK" if self.legacy_mode else "PRIMARY")
            except Exception as e:
                logger.warning(f"  CalculatorDB unavailable: {e}")
                self.calculator_db = None

        # 2. Qdrant — OPTIONAL (semantic search only)
        if enable_qdrant:
            try:
                self.qdrant = QdrantClientAdapter()
                logger.info(" Qdrant adapter initialized (semantic search only)")
            except Exception as e:
                logger.warning(f"  Qdrant unavailable: {e}")
                self.qdrant = None

        # 3. Legacy shared PostgreSQL — PRIMARY in legacy mode only
        if enable_postgres:
            try:
                self.postgres = PostgreSQLExchangeRateAdapter()
                logger.info(" Shared PostgreSQL adapter initialized (%s)",
                            "PRIMARY" if self.legacy_mode else "legacy fallback")
            except Exception as e:
                logger.warning(f"  Shared PostgreSQL unavailable: {e}")
                self.postgres = None

        # 4. Rules DB (calculator DB formulas)
        try:
            from .rules_database import RulesDatabaseAdapter
            self.rules_db = RulesDatabaseAdapter()
            logger.info(" Rules DB adapter initialized")
        except Exception as e:
            logger.warning(f"  Rules DB unavailable: {e}")
            self.rules_db = None

        if not self.calculator_db:
            logger.error(" CalculatorDB is not available — calculations will fail")

    @staticmethod
    def _normalize_origin_country(origin: str) -> str:
        """Normalize country name or code to ISO alpha-2."""
        if not origin:
            return ""
        origin_upper = origin.strip().upper()
        if len(origin_upper) == 2 and origin_upper.isalpha():
            return origin_upper
        return _COUNTRY_NAME_TO_CODE.get(origin_upper, origin_upper)

    # =====================================================================
    # Duty rates — Calculator DB only (no fallback)
    # =====================================================================

    def _get_duty_rates_from_shared_pg(
        self,
        hs_code: str,
        origin_country: str = "XX",
        effective_date: str = None,
    ) -> Optional[Dict[str, Any]]:
        """Query duty rates from shared PostgreSQL (legacy fallback only)."""
        if not self.postgres or not self.postgres.conn:
            return None
        if not effective_date:
            effective_date = datetime.now().strftime("%Y-%m-%d")

        try:
            import psycopg2.extras
            cursor = self.postgres.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            # 1. MFN duty rate
            cursor.execute(
                """
                SELECT hs_code, cd_rate, st_rate, vat_rate, et_rate, atp_rate,
                       effective_date, source
                FROM duty_rates
                WHERE hs_code = %s
                  AND effective_date <= %s
                  AND (expires_date IS NULL OR expires_date > %s)
                ORDER BY effective_date DESC
                LIMIT 1
                """,
                (hs_code, effective_date, effective_date),
            )
            row = cursor.fetchone()
            if not row:
                cursor.close()
                return None

            rates = dict(row)

            # NOTE: preferential_rates table is disabled for now.
            # Preferential rates are provided by the user via preferential_cd_rate
            # or auto-applied for known zero-rate agreements in calculator.py.
            # The preferential_rates DB table is reserved for future use.

            cursor.close()

            return {
                "hs_code": rates["hs_code"],
                "cd_rate": float(Decimal(str(rates["cd_rate"])) / Decimal("100")) if rates["cd_rate"] is not None else 0.0,
                "st_rate": float(Decimal(str(rates["st_rate"])) / Decimal("100")) if rates["st_rate"] is not None else 0.0,
                "vat_rate": float(Decimal(str(rates["vat_rate"])) / Decimal("100")) if rates["vat_rate"] is not None else 0.1,
                "et_rate": float(Decimal(str(rates["et_rate"])) / Decimal("100")) if rates["et_rate"] is not None else 0.0,
                "atp_rate": float(rates["atp_rate"]) if rates.get("atp_rate") is not None else 0.0,
                "origin_country": origin_country,
                "description": "",
                "unit": "",
                "source": rates.get("source", "shared_pg"),
            }
        except Exception as e:
            logger.warning(f"Shared PG duty-rate query failed for {hs_code}: {e}")
            return None

    def get_duty_rates(
        self,
        hs_code: str,
        origin_country: str = "XX",
        effective_date: str = None,
    ) -> Optional[Dict[str, Any]]:
        rates = None

        if self.legacy_mode:
            # LEGACY priority: Shared PG → Qdrant → Calculator DB
            # 1. Shared PostgreSQL (legacy)
            if rates is None and self.postgres:
                try:
                    rates = self._get_duty_rates_from_shared_pg(hs_code, origin_country, effective_date)
                    if rates:
                        logger.info(f"Duty rates for {hs_code} from SHARED PG (legacy mode): CD={rates['cd_rate']}, ST={rates['st_rate']}, VAT={rates['vat_rate']}")
                except Exception as e:
                    logger.warning(f"Shared PG duty-rate query failed for {hs_code}: {e}")

            # 2. Qdrant
            if rates is None and self.qdrant:
                try:
                    rates = self.qdrant.get_duty_rates(hs_code)
                    if rates:
                        rates["origin_country"] = origin_country
                        logger.info(f"Duty rates for {hs_code} from Qdrant (legacy mode)")
                except Exception as e:
                    logger.warning(f"Qdrant duty-rate query failed for {hs_code}: {e}")

        # 3. Calculator DB (standalone primary)
        if rates is None and self.calculator_db:
            try:
                rates = self.calculator_db.get_duty_rates(hs_code, origin_country, effective_date)
                if rates:
                    logger.debug(f"Duty rates for {hs_code} from CalculatorDB")
            except Exception as e:
                logger.warning(f"CalculatorDB duty-rate query failed for {hs_code}: {e}")

        if rates is None:
            logger.warning(f"No duty rates found for HS code {hs_code}")
            return None

        return rates

    # =====================================================================
    # HS code info — Calculator DB only (no fallback)
    # =====================================================================

    def _get_hs_code_info_from_shared_pg(self, hs_code: str) -> Optional[Dict[str, Any]]:
        """Query HS info from shared PostgreSQL (legacy fallback only)."""
        if not self.postgres or not self.postgres.conn:
            return None
        try:
            import psycopg2.extras
            cursor = self.postgres.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(
                "SELECT code, description, unit FROM hs_codes WHERE code = %s LIMIT 1",
                (hs_code,),
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return {
                    "hs_code": row["code"],
                    "description": row["description"],
                    "unit": row["unit"],
                    "source": "shared_pg",
                }
        except Exception as e:
            logger.warning(f"Shared PG HS-info query failed for {hs_code}: {e}")
        return None

    def get_hs_code_info(self, hs_code: str) -> Optional[Dict[str, Any]]:
        if self.legacy_mode:
            # LEGACY priority: Qdrant → Shared PG → Calculator DB
            if self.qdrant:
                try:
                    info = self.qdrant.get_hs_code_info(hs_code)
                    if info:
                        logger.debug(f"HS info for {hs_code} from Qdrant (legacy)")
                        return info
                except Exception as e:
                    logger.warning(f"Qdrant HS-info query failed for {hs_code}: {e}")

            if self.postgres:
                try:
                    info = self._get_hs_code_info_from_shared_pg(hs_code)
                    if info:
                        logger.debug(f"HS info for {hs_code} from Shared PG (legacy)")
                        return info
                except Exception as e:
                    logger.warning(f"Shared PG HS-info query failed for {hs_code}: {e}")

        # Calculator DB (standalone primary)
        if self.calculator_db:
            try:
                info = self.calculator_db.get_hs_code_info(hs_code)
                if info:
                    logger.debug(f"HS info for {hs_code} from CalculatorDB")
                    return info
            except Exception as e:
                logger.warning(f"CalculatorDB HS-info query failed for {hs_code}: {e}")

        logger.warning(f"No HS code info found for {hs_code}")
        return None

    # =====================================================================
    # Exchange rate — Calculator DB only (no fallback)
    # =====================================================================

    # Mapping from ISO currency codes to names used in exchange_rates
    _CURRENCY_NAME_MAP: Dict[str, str] = {
        "USD": "US Dollar",
        "EUR": "Euro",
        "THB": "Thailand",
        "CNY": "China",
        "JPY": "Japan",
        "KRW": "South Korea",
        "VND": "Vietnam",
        "MYR": "Malaysia",
        "SGD": "Singapore",
        "GBP": "England",
        "AUD": "Australia",
        "CAD": "Canada",
        "HKD": "Hong Kong",
        "INR": "India",
    }

    def _get_exchange_rate_from_shared_pg(
        self, currency_code: str, effective_date: str
    ) -> Optional[Decimal]:
        """Query exchange rate from shared PostgreSQL, handling currency name aliases."""
        if not self.postgres or not self.postgres.conn:
            return None
        # Try direct code first (e.g. USD), then mapped name (e.g. US Dollar)
        candidates = [currency_code]
        mapped = self._CURRENCY_NAME_MAP.get(currency_code.upper())
        if mapped and mapped not in candidates:
            candidates.append(mapped)

        try:
            import psycopg2.extras
            cursor = self.postgres.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            for cand in candidates:
                cursor.execute(
                    """
                    SELECT local_rate
                    FROM exchange_rates
                    WHERE currency = %s
                      AND effective_date <= %s
                    ORDER BY effective_date DESC
                    LIMIT 1
                    """,
                    (cand, effective_date),
                )
                row = cursor.fetchone()
                if row and row.get("local_rate") is not None:
                    cursor.close()
                    rate = Decimal(str(row["local_rate"]))
                    logger.info(f"Exchange rate {currency_code}->KHR from SHARED PG (legacy): {rate} (matched '{cand}')")
                    return rate
            cursor.close()
        except Exception as e:
            logger.warning(f"Shared PG exchange-rate query failed for {currency_code}: {e}")
        return None

    def get_exchange_rate(
        self,
        currency_code: str,
        effective_date: str = None,
    ) -> Optional[Decimal]:
        if not effective_date:
            effective_date = datetime.now().strftime("%Y-%m-%d")

        if self.legacy_mode:
            # LEGACY priority: Shared PG → Calculator DB
            if self.postgres:
                try:
                    rate = self._get_exchange_rate_from_shared_pg(currency_code, effective_date)
                    if rate:
                        return rate
                except Exception as e:
                    logger.warning(f"Shared PostgreSQL exchange-rate query failed for {currency_code}: {e}")

            if self.calculator_db:
                try:
                    rate = self.calculator_db.get_exchange_rate(currency_code, effective_date)
                    if rate:
                        logger.debug(f"Exchange rate {currency_code}->KHR from CalculatorDB: {rate}")
                        return rate
                except Exception as e:
                    logger.warning(f"CalculatorDB exchange-rate query failed for {currency_code}: {e}")
        else:
            # STANDALONE priority: Calculator DB only
            if self.calculator_db:
                try:
                    rate = self.calculator_db.get_exchange_rate(currency_code, effective_date)
                    if rate:
                        logger.debug(f"Exchange rate {currency_code}->KHR from CalculatorDB: {rate}")
                        return rate
                except Exception as e:
                    logger.warning(f"CalculatorDB exchange-rate query failed for {currency_code}: {e}")

        logger.warning(f"No exchange rate found for {currency_code}")
        return None

    # =====================================================================
    # Deduction value (DV) —
    #   Standalone: Calculator DB → Shared PG
    #   Legacy:     Shared PG → Calculator DB
    # =====================================================================

    def get_declared_value(
        self,
        hs_code: str,
        effective_date: str = None,
    ) -> Optional[Dict[str, Any]]:
        if not effective_date:
            effective_date = datetime.now().strftime("%Y-%m-%d")

        if self.legacy_mode:
            # LEGACY priority: Shared PG → Calculator DB
            if self.postgres and self.postgres.conn:
                try:
                    cursor = self.postgres.conn.cursor()
                    cursor.execute(
                        """
                        SELECT dv_per_metric_ton, currency, source
                        FROM declared_values
                        WHERE hs_code = %s
                          AND is_active = TRUE
                          AND effective_date <= %s
                        ORDER BY effective_date DESC
                        LIMIT 1
                        """,
                        (hs_code, effective_date),
                    )
                    row = cursor.fetchone()
                    cursor.close()
                    if row:
                        logger.info(f"Deduction value (DV) for {hs_code} from SHARED PG (legacy)")
                        return {
                            "dv_per_metric_ton": Decimal(str(row[0])),
                            "currency": row[1] or "USD",
                            "source": row[2] or "government",
                        }
                except Exception as e:
                    logger.warning(f"Shared PostgreSQL deduction-value (DV) query failed for {hs_code}: {e}")

            if self.calculator_db:
                try:
                    dv = self.calculator_db.get_declared_value(hs_code, effective_date)
                    if dv:
                        return dv
                except Exception as e:
                    logger.warning(f"CalculatorDB deduction-value (DV) query failed for {hs_code}: {e}")
        else:
            # STANDALONE priority: Calculator DB → Shared PG
            if self.calculator_db:
                try:
                    dv = self.calculator_db.get_declared_value(hs_code, effective_date)
                    if dv:
                        return dv
                except Exception as e:
                    logger.warning(f"CalculatorDB deduction-value (DV) query failed for {hs_code}: {e}")

            if self.postgres and self.postgres.conn:
                try:
                    cursor = self.postgres.conn.cursor()
                    cursor.execute(
                        """
                        SELECT dv_per_metric_ton, currency, source
                        FROM declared_values
                        WHERE hs_code = %s
                          AND is_active = TRUE
                          AND effective_date <= %s
                        ORDER BY effective_date DESC
                        LIMIT 1
                        """,
                        (hs_code, effective_date),
                    )
                    row = cursor.fetchone()
                    cursor.close()
                    if row:
                        return {
                            "dv_per_metric_ton": Decimal(str(row[0])),
                            "currency": row[1] or "USD",
                            "source": row[2] or "government",
                        }
                except Exception as e:
                    logger.warning(f"Shared PostgreSQL deduction-value (DV) query failed for {hs_code}: {e}")

        return None

    # =====================================================================
    # Calculation persistence
    # =====================================================================

    def save_calculation(self, calculation_result: Any) -> None:
        """Save calculation result for audit trail."""
        if self.calculator_db:
            try:
                self.calculator_db.save_calculation(calculation_result)
                return
            except Exception as e:
                logger.warning(f"CalculatorDB save_calculation failed: {e}")
        logger.info(f"Calculation saved (no DB): {getattr(calculation_result, 'calculation_id', 'unknown')}")

    # =====================================================================
    # Semantic search (Qdrant only — NOT used in calculation path)
    # =====================================================================

    def search_by_description(self, query: str) -> Optional[tuple[str, float]]:
        """
        Semantic HS search via Qdrant, with Calculator DB fallback.
        Returns (hs_code, confidence) or None.
        """
        if self.qdrant:
            try:
                result = self.qdrant.search_by_description(query)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Qdrant search_by_description failed: {e}")

        # Fallback: DB description search
        if self.calculator_db:
            try:
                db_results = self.calculator_db.search_hs_by_description(query, limit=1)
                if db_results:
                    top = db_results[0]
                    return (top["hs_code"], 0.7)
            except Exception as e:
                logger.debug(f"DB search_by_description fallback failed: {e}")

        return None

    def search_hs_by_description(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantic HS search via Qdrant, with Calculator DB fallback."""
        if self.qdrant:
            try:
                return self.qdrant.search_by_description(query, top_k)
            except Exception as e:
                logger.warning(f"Qdrant semantic search failed: {e}")

        # Fallback: DB description search
        if self.calculator_db:
            try:
                db_results = self.calculator_db.search_hs_by_description(query, limit=top_k)
                if db_results:
                    return [
                        {"hs_code": r["hs_code"], "description": r["description"], "score": 0.7, "source": "calculator_db"}
                        for r in db_results
                    ]
            except Exception as e:
                logger.debug(f"DB search_hs_by_description fallback failed: {e}")

        return []

    def get_hs_candidates(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get HS code candidates via Qdrant."""
        if not self.qdrant:
            logger.warning("Qdrant not available for candidate search")
            return []
        try:
            return self.qdrant.get_candidates(query, limit)
        except Exception as e:
            logger.warning(f"Qdrant candidate search failed: {e}")
            return []

    # =====================================================================
    # Prefix search (Qdrant + Calculator DB)
    # =====================================================================

    def get_hs_codes_by_prefix(self, prefix: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get HS codes starting with prefix from Calculator DB."""
        if self.calculator_db:
            try:
                return self.calculator_db.get_hs_codes_by_prefix(prefix, limit)
            except Exception as e:
                logger.warning(f"CalculatorDB prefix search failed: {e}")
        return []

    def search_hs_by_prefix_and_description(
        self,
        prefix: str,
        description: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search by description, filtered to HS codes starting with prefix.
        Delegates to Qdrant first, falls back to DB prefix + basic matching.
        """
        # 1. Qdrant semantic search with prefix filter
        if self.qdrant:
            try:
                candidates = self.qdrant.search_by_prefix_and_description(
                    prefix, description, top_k
                )
                if candidates:
                    return candidates
            except Exception as e:
                logger.warning(f"Qdrant prefix+description search failed: {e}")

        # 2. Fallback: DB prefix lookup + basic description matching
        if self.calculator_db:
            try:
                db_results = self.calculator_db.get_hs_codes_by_prefix(prefix, limit=top_k * 3)
                if db_results:
                    # Simple keyword overlap scoring
                    desc_words = set(description.lower().split())
                    scored = []
                    for r in db_results:
                        r_desc = (r.get("description") or "").lower()
                        r_words = set(r_desc.split())
                        overlap = len(desc_words & r_words)
                        scored.append({
                            **r,
                            "score": overlap / max(len(desc_words), 1),
                            "source": "db_prefix",
                        })
                    scored.sort(key=lambda x: x["score"], reverse=True)
                    return scored[:top_k]
            except Exception as e:
                logger.warning(f"DB prefix+description fallback failed: {e}")

        return []

    # =====================================================================
    # Health check
    # =====================================================================

    def check_health(self) -> Dict[str, Any]:
        calc_health = self.calculator_db.check_health() if self.calculator_db else {"ok": False, "message": "Not initialized"}
        qdrant_health = self.qdrant.check_health() if self.qdrant else {"ok": False, "message": "Not initialized (semantic search only)"}
        postgres_health = self.postgres.check_health() if self.postgres else {"ok": False, "message": "Not initialized (legacy fallback)"}

        # Top-level ok = True if primary source (calculator_db) is healthy
        primary_ok = calc_health.get("ok", False)
        return {
            "ok": primary_ok,
            "calculator_db": calc_health,
            "qdrant": qdrant_health,
            "shared_postgresql": postgres_health,
        }
