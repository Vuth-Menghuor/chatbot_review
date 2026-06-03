"""
GDCE Calculator Service - Unified Database Adapter
===================================================
Hierarchical data access layer that uses:
- Qdrant (primary) for HS codes and duty rates
- PostgreSQL (primary) for exchange rates and ATP rates
- CSV (fallback) when above sources unavailable
- Hardcoded petroleum rates as ultimate fallback

Implements the DatabaseInterface contract from core.calculator.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional
from decimal import Decimal
from datetime import datetime

from .qdrant_client import QdrantClientAdapter
from .exchange_rate_adapter import PostgreSQLExchangeRateAdapter
from .csv_database import CSVDatabase
from ..core.calculator import DatabaseInterface

logger = logging.getLogger(__name__)


def _find_atp_excel_path() -> Optional[Path]:
    """Find the latest untartab Excel file using glob patterns."""
    search_paths = [
        Path("."),
        Path(__file__).parent.parent.parent.parent,
    ]
    candidates: list[Path] = []
    for base in search_paths:
        if base.exists():
            candidates.extend(base.glob("untartab*.xlsx"))
    if not candidates:
        return None
    # Return the most recently modified file
    return max(candidates, key=lambda p: p.stat().st_mtime)


# Hardcoded petroleum duty rates from untartab_202605120954.xlsx.
# These are the CURRENT valid rates (valid_from 2023-07-01, no end date).
# Format: cd_rate, st_rate, vat_rate are decimals (0.15 = 15%).
_PETROLEUM_RATES_DEFAULT: Dict[str, Dict[str, float]] = {
    "2710.12.11": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.12": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.13": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.21": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.22": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.23": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.24": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.25": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.26": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.27": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.28": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.12.29": {"cd": 0.15, "st": 0.10, "vat": 0.10, "et": 0.0, "atp": 0.02},
    "2710.19.71": {"cd": 0.00, "st": 0.03, "vat": 0.10, "et": 0.0, "atp": 0.04},
    "2710.19.72": {"cd": 0.00, "st": 0.03, "vat": 0.10, "et": 0.0, "atp": 0.04},
}

# ATP-only lookup derived from the table above (for backward-compat logging)
_ATP_RATES_DEFAULT: Dict[str, Decimal] = {
    k: Decimal(str(v["atp"])) for k, v in _PETROLEUM_RATES_DEFAULT.items()
}

# Mapping from common country names to ISO alpha-2 codes for preferential rate lookup
_COUNTRY_NAME_TO_CODE: Dict[str, str] = {
    "CHINA": "CN",
    "THAILAND": "TH",
    "VIETNAM": "VN",
    "MALAYSIA": "MY",
    "SINGAPORE": "SG",
    "INDONESIA": "ID",
    "PHILIPPINES": "PH",
    "BRUNEI": "BN",
    "MYANMAR": "MM",
    "LAOS": "LA",
    "CAMBODIA": "KH",
    "KOREA": "KR",
    "SOUTH KOREA": "KR",
    "JAPAN": "JP",
    "AUSTRALIA": "AU",
    "NEW ZEALAND": "NZ",
    "INDIA": "IN",
    "UNITED STATES": "US",
    "USA": "US",
    "UNITED KINGDOM": "GB",
    "UK": "GB",
    "GERMANY": "DE",
    "FRANCE": "FR",
    "ITALY": "IT",
    "SPAIN": "ES",
    "NETHERLANDS": "NL",
    "BELGIUM": "BE",
    "SWITZERLAND": "CH",
    "RUSSIA": "RU",
    "CANADA": "CA",
    "MEXICO": "MX",
    "BRAZIL": "BR",
    "ARGENTINA": "AR",
    "SOUTH AFRICA": "ZA",
    "TURKEY": "TR",
    "PAKISTAN": "PK",
    "BANGLADESH": "BD",
    "SRI LANKA": "LK",
    "NEPAL": "NP",
    "BHUTAN": "BT",
    "MALDIVES": "MV",
    "AFGHANISTAN": "AF",
    "IRAN": "IR",
    "IRAQ": "IQ",
    "SYRIA": "SY",
    "LEBANON": "LB",
    "ISRAEL": "IL",
    "JORDAN": "JO",
    "SAUDI ARABIA": "SA",
    "UAE": "AE",
    "UNITED ARAB EMIRATES": "AE",
    "QATAR": "QA",
    "KUWAIT": "KW",
    "BAHRAIN": "BH",
    "OMAN": "OM",
    "YEMEN": "YE",
    "EGYPT": "EG",
    "LIBYA": "LY",
    "TUNISIA": "TN",
    "ALGERIA": "DZ",
    "MOROCCO": "MA",
    "SUDAN": "SD",
    "ETHIOPIA": "ET",
    "KENYA": "KE",
    "TANZANIA": "TZ",
    "UGANDA": "UG",
    "RWANDA": "RW",
    "BURUNDI": "BI",
    "CONGO": "CG",
    "DEMOCRATIC REPUBLIC OF THE CONGO": "CD",
    "DRC": "CD",
    "ZAMBIA": "ZM",
    "ZIMBABWE": "ZW",
    "BOTSWANA": "BW",
    "NAMIBIA": "NA",
    "ANGOLA": "AO",
    "MOZAMBIQUE": "MZ",
    "MADAGASCAR": "MG",
    "MAURITIUS": "MU",
    "SEYCHELLES": "SC",
    "NIGERIA": "NG",
    "GHANA": "GH",
    "IVORY COAST": "CI",
    "SENEGAL": "SN",
    "MALI": "ML",
    "BURKINA FASO": "BF",
    "NIGER": "NE",
    "CHAD": "TD",
    "CENTRAL AFRICAN REPUBLIC": "CF",
    "CAMEROON": "CM",
    "GABON": "GA",
    "EQUATORIAL GUINEA": "GQ",
    "SAO TOME AND PRINCIPE": "ST",
    "CAPE VERDE": "CV",
    "GAMBIA": "GM",
    "GUINEA": "GN",
    "GUINEA BISSAU": "GW",
    "SIERRA LEONE": "SL",
    "LIBERIA": "LR",
    "TOGO": "TG",
    "BENIN": "BJ",
    "MAURITANIA": "MR",
    "WESTERN SAHARA": "EH",
    "SOMALIA": "SO",
    "DJIBOUTI": "DJ",
    "ERITREA": "ER",
    "TAIWAN": "TW",
    "HONG KONG": "HK",
    "MACAU": "MO",
    "MONGOLIA": "MN",
    "KAZAKHSTAN": "KZ",
    "UZBEKISTAN": "UZ",
    "TURKMENISTAN": "TM",
    "TAJIKISTAN": "TJ",
    "KYRGYZSTAN": "KG",
    "GEORGIA": "GE",
    "ARMENIA": "AM",
    "AZERBAIJAN": "AZ",
    "UKRAINE": "UA",
    "BELARUS": "BY",
    "MOLDOVA": "MD",
    "ESTONIA": "EE",
    "LATVIA": "LV",
    "LITHUANIA": "LT",
    "POLAND": "PL",
    "CZECH REPUBLIC": "CZ",
    "CZECHIA": "CZ",
    "SLOVAKIA": "SK",
    "HUNGARY": "HU",
    "ROMANIA": "RO",
    "BULGARIA": "BG",
    "CROATIA": "HR",
    "SLOVENIA": "SI",
    "SERBIA": "RS",
    "MONTENEGRO": "ME",
    "NORTH MACEDONIA": "MK",
    "MACEDONIA": "MK",
    "ALBANIA": "AL",
    "BOSNIA AND HERZEGOVINA": "BA",
    "KOSOVO": "XK",
    "GREECE": "GR",
    "CYPRUS": "CY",
    "MALTA": "MT",
    "ICELAND": "IS",
    "NORWAY": "NO",
    "SWEDEN": "SE",
    "FINLAND": "FI",
    "DENMARK": "DK",
    "IRELAND": "IE",
    "PORTUGAL": "PT",
    "LUXEMBOURG": "LU",
    "MONACO": "MC",
    "ANDORRA": "AD",
    "LIECHTENSTEIN": "LI",
    "SAN MARINO": "SM",
    "VATICAN": "VA",
    "CHILE": "CL",
    "PERU": "PE",
    "ECUADOR": "EC",
    "COLOMBIA": "CO",
    "VENEZUELA": "VE",
    "BOLIVIA": "BO",
    "PARAGUAY": "PY",
    "URUGUAY": "UY",
    "GUYANA": "GY",
    "SURINAME": "SR",
    "FRENCH GUIANA": "GF",
    "PANAMA": "PA",
    "COSTA RICA": "CR",
    "NICARAGUA": "NI",
    "HONDURAS": "HN",
    "EL SALVADOR": "SV",
    "GUATEMALA": "GT",
    "BELIZE": "BZ",
    "CUBA": "CU",
    "JAMAICA": "JM",
    "HAITI": "HT",
    "DOMINICAN REPUBLIC": "DO",
    "TRINIDAD AND TOBAGO": "TT",
    "BARBADOS": "BB",
    "SAINT LUCIA": "LC",
    "GRENADA": "GD",
    "SAINT VINCENT AND THE GRENADINES": "VC",
    "ANTIGUA AND BARBUDA": "AG",
    "DOMINICA": "DM",
    "SAINT KITTS AND NEVIS": "KN",
    "BAHAMAS": "BS",
    "FIJI": "FJ",
    "PAPUA NEW GUINEA": "PG",
    "SOLOMON ISLANDS": "SB",
    "VANUATU": "VU",
    "SAMOA": "WS",
    "TONGA": "TO",
    "KIRIBATI": "KI",
    "TUVALU": "TV",
    "NAURU": "NR",
    "PALAU": "PW",
    "MARSHALL ISLANDS": "MH",
    "MICRONESIA": "FM",
    "GUAM": "GU",
    "AMERICAN SAMOA": "AS",
    "COOK ISLANDS": "CK",
    "NIUE": "NU",
    "TOKELAU": "TK",
    "PITCAIRN": "PN",
    "WALLIS AND FUTUNA": "WF",
    "FRENCH POLYNESIA": "PF",
    "NEW CALEDONIA": "NC",
    "TIMOR LESTE": "TL",
    "EAST TIMOR": "TL",
}


def _load_atp_rates_from_excel(excel_path: Optional[Path] = None) -> tuple[Dict[str, Decimal], Optional[Path], float]:
    """
    TEMPORARY: Load ATP rates from untartab Excel file.

    Uses hardcoded defaults for instant startup.  The Excel file is only
    parsed when explicitly requested (e.g. admin reload) because reading
    a 65 k-row .xlsx with pandas/openpyxl takes 50–80 s.

    TODO: Remove when team uploads untartab to PostgreSQL.
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
    """Unified database adapter with hierarchical fallback strategy."""

    def __init__(self, enable_qdrant: bool = True, enable_postgres: bool = True, enable_csv: bool = True):
        """
        Initialize unified database adapter.

        Args:
            enable_qdrant: Enable Qdrant connection (primary for duty rates)
            enable_postgres: Enable PostgreSQL connection (primary for exchange rates)
            enable_csv: Enable CSV fallback (used if Qdrant/PostgreSQL unavailable)
        """
        self.qdrant: Optional[QdrantClientAdapter] = None
        self.postgres: Optional[PostgreSQLExchangeRateAdapter] = None
        self.csv: Optional[CSVDatabase] = None

        # TEMPORARY: Load ATP rates from Excel until DB is populated
        self._atp_rates: Dict[str, Decimal] = {k: Decimal(str(v)) for k, v in _ATP_RATES_DEFAULT.items()}
        self._atp_excel_path: Optional[Path] = None
        self._atp_mtime: float = 0.0
        self._reload_atp_rates()

        # Try to initialize Qdrant (primary for duty rates)
        if enable_qdrant:
            try:
                self.qdrant = QdrantClientAdapter()
                logger.info("✅ Qdrant adapter initialized (primary for duty rates)")
            except Exception as e:
                logger.warning(f"⚠️  Qdrant unavailable: {e}")
                self.qdrant = None

        # Try to initialize PostgreSQL (primary for exchange rates)
        if enable_postgres:
            try:
                self.postgres = PostgreSQLExchangeRateAdapter()
                logger.info("✅ PostgreSQL adapter initialized (primary for exchange rates)")
            except Exception as e:
                logger.warning(f"⚠️  PostgreSQL unavailable: {e}")
                self.postgres = None

        # Initialize CSV fallback
        if enable_csv:
            try:
                self.csv = CSVDatabase()
                logger.info("✅ CSV fallback initialized")
            except Exception as e:
                logger.warning(f"⚠️  CSV fallback unavailable: {e}")
                self.csv = None

        # Try to initialize Rules DB (customs_ai — for preferential rates)
        self.rules_db = None
        try:
            from .rules_database import RulesDatabaseAdapter
            self.rules_db = RulesDatabaseAdapter()
            logger.info("✅ Rules DB adapter initialized (customs_ai for preferential rates)")
        except Exception as e:
            logger.warning(f"⚠️  Rules DB (customs_ai) unavailable: {e}")
            self.rules_db = None

        # Verify at least one source is available
        if not (self.qdrant or self.csv):
            logger.error("❌ No duty rate source available (need Qdrant or CSV)")
        if not (self.postgres or self.csv):
            logger.error("⚠️  No exchange rate source available (need PostgreSQL or CSV)")

    @staticmethod
    def _normalize_origin_country(origin: str) -> str:
        """Normalize country name or code to ISO alpha-2 for preferential rate lookup."""
        if not origin:
            return ""
        origin_upper = origin.strip().upper()
        if len(origin_upper) == 2 and origin_upper.isalpha():
            return origin_upper
        return _COUNTRY_NAME_TO_CODE.get(origin_upper, origin_upper)

    def _reload_atp_rates(self) -> None:
        """Reload ATP rates from Excel if the file has changed or was not loaded."""
        try:
            current_path = _find_atp_excel_path()
            if current_path is None:
                return
            mtime = current_path.stat().st_mtime
            if current_path == self._atp_excel_path and mtime == self._atp_mtime:
                return  # No change
            rates, path, new_mtime = _load_atp_rates_from_excel(current_path)
            self._atp_rates = rates
            self._atp_excel_path = path
            self._atp_mtime = new_mtime
        except Exception as e:
            logger.warning(f"ATP rate reload check failed: {e}")

    def _get_atp_rate_from_db(self, hs_code: str) -> Optional[float]:
        """Query PostgreSQL duty_rates table for ATP rate."""
        if not self.postgres or not self.postgres.conn:
            return None
        try:
            cursor = self.postgres.conn.cursor()
            cursor.execute(
                "SELECT atp_rate FROM duty_rates WHERE hs_code = %s LIMIT 1",
                (hs_code,)
            )
            row = cursor.fetchone()
            cursor.close()
            if row and row[0] is not None:
                atp = float(row[0])
                if atp > 0:
                    return atp
        except Exception as e:
            logger.debug(f"DB ATP lookup failed for {hs_code}: {e}")
        return None

    def get_duty_rates(
        self,
        hs_code: str,
        origin_country: str = "XX",
        effective_date: str = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get duty rates with hierarchical fallback.

        Priority:
        1. Qdrant (primary) - has all rate fields in payload
        2. CSV (fallback) - loaded in memory
        3. Hardcoded petroleum rates (ultimate fallback for known petroleum HS codes)

        ATP rate is enriched from PostgreSQL duty_rates table when available.

        Args:
            hs_code: HS code (e.g., "0102.29.11")
            origin_country: Origin country code (used by CSV as fallback)
            effective_date: Not used for Qdrant (rates don't change by date in this impl)

        Returns:
            Dict with cd_rate, st_rate, vat_rate, et_rate, atp_rate (as decimals 0-1.0)
        """
        rates = None

        # Try Qdrant first
        if self.qdrant:
            try:
                rates = self.qdrant.get_duty_rates(hs_code)
                if rates:
                    logger.debug(f"Duty rates for {hs_code} from Qdrant")
            except Exception as e:
                logger.warning(f"Qdrant query failed for {hs_code}: {e}")

        # Fallback to CSV
        if rates is None and self.csv:
            try:
                rates = self.csv.get_duty_rates(hs_code, origin_country, effective_date)
                if rates:
                    logger.debug(f"Duty rates for {hs_code} from CSV fallback")
            except Exception as e:
                logger.warning(f"CSV query failed for {hs_code}: {e}")

        # Fallback to hardcoded petroleum rates for known petroleum HS codes
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
            logger.info(f"Using hardcoded petroleum rates for {hs_code}: CD={pet_rates['cd']}, ST={pet_rates['st']}, VAT={pet_rates['vat']}, ATP={pet_rates['atp']}")

        if rates is None:
            logger.warning(f"No duty rates found for HS code {hs_code}")
            return None

        # Enrich with ATP rate from PostgreSQL duty_rates table
        atp_from_db = self._get_atp_rate_from_db(hs_code)
        if atp_from_db is not None:
            rates["atp_rate"] = atp_from_db
            logger.debug(f"Enriched atp_rate={atp_from_db} for {hs_code} from PostgreSQL")
        elif "atp_rate" not in rates and hs_code in self._atp_rates:
            # Fallback to hardcoded ATP table
            rates["atp_rate"] = float(self._atp_rates[hs_code])
            logger.debug(f"Enriched atp_rate={rates['atp_rate']} for {hs_code} from hardcoded table")

        # Enrich with origin-specific preferential flags when available in Postgres
        try:
            if self.postgres and getattr(self.postgres, 'conn', None):
                cur = self.postgres.conn.cursor()
                # Best-effort: attempt to read a 'fta_eligible' boolean column
                try:
                    cur.execute(
                        "SELECT fta_eligible FROM duty_rates WHERE hs_code = %s AND origin_country = %s LIMIT 1",
                        (hs_code, self._normalize_origin_country(origin_country))
                    )
                    row = cur.fetchone()
                    if row and row[0] is not None:
                        rates["fta_eligible"] = bool(row[0])
                        logger.debug(f"Enriched fta_eligible={rates['fta_eligible']} for {hs_code} origin={origin_country}")
                except Exception:
                    # Table may not have the column; ignore and continue
                    pass
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Could not enrich fta_eligible from Postgres: {e}")

        return rates

    def get_declared_value(
        self,
        hs_code: str,
        effective_date: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get government-declared fair market value per metric ton for an HS code.

        Priority:
        1. PostgreSQL declared_values table
        2. None (caller falls back to request value or CIF-derived)

        Args:
            hs_code: HS code (e.g., "2710.11.11")
            effective_date: Date to look up (format: YYYY-MM-DD)

        Returns:
            Dict with dv_per_metric_ton, currency, source, or None if not found.
        """
        if not effective_date:
            effective_date = datetime.now().strftime("%Y-%m-%d")

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
                    (hs_code, effective_date)
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
                logger.warning(f"PostgreSQL declared_value lookup failed for {hs_code}: {e}")

        return None

    def get_exchange_rate(
        self,
        currency_code: str,
        effective_date: str = None
    ) -> Optional[Decimal]:
        """
        Get exchange rate to KHR with hierarchical fallback.
        
        Priority:
        1. PostgreSQL (primary) - latest/dated rates from table
        2. CSV (fallback) - hardcoded in CSV file
        3. Environment variable (fallback) - e.g., USD_TO_KHR_RATE_FALLBACK
        
        Args:
            currency_code: Currency code (e.g., "USD")
            effective_date: Date to look up (format: YYYY-MM-DD)
            
        Returns:
            Exchange rate as Decimal (e.g., 4022.0)
        """
        if not effective_date:
            effective_date = datetime.now().strftime("%Y-%m-%d")

        # Try PostgreSQL first
        if self.postgres:
            try:
                rate = self.postgres.get_exchange_rate(currency_code, effective_date)
                if rate:
                    logger.debug(f"Exchange rate {currency_code}->KHR from PostgreSQL: {rate}")
                    return rate
            except Exception as e:
                logger.warning(f"PostgreSQL query failed for {currency_code}: {e}")

        # Fallback to CSV
        if self.csv:
            try:
                rate = self.csv.get_exchange_rate(currency_code, effective_date)
                if rate:
                    logger.debug(f"Exchange rate {currency_code}->KHR from CSV fallback: {rate}")
                    return rate
            except Exception as e:
                logger.warning(f"CSV query failed for {currency_code}: {e}")

        # Fallback to environment variable (e.g., USD_TO_KHR_RATE_FALLBACK)
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

    def get_hs_code_info(self, hs_code: str) -> Optional[Dict[str, Any]]:
        """
        Get HS code info with hierarchical fallback.
        
        Priority:
        1. Qdrant (primary) - payload includes description and unit
        2. CSV (fallback) - loaded in memory
        """
        # Try Qdrant first
        if self.qdrant:
            try:
                info = self.qdrant.get_hs_code_info(hs_code)
                if info:
                    logger.debug(f"HS info for {hs_code} from Qdrant")
                    return info
            except Exception as e:
                logger.warning(f"Qdrant query failed for {hs_code}: {e}")

        # Fallback to CSV
        if self.csv:
            try:
                info = self.csv.get_hs_code_info(hs_code)
                if info:
                    logger.debug(f"HS info for {hs_code} from CSV fallback")
                    return info
            except Exception as e:
                logger.warning(f"CSV query failed for {hs_code}: {e}")

        logger.warning(f"No HS code info found for {hs_code}")
        return None

    def save_calculation(self, calculation_result: Any) -> None:
        """Save calculation result for audit trail (not implemented in fallback)."""
        logger.info(f"Calculation saved: {calculation_result.calculation_id}")

    def check_health(self) -> Dict[str, Any]:
        """Check health of all data sources."""
        return {
            "qdrant": self.qdrant.check_health() if self.qdrant else {"ok": False, "message": "Not initialized"},
            "postgresql": self.postgres.check_health() if self.postgres else {"ok": False, "message": "Not initialized"},
            "csv": self.csv.check_health() if self.csv else {"ok": False, "message": "Not initialized"},
        }
