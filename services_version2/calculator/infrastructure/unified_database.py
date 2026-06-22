"""
GDCE Calculator Service - Unified Database Adapter (Standalone)
================================================================
Hierarchical data access layer for the standalone calculator.

Priority (inverted for standalone independence):
1. Calculator PostgreSQL  (PRIMARY) — own DB, full ACID, source of truth
2. CSV                    (OFFLINE) — degraded mode
3. Hardcoded petroleum    (ULTIMATE) — always works for known HS codes

Qdrant is REMOVED from the duty-rate and HS-info lookup chain.
It remains available ONLY for semantic search endpoints:
    - search_hs_by_description(query)
    - get_hs_candidates(query)

The calculator's own PostgreSQL (gdce_calculator) is the sole source
of truth for all data. Legacy fallback connections are removed.
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
from .csv_database import CSVDatabase
from ..core.calculator import DatabaseInterface

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hardcoded petroleum duty rates (untartab_202605120954.xlsx)
# These are the CURRENT valid rates (valid_from 2023-07-01, no end date).
# Format: cd_rate, st_rate, vat_rate are decimals (0.15 = 15%).
# ---------------------------------------------------------------------------
# Updated 2026-06-17 per official tariff screenshot (HS 2710.12.xx)
# CD=0%, ST=30%, VAT=10%, ATP=0.02$/L
_PETROLEUM_RATES_DEFAULT: Dict[str, Dict[str, float]] = {
    "2710.12.11": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.12": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.13": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.21": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.22": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.23": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.24": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.25": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.26": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.27": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.28": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.29": {"cd": 0.00, "st": 0.30, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.19.71": {"cd": 0.00, "st": 0.04, "vat": 0.10, "et": 0.0, "atp": 0.04},
    "2710.19.72": {"cd": 0.00, "st": 0.04, "vat": 0.10, "et": 0.0, "atp": 0.04},
}

# ATP-only lookup derived from the table above
_ATP_RATES_DEFAULT: Dict[str, Decimal] = {
    k: Decimal(str(v["atp"])) for k, v in _PETROLEUM_RATES_DEFAULT.items()
}

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


def _find_atp_excel_path() -> Optional[Path]:
    """Find the latest untartab Excel file using glob patterns."""
    search_paths = [Path("."), Path(__file__).parent.parent.parent.parent]
    candidates: list[Path] = []
    for base in search_paths:
        if base.exists():
            candidates.extend(base.glob("untartab*.xlsx"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _load_atp_rates_from_excel(excel_path: Optional[Path] = None) -> tuple[Dict[str, Decimal], Optional[Path], float]:
    """
    TEMPORARY: Load ATP rates from untartab Excel file.
    Uses hardcoded defaults for instant startup.
    """
    atp_rates = dict(_ATP_RATES_DEFAULT)
    if excel_path is None:
        excel_path = _find_atp_excel_path()
    if not excel_path or not excel_path.exists():
        logger.info(f"Using {len(atp_rates)} hardcoded ATP rates (Excel not found)")
        return atp_rates, None, 0.0
    mtime = excel_path.stat().st_mtime
    logger.info(f"Using {len(atp_rates)} hardcoded ATP rates ({excel_path.name} present but not parsed)")
    return atp_rates, excel_path, mtime


class UnifiedDatabase(DatabaseInterface):
    """
    Unified database adapter with hierarchical fallback strategy.

    STANDALONE priority (new):
        1. Calculator PostgreSQL (gdce_calculator) — PRIMARY
        2. CSV fallback                          — OFFLINE
        3. Hardcoded petroleum                   — ULTIMATE

    Qdrant is kept only for semantic search endpoints.
    """

    def __init__(
        self,
        enable_calculator_db: bool = True,
        enable_qdrant: bool = True,
        enable_postgres: bool = True,
        enable_csv: bool = True,
        legacy_mode: bool = None,
    ):
        # Legacy mode: read from shared PG + Qdrant as PRIMARY,
        # calculator DB as fallback. Toggle via env var CALCULATOR_LEGACY_MODE.
        if legacy_mode is None:
            legacy_mode = os.getenv("CALCULATOR_LEGACY_MODE", "false").lower() in ("true", "1", "yes", "on")
        self.legacy_mode = legacy_mode
        if self.legacy_mode:
            logger.info(" LEGACY MODE enabled: shared PG is PRIMARY, calculator DB is fallback")

        self.calculator_db: Optional[CalculatorDatabaseAdapter] = None
        self.qdrant: Optional[QdrantClientAdapter] = None
        self.postgres: Optional[PostgreSQLExchangeRateAdapter] = None
        self.csv: Optional[CSVDatabase] = None
        self.rules_db = None

        # ATP hardcoded rates
        self._atp_rates: Dict[str, Decimal] = {}
        self._atp_excel_path: Optional[Path] = None
        self._atp_mtime: float = 0.0
        self._reload_atp_rates()

        # 1. Calculator DB — PRIMARY source of truth (standalone)
        if enable_calculator_db:
            try:
                self.calculator_db = CalculatorDatabaseAdapter()
                logger.info(" CalculatorDB adapter initialized (%s)",
                            "FALLBACK" if self.legacy_mode else "PRIMARY")
            except Exception as e:
                logger.warning(f"  CalculatorDB unavailable: {e}")
                self.calculator_db = None

        # 2. Qdrant — OPTIONAL (semantic search only in standalone; PRIMARY in legacy)
        if enable_qdrant:
            try:
                self.qdrant = QdrantClientAdapter()
                logger.info(" Qdrant adapter initialized (%s)",
                            "PRIMARY duty/HS lookup" if self.legacy_mode else "semantic search only")
            except Exception as e:
                logger.warning(f"  Qdrant unavailable: {e}")
                self.qdrant = None

        # 3. Legacy shared PostgreSQL — PRIMARY in legacy mode
        if enable_postgres:
            try:
                self.postgres = PostgreSQLExchangeRateAdapter()
                logger.info(" Shared PostgreSQL adapter initialized (%s)",
                            "PRIMARY" if self.legacy_mode else "legacy fallback")
            except Exception as e:
                logger.warning(f"  Shared PostgreSQL unavailable: {e}")
                self.postgres = None

        # 4. CSV fallback
        if enable_csv:
            try:
                self.csv = CSVDatabase()
                logger.info(" CSV fallback initialized")
            except Exception as e:
                logger.warning(f"  CSV fallback unavailable: {e}")
                self.csv = None

        # 5. Rules DB (calculator DB formulas)
        try:
            from .rules_database import RulesDatabaseAdapter
            self.rules_db = RulesDatabaseAdapter()
            logger.info(" Rules DB adapter initialized")
        except Exception as e:
            logger.warning(f"  Rules DB unavailable: {e}")
            self.rules_db = None

        # Verify at least one source is available
        if not (self.calculator_db or self.csv or (self.legacy_mode and self.qdrant)):
            logger.error(" No duty rate source available (need CalculatorDB, CSV, or Qdrant in legacy mode)")
        if not (self.calculator_db or self.postgres or self.csv):
            logger.error("  No exchange rate source available (need CalculatorDB, PostgreSQL, or CSV)")

    @staticmethod
    def _normalize_origin_country(origin: str) -> str:
        """Normalize country name or code to ISO alpha-2."""
        if not origin:
            return ""
        origin_upper = origin.strip().upper()
        if len(origin_upper) == 2 and origin_upper.isalpha():
            return origin_upper
        return _COUNTRY_NAME_TO_CODE.get(origin_upper, origin_upper)

    def _reload_atp_rates(self) -> None:
        """Reload ATP rates from Excel if the file has changed."""
        try:
            current_path = _find_atp_excel_path()
            if current_path is None:
                return
            mtime = current_path.stat().st_mtime
            if current_path == self._atp_excel_path and mtime == self._atp_mtime:
                return
            rates, path, new_mtime = _load_atp_rates_from_excel(current_path)
            self._atp_rates = rates
            self._atp_excel_path = path
            self._atp_mtime = new_mtime
        except Exception as e:
            logger.warning(f"ATP rate reload check failed: {e}")

    # =====================================================================
    # Duty rates —
    #   Standalone:  Calculator DB → CSV → hardcoded
    #   Legacy:      Shared PG → Qdrant → Calculator DB → CSV → hardcoded
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

            # 2. Preferential rate override (origin-specific)
            origin = self._normalize_origin_country(origin_country)
            if origin and origin != "XX":
                cursor.execute(
                    """
                    SELECT preferential_cd_rate, agreement_code
                    FROM preferential_rates
                    WHERE hs_code = %s
                      AND origin_country = %s
                      AND (end_date IS NULL OR end_date > %s)
                      AND effective_date <= %s
                    ORDER BY effective_date DESC
                    LIMIT 1
                    """,
                    (hs_code, origin, effective_date, effective_date),
                )
                pref = cursor.fetchone()
                if pref:
                    rates["cd_rate"] = pref["preferential_cd_rate"]
                    rates["agreement_code"] = pref["agreement_code"]
                    rates["source"] = f"shared_pg_preferential ({pref['agreement_code']})"

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
            # LEGACY priority: Shared PG → Qdrant → Calculator DB → CSV → hardcoded
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
        else:
            # STANDALONE priority: Calculator DB → CSV → hardcoded
            # 1. Calculator DB (PRIMARY)
            if self.calculator_db:
                try:
                    rates = self.calculator_db.get_duty_rates(hs_code, origin_country, effective_date)
                    if rates:
                        logger.debug(f"Duty rates for {hs_code} from CalculatorDB")
                except Exception as e:
                    logger.warning(f"CalculatorDB duty-rate query failed for {hs_code}: {e}")

        # 3. CSV fallback (both modes)
        if rates is None and self.csv:
            try:
                rates = self.csv.get_duty_rates(hs_code, origin_country, effective_date)
                if rates:
                    logger.debug(f"Duty rates for {hs_code} from CSV fallback")
            except Exception as e:
                logger.warning(f"CSV duty-rate query failed for {hs_code}: {e}")

        # 4. Hardcoded petroleum rates (ULTIMATE fallback)
        if rates is None and hs_code in _PETROLEUM_RATES_DEFAULT:
            pet_rates = _PETROLEUM_RATES_DEFAULT[hs_code]
            rates = {
                "cd_rate": pet_rates["cd"],
                "st_rate": pet_rates["st"],
                "vat_rate": pet_rates["vat"],
                "et_rate": pet_rates["et"],
                "atp_rate": pet_rates["atp"],
                "source": "hardcoded_petroleum",
            }
            logger.info(
                f"Using hardcoded petroleum rates for {hs_code}: "
                f"CD={pet_rates['cd']}, ST={pet_rates['st']}, VAT={pet_rates['vat']}, ATP={pet_rates['atp']}"
            )

        if rates is None:
            logger.warning(f"No duty rates found for HS code {hs_code}")
            return None

        # Enrich ATP rate from hardcoded table if primary source lacks it
        if hs_code in self._atp_rates:
            existing = rates.get("atp_rate")
            if existing is None or existing == 0:
                rates["atp_rate"] = float(self._atp_rates[hs_code])
                logger.debug(f"Enriched atp_rate={rates['atp_rate']} for {hs_code} from hardcoded table")

        return rates

    # =====================================================================
    # HS code info —
    #   Standalone: Calculator DB → CSV
    #   Legacy:     Qdrant → Shared PG → Calculator DB → CSV
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
            # LEGACY priority: Qdrant → Shared PG → Calculator DB → CSV
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

        # STANDALONE priority (also fallback in legacy):
        # Calculator DB → CSV
        if self.calculator_db:
            try:
                info = self.calculator_db.get_hs_code_info(hs_code)
                if info:
                    logger.debug(f"HS info for {hs_code} from CalculatorDB")
                    return info
            except Exception as e:
                logger.warning(f"CalculatorDB HS-info query failed for {hs_code}: {e}")

        if self.csv:
            try:
                info = self.csv.get_hs_code_info(hs_code)
                if info:
                    logger.debug(f"HS info for {hs_code} from CSV fallback")
                    return info
            except Exception as e:
                logger.warning(f"CSV HS-info query failed for {hs_code}: {e}")

        logger.warning(f"No HS code info found for {hs_code}")
        return None

    # =====================================================================
    # Exchange rate —
    #   Standalone: Calculator DB → Shared PG → CSV → env var
    #   Legacy:     Shared PG → Calculator DB → CSV → env var
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
            # LEGACY priority: Shared PG → Calculator DB → CSV → env var
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
            # STANDALONE priority: Calculator DB → Shared PG → CSV → env var
            if self.calculator_db:
                try:
                    rate = self.calculator_db.get_exchange_rate(currency_code, effective_date)
                    if rate:
                        logger.debug(f"Exchange rate {currency_code}->KHR from CalculatorDB: {rate}")
                        return rate
                except Exception as e:
                    logger.warning(f"CalculatorDB exchange-rate query failed for {currency_code}: {e}")

            if self.postgres:
                try:
                    rate = self.postgres.get_exchange_rate(currency_code, effective_date)
                    if rate:
                        logger.debug(f"Exchange rate {currency_code}->KHR from shared PostgreSQL: {rate}")
                        return rate
                except Exception as e:
                    logger.warning(f"Shared PostgreSQL exchange-rate query failed for {currency_code}: {e}")

        # CSV fallback (both modes)
        if self.csv:
            try:
                rate = self.csv.get_exchange_rate(currency_code, effective_date)
                if rate:
                    logger.debug(f"Exchange rate {currency_code}->KHR from CSV fallback: {rate}")
                    return rate
            except Exception as e:
                logger.warning(f"CSV exchange-rate query failed for {currency_code}: {e}")

        # Environment variable (emergency)
        fallback_key = f"{currency_code}_TO_KHR_RATE_FALLBACK"
        fallback_rate = os.getenv(fallback_key)
        if fallback_rate:
            try:
                rate = Decimal(fallback_rate)
                logger.debug(f"Exchange rate {currency_code}->KHR from env fallback: {rate}")
                return rate
            except Exception as e:
                logger.warning(f"Invalid fallback rate in {fallback_key}: {e}")

        logger.warning(f"No exchange rate found for {currency_code}")
        return None

    # =====================================================================
    # Declared value —
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
                        logger.info(f"Declared value for {hs_code} from SHARED PG (legacy)")
                        return {
                            "dv_per_metric_ton": Decimal(str(row[0])),
                            "currency": row[1] or "USD",
                            "source": row[2] or "government",
                        }
                except Exception as e:
                    logger.warning(f"Shared PostgreSQL declared-value query failed for {hs_code}: {e}")

            if self.calculator_db:
                try:
                    dv = self.calculator_db.get_declared_value(hs_code, effective_date)
                    if dv:
                        return dv
                except Exception as e:
                    logger.warning(f"CalculatorDB declared-value query failed for {hs_code}: {e}")
        else:
            # STANDALONE priority: Calculator DB → Shared PG
            if self.calculator_db:
                try:
                    dv = self.calculator_db.get_declared_value(hs_code, effective_date)
                    if dv:
                        return dv
                except Exception as e:
                    logger.warning(f"CalculatorDB declared-value query failed for {hs_code}: {e}")

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
                    logger.warning(f"Shared PostgreSQL declared-value query failed for {hs_code}: {e}")

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
        Legacy-compatible semantic HS search.
        Tries Qdrant first, then CSV fuzzy search.
        Returns (hs_code, confidence) or None.
        """
        # 1. Qdrant semantic search
        if self.qdrant:
            try:
                # QdrantClientAdapter may have search_by_description returning a tuple
                result = self.qdrant.search_by_description(query)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"Qdrant search_by_description failed: {e}")

        # 2. CSV fallback
        if self.csv:
            try:
                result = self.csv.search_by_description(query)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"CSV search_by_description failed: {e}")

        return None

    def search_hs_by_description(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Semantic HS search via Qdrant. Returns candidates with descriptions."""
        if not self.qdrant:
            logger.warning("Qdrant not available for semantic search")
            return []
        try:
            return self.qdrant.search_by_description(query, top_k)
        except Exception as e:
            logger.warning(f"Qdrant semantic search failed: {e}")
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
    # Health check
    # =====================================================================

    def check_health(self) -> Dict[str, Any]:
        calc_health = self.calculator_db.check_health() if self.calculator_db else {"ok": False, "message": "Not initialized"}
        qdrant_health = self.qdrant.check_health() if self.qdrant else {"ok": False, "message": "Not initialized (semantic search only)"}
        postgres_health = self.postgres.check_health() if self.postgres else {"ok": False, "message": "Not initialized (legacy fallback)"}
        csv_health = self.csv.check_health() if self.csv else {"ok": False, "message": "Not initialized"}

        # Top-level ok = True if primary source (calculator_db) is healthy
        primary_ok = calc_health.get("ok", False)
        return {
            "ok": primary_ok,
            "calculator_db": calc_health,
            "qdrant": qdrant_health,
            "shared_postgresql": postgres_health,
            "csv": csv_health,
        }
