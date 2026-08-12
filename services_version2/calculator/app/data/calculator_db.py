
"""
GDCE Calculator Service - Calculator PostgreSQL Adapter

=========================================================
Primary data access layer for the standalone calculator.
Connects to the calculator's own PostgreSQL database (gdce_calculator)
and implements the DatabaseInterface contract.

This is the PRIMARY source of truth for:
- Duty rates (by HS code + origin country)
- HS code descriptions and units
- Exchange rates
- Deduction values (DV per metric ton)
- Dynamic rules (formulas, rounding_rules, policies, exemptions)
- Calculation history (audit trail)

Tables served:
    hs_codes, duty_rates, exchange_rates, declared_values,
    fees, exemptions, formulas, policies, rounding_rules,
    rules_audit_log, calculation_history

Date: 2026-06-11
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CalculatorDatabaseAdapter:
    """
    PostgreSQL adapter for the calculator's dedicated database.
    Uses psycopg2 with a simple connection-per-request pattern.
    Future: can upgrade to ThreadedConnectionPool or asyncpg.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
        ssl_mode: str | None = None,
    ):
        self.host = host or os.getenv("CALCULATOR_DB_HOST", "localhost")
        self.port = port or int(os.getenv("CALCULATOR_DB_PORT", "5432"))
        self.database = database or os.getenv("CALCULATOR_DB_NAME", "gdce_calculator")
        self.user = user or os.getenv("CALCULATOR_DB_USER", "calc_app")
        self.password = password or os.getenv("CALCULATOR_DB_PASSWORD", "")
        self.ssl_mode = ssl_mode or os.getenv("CALCULATOR_DB_SSL_MODE", "disable")

        self._psycopg2 = None
        self._pool = None
        self._connect()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Import psycopg2 and open one connection to verify parameters."""
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            self._psycopg2 = psycopg2
            self._RealDictCursor = RealDictCursor

            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.close()

            logger.info(
                f"CalculatorDB connected to {self.host}:{self.port}/{self.database} "
                f"as {self.user}"
            )
        except ImportError:
            logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to calculator database: {e}")
            raise

    def _get_connection(self):
        """Return a fresh psycopg2 connection."""
        if self._psycopg2 is None:
            raise RuntimeError("psycopg2 not available")
        conn_kwargs = {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "user": self.user,
            "password": self.password,
            "connect_timeout": 5,
        }
        if self.ssl_mode:
            conn_kwargs["sslmode"] = self.ssl_mode
        return self._psycopg2.connect(**conn_kwargs)

    @contextmanager
    def _cursor(self, dict_cursor: bool = True):
        """Context manager that yields a cursor and commits on success."""
        conn = self._get_connection()
        try:
            if dict_cursor:
                cursor = conn.cursor(cursor_factory=self._RealDictCursor)
            else:
                cursor = conn.cursor()
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    # ------------------------------------------------------------------
    # Duty rates
    # ------------------------------------------------------------------

    def get_duty_rates(
        self,
        hs_code: str,
        origin_country: str = "XX",
        effective_date: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get duty rates from the calculator's duty_rates table.
        Falls back to general MFN (origin='XX') if country-specific not found.
        """
        if not effective_date:
            effective_date = datetime.now().strftime("%Y-%m-%d")

        with self._cursor() as cur:
            # 1. Try country-specific rate
            cur.execute(
                """
                SELECT dr.hs_code, dr.cd_rate, dr.st_rate, dr.vat_rate,
                       dr.et_rate, dr.atp_rate, dr.origin_country,
                       dr.effective_date, hs.description, hs.unit
                FROM duty_rates dr
                JOIN hs_codes hs ON dr.hs_code = hs.hs_code
                WHERE dr.hs_code = %s
                  AND dr.origin_country = %s
                  AND dr.is_active = TRUE
                  AND (dr.end_date IS NULL OR dr.end_date > %s)
                  AND dr.effective_date <= %s
                ORDER BY dr.effective_date DESC
                LIMIT 1
                """,
                (hs_code, origin_country, effective_date, effective_date),
            )
            row = cur.fetchone()

            # 2. Fallback to MFN (XX)
            if row is None and origin_country != "XX":
                cur.execute(
                    """
                    SELECT dr.hs_code, dr.cd_rate, dr.st_rate, dr.vat_rate,
                           dr.et_rate, dr.atp_rate, dr.origin_country,
                           dr.effective_date, hs.description, hs.unit
                    FROM duty_rates dr
                    JOIN hs_codes hs ON dr.hs_code = hs.hs_code
                    WHERE dr.hs_code = %s
                      AND dr.origin_country = 'XX'
                      AND dr.is_active = TRUE
                      AND (dr.end_date IS NULL OR dr.end_date > %s)
                      AND dr.effective_date <= %s
                    ORDER BY dr.effective_date DESC
                    LIMIT 1
                    """,
                    (hs_code, effective_date, effective_date),
                )
                row = cur.fetchone()

            if row is None:
                return None

            return {
                "hs_code": row["hs_code"],
                "cd_rate": Decimal(str(row["cd_rate"])) / Decimal("100") if row["cd_rate"] is not None else Decimal("0"),
                "st_rate": Decimal(str(row["st_rate"])) / Decimal("100") if row["st_rate"] is not None else Decimal("0"),
                "vat_rate": Decimal(str(row["vat_rate"])) / Decimal("100") if row["vat_rate"] is not None else Decimal("0.1"),
                "et_rate": Decimal(str(row["et_rate"])) / Decimal("100") if row["et_rate"] is not None else Decimal("0"),
                "atp_rate": float(row["atp_rate"]) if row["atp_rate"] is not None else 0.0,
                "origin_country": row["origin_country"],
                "description": row["description"],
                "unit": row["unit"],
                "source": "calculator_db",
            }

    # ------------------------------------------------------------------
    # HS code info
    # ------------------------------------------------------------------

    def get_hs_code_info(self, hs_code: str) -> Optional[Dict[str, Any]]:
        """Get HS code description and unit from hs_codes table."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT hs_code, description, unit
                FROM hs_codes
                WHERE hs_code = %s
                  AND is_active = TRUE
                  AND (end_date IS NULL OR end_date > CURRENT_DATE)
                LIMIT 1
                """,
                (hs_code,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "hs_code": row["hs_code"],
                "description": row["description"],
                "unit": row["unit"],
                "source": "calculator_db",
            }

    def get_hs_codes_by_prefix(
        self,
        prefix: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get HS codes starting with a given prefix.

        Args:
            prefix: HS prefix (e.g. "7204")
            limit: Maximum number of results

        Returns:
            List of dicts with keys: hs_code, description, unit
        """
        if not prefix or not isinstance(prefix, str):
            return []

        clean_prefix = prefix.replace(".", "")
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT hs_code, description, unit
                FROM hs_codes
                WHERE hs_code LIKE %s
                  AND is_active = TRUE
                  AND (end_date IS NULL OR end_date > CURRENT_DATE)
                ORDER BY hs_code ASC
                LIMIT %s
                """,
                (f"{clean_prefix}%", limit),
            )
            rows = cur.fetchall()
            return [
                {
                    "hs_code": r["hs_code"],
                    "description": r["description"],
                    "unit": r["unit"],
                }
                for r in rows
            ]

    def search_hs_by_description(
        self,
        query: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search HS codes by description using PostgreSQL ILIKE.
        Splits query into words and matches descriptions containing any word.
        """
        if not query or not isinstance(query, str):
            return []

        words = [w for w in query.lower().split() if len(w) > 2]
        if not words:
            words = [query.lower()]

        with self._cursor() as cur:
            conditions = " OR ".join(["description ILIKE %s"] * len(words))
            params = [f"%{w}%" for w in words] + [limit]
            cur.execute(
                f"""
                SELECT hs_code, description, unit
                FROM hs_codes
                WHERE ({conditions})
                  AND is_active = TRUE
                  AND (end_date IS NULL OR end_date > CURRENT_DATE)
                ORDER BY hs_code ASC
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
            return [
                {
                    "hs_code": r["hs_code"],
                    "description": r["description"],
                    "unit": r["unit"],
                }
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Exchange rates
    # ------------------------------------------------------------------

    def get_exchange_rate(
        self, currency_code: str, effective_date: str | None = None
    ) -> Optional[Decimal]:
        """Get exchange rate to KHR from calculator's exchange_rates table."""
        if not effective_date:
            effective_date = datetime.now().strftime("%Y-%m-%d")

        with self._cursor() as cur:
            cur.execute(
                """
                SELECT local_rate
                FROM exchange_rates
                WHERE currency = %s
                  AND effective_date <= %s
                ORDER BY effective_date DESC
                LIMIT 1
                """,
                (currency_code, effective_date),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return Decimal(str(row["local_rate"]))

    def get_all_exchange_rates(self, effective_date: str | None = None) -> Optional[Dict[str, Decimal]]:
        """Get all latest exchange rates."""
        if not effective_date:
            effective_date = datetime.now().strftime("%Y-%m-%d")

        with self._cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (currency)
                       currency, local_rate
                FROM exchange_rates
                WHERE effective_date <= %s
                ORDER BY currency, effective_date DESC
                """,
                (effective_date,),
            )
            rows = cur.fetchall()
            return {r["currency"]: Decimal(str(r["local_rate"])) for r in rows} if rows else None

    # ------------------------------------------------------------------
    # Deduction values
    # ------------------------------------------------------------------

    def get_declared_value(
        self, hs_code: str, effective_date: str | None = None
    ) -> Optional[Dict[str, Any]]:
        """Get government Deduction Value (DV) per metric ton."""
        if not effective_date:
            effective_date = datetime.now().strftime("%Y-%m-%d")

        with self._cursor() as cur:
            cur.execute(
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
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "dv_per_metric_ton": Decimal(str(row["dv_per_metric_ton"])),
                "currency": row["currency"] or "USD",
                "source": row["source"] or "government",
            }

    # ------------------------------------------------------------------
    # Reference data: FTA types, country groups, country-region mappings
    # ------------------------------------------------------------------

    def get_preferential_rate(self, agreement_code: str) -> Optional[Dict[str, Any]]:
        """Get FTA / preferential agreement reference by code (any row)."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT agreement_code, origin_country, hs_code, name_en, name_kh, valid_from, valid_to
                FROM preferential_rates
                WHERE agreement_code = %s
                LIMIT 1
                """,
                (agreement_code.upper(),),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return dict(row)

    def is_agreement_valid_for_country(
        self, agreement_code: str, origin_country: str
    ) -> bool:
        """Check whether an agreement actually covers the given origin country."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM preferential_rates
                WHERE agreement_code = %s AND origin_country = %s
                LIMIT 1
                """,
                (agreement_code.upper(), origin_country.upper()),
            )
            return cur.fetchone() is not None

    def list_agreements_for_country(self, origin_country: str) -> List[Dict[str, Any]]:
        """List all agreements that cover the given origin country."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT agreement_code, hs_code, name_en, name_kh, valid_from, valid_to
                FROM preferential_rates
                WHERE origin_country = %s
                ORDER BY agreement_code
                """,
                (origin_country.upper(),),
            )
            return [dict(r) for r in cur.fetchall()]

    def list_preferential_rates(self) -> List[Dict[str, Any]]:
        """List all agreement-country pairs."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT agreement_code, origin_country, hs_code, name_en, name_kh, valid_from, valid_to
                FROM preferential_rates
                ORDER BY agreement_code, origin_country
                """
            )
            return [dict(r) for r in cur.fetchall()]

    def get_country_regions(self, country_code: str) -> List[Dict[str, Any]]:
        """Get region groups for a country (e.g., CN -> ['ASI', 'CHN'])."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT country_code, region_code, region_desc
                FROM countries_by_regions
                WHERE country_code = %s
                """,
                (country_code.upper(),),
            )
            return [dict(r) for r in cur.fetchall()]

    def list_country_groups(self) -> List[Dict[str, Any]]:
        """List all country groups / regions."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT code, name, name_kh, valid_from
                FROM country_groups
                ORDER BY code
                """
            )
            return [dict(r) for r in cur.fetchall()]

    # ------------------------------------------------------------------
    # Calculation history (audit trail)
    # ------------------------------------------------------------------

    def save_calculation(self, calculation_result: Any) -> None:
        """Persist a calculation result into calculation_history."""
        try:
            # Extract fields safely from the result object/dict
            data = getattr(calculation_result, "__dict__", calculation_result)
            if isinstance(data, dict):
                pass
            else:
                data = {}

            with self._cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO calculation_history (
                        session_id, hs_code, origin_country,
                        invoice_value, invoice_currency, freight, insurance,
                        cif_value, customs_duty, special_tax, vat,
                        export_tax, total_tax, exemption_code,
                        calculation_method, formulas_used, input_data, result_data
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        data.get("session_id"),
                        data.get("hs_code"),
                        data.get("origin_country"),
                        data.get("invoice_value"),
                        data.get("invoice_currency"),
                        data.get("freight"),
                        data.get("insurance"),
                        data.get("cif_value"),
                        data.get("customs_duty"),
                        data.get("special_tax"),
                        data.get("vat"),
                        data.get("export_tax"),
                        data.get("total_tax"),
                        data.get("exemption_code"),
                        data.get("calculation_method"),
                        None,  # formulas_used — JSONB
                        None,  # input_data — JSONB
                        None,  # result_data — JSONB
                    ),
                )
            logger.info(f"Calculation saved to history: {data.get('hs_code')}")
        except Exception as e:
            logger.warning(f"Failed to save calculation history: {e}")

    # ------------------------------------------------------------------
    # Rules engine support
    # ------------------------------------------------------------------

    def get_formulas(self, formula_type: str | None = None) -> List[Dict[str, Any]]:
        """Load active formulas from the database."""
        with self._cursor() as cur:
            if formula_type:
                cur.execute(
                    """
                    SELECT formula_id, formula_name, formula_type, expression,
                           description, variables, is_active, version, effective_date
                    FROM formulas
                    WHERE is_active = TRUE
                      AND formula_type = %s
                      AND (end_date IS NULL OR end_date > CURRENT_DATE)
                    ORDER BY effective_date DESC
                    """,
                    (formula_type,),
                )
            else:
                cur.execute(
                    """
                    SELECT formula_id, formula_name, formula_type, expression,
                           description, variables, is_active, version, effective_date
                    FROM formulas
                    WHERE is_active = TRUE
                      AND (end_date IS NULL OR end_date > CURRENT_DATE)
                    ORDER BY effective_date DESC
                    """
                )
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []

    def get_rounding_rules(self) -> List[Dict[str, Any]]:
        """Load active rounding rules."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT rule_id, rule_name, rule_type, rounding_mode,
                       precision, conditions, is_active, effective_date
                FROM rounding_rules
                WHERE is_active = TRUE
                  AND (end_date IS NULL OR end_date > CURRENT_DATE)
                ORDER BY rule_id
                """
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []

    def get_policies(self) -> List[Dict[str, Any]]:
        """Load active policies."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT policy_id, policy_name, policy_type, conditions,
                       actions, priority, is_active, effective_date
                FROM policies
                WHERE is_active = TRUE
                  AND (end_date IS NULL OR end_date > CURRENT_DATE)
                ORDER BY priority
                """
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []

    def get_exemptions(self) -> List[Dict[str, Any]]:
        """Load active exemptions."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT exemption_code, regime_name, exemption_type,
                       cd_exempt, st_exempt, vat_exempt, et_exempt,
                       cd_reduction_pct, vat_reduction_pct, conditions
                FROM exemptions
                WHERE is_active = TRUE
                  AND (end_date IS NULL OR end_date > CURRENT_DATE)
                """
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []

    def get_fees(self) -> List[Dict[str, Any]]:
        """Load active fees."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT fee_code, fee_name, basis, amount, currency,
                       percentage, is_active
                FROM fees
                WHERE is_active = TRUE
                  AND (end_date IS NULL OR end_date > CURRENT_DATE)
                """
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows] if rows else []

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def check_health(self) -> Dict[str, Any]:
        """Return health status of the calculator database."""
        try:
            with self._cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM duty_rates;")
                duty_count = cur.fetchone()["count"]
                cur.execute("SELECT COUNT(*) FROM exchange_rates;")
                exchange_count = cur.fetchone()["count"]
                cur.execute("SELECT COUNT(*) FROM hs_codes;")
                hs_count = cur.fetchone()["count"]

            return {
                "ok": True,
                "server": f"{self.host}:{self.port}",
                "database": self.database,
                "duty_rates_count": duty_count,
                "exchange_rates_count": exchange_count,
                "hs_codes_count": hs_count,
                "message": "Connected",
            }
        except Exception as e:
            return {
                "ok": False,
                "server": f"{self.host}:{self.port}",
                "database": self.database,
                "message": str(e),
            }

    # ------------------------------------------------------------------
    # Bulk insert helpers (used by migration scripts)
    # ------------------------------------------------------------------

    def bulk_insert_hs_codes(self, records: List[Dict[str, Any]], upsert: bool = True) -> int:
        """Bulk insert HS codes. If upsert=True, updates on conflict."""
        if not records:
            return 0
        with self._cursor(dict_cursor=False) as cur:
            if upsert:
                for rec in records:
                    cur.execute(
                        """
                        INSERT INTO hs_codes (hs_code, description, unit, is_active, effective_date, notes)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (hs_code) DO UPDATE SET
                            description = EXCLUDED.description,
                            unit = EXCLUDED.unit,
                            is_active = EXCLUDED.is_active,
                            updated_at = CURRENT_TIMESTAMP
                        """,
                        (
                            rec.get("hs_code"),
                            rec.get("description", ""),
                            rec.get("unit", ""),
                            rec.get("is_active", True),
                            rec.get("effective_date", datetime.now().strftime("%Y-%m-%d")),
                            rec.get("notes", "Imported from migration"),
                        ),
                    )
            else:
                args = [
                    (
                        r.get("hs_code"),
                        r.get("description", ""),
                        r.get("unit", ""),
                        r.get("is_active", True),
                        r.get("effective_date", datetime.now().strftime("%Y-%m-%d")),
                        r.get("notes", "Imported from migration"),
                    )
                    for r in records
                ]
                cur.executemany(
                    """
                    INSERT INTO hs_codes (hs_code, description, unit, is_active, effective_date, notes)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (hs_code) DO NOTHING
                    """,
                    args,
                )
        return len(records)

    def bulk_insert_duty_rates(self, records: List[Dict[str, Any]], upsert: bool = True) -> int:
        """Bulk insert duty rates. If upsert=True, updates on conflict."""
        if not records:
            return 0
        with self._cursor(dict_cursor=False) as cur:
            if upsert:
                for rec in records:
                    cur.execute(
                        """
                        INSERT INTO duty_rates (
                            hs_code, description, unit, cd_rate, st_rate, vat_rate,
                            et_rate, atp_rate, origin_country, is_active, effective_date, notes
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        (
                            rec.get("hs_code"),
                            rec.get("description", ""),
                            rec.get("unit", ""),
                            rec.get("cd_rate", 0),
                            rec.get("st_rate", 0),
                            rec.get("vat_rate", 10),
                            rec.get("et_rate", 0),
                            rec.get("atp_rate", 0),
                            rec.get("origin_country", "XX"),
                            rec.get("is_active", True),
                            rec.get("effective_date", datetime.now().strftime("%Y-%m-%d")),
                            rec.get("notes", "Imported from migration"),
                        ),
                    )
            else:
                args = [
                    (
                        r.get("hs_code"),
                        r.get("description", ""),
                        r.get("unit", ""),
                        r.get("cd_rate", 0),
                        r.get("st_rate", 0),
                        r.get("vat_rate", 10),
                        r.get("et_rate", 0),
                        r.get("atp_rate", 0),
                        r.get("origin_country", "XX"),
                        r.get("is_active", True),
                        r.get("effective_date", datetime.now().strftime("%Y-%m-%d")),
                        r.get("notes", "Imported from migration"),
                    )
                    for r in records
                ]
                cur.executemany(
                    """
                    INSERT INTO duty_rates (
                        hs_code, description, unit, cd_rate, st_rate, vat_rate,
                        et_rate, atp_rate, origin_country, is_active, effective_date, notes
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    args,
                )
        return len(records)

    def bulk_insert_exchange_rates(self, records: List[Dict[str, Any]]) -> int:
        """Bulk insert exchange rates with conflict handling."""
        if not records:
            return 0
        with self._cursor(dict_cursor=False) as cur:
            args = [
                (
                    r.get("currency_code"),
                    r.get("currency_name", ""),
                    r.get("usd_rate", 1.0),
                    r.get("khr_rate", 0),
                    r.get("effective_date", datetime.now().strftime("%Y-%m-%d")),
                    r.get("source", "NBC"),
                )
                for r in records
            ]
            cur.executemany(
                """
                INSERT INTO exchange_rates (currency_code, currency_name, usd_rate, khr_rate, effective_date, source)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (currency_code, effective_date) DO UPDATE SET
                    usd_rate = EXCLUDED.usd_rate,
                    khr_rate = EXCLUDED.khr_rate,
                    source = EXCLUDED.source
                """,
                args,
            )
        return len(records)

    def bulk_insert_declared_values(self, records: List[Dict[str, Any]]) -> int:
        """Bulk insert deduction values."""
        if not records:
            return 0
        with self._cursor(dict_cursor=False) as cur:
            args = [
                (
                    r.get("hs_code"),
                    r.get("dv_per_metric_ton", 0),
                    r.get("currency", "USD"),
                    r.get("effective_date", datetime.now().strftime("%Y-%m-%d")),
                    r.get("source", "government"),
                    r.get("is_active", True),
                )
                for r in records
            ]
            cur.executemany(
                """
                INSERT INTO declared_values (hs_code, dv_per_metric_ton, currency, effective_date, source, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (hs_code, effective_date) DO UPDATE SET
                    dv_per_metric_ton = EXCLUDED.dv_per_metric_ton,
                    currency = EXCLUDED.currency,
                    source = EXCLUDED.source
                """,
                args,
            )
        return len(records)
