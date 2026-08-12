"""
GDCE Calculator Service - PostgreSQL Exchange Rate Adapter
===========================================================
Infrastructure adapter: connects to the calculator's own PostgreSQL
to retrieve exchange rates from database gdce_calculator, table exchange_rates.

Table Structure:
CREATE TABLE exchange_rates (
    id SERIAL PRIMARY KEY,
    currency TEXT,
    usd_unit TEXT DEFAULT '1USD',
    foreign_rate NUMERIC(15, 4),
    foreign_unit TEXT,
    local_rate NUMERIC(15, 4),      -- e.g., 4022.0 for USD->KHR
    effective_date DATE,
    created_at TIMESTAMP
);

Example: 1 USD = 4022 KHR
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class PostgreSQLExchangeRateAdapter:
    """Adapter for querying PostgreSQL exchange rates."""

    def __init__(self, 
                 host: str = None,
                 port: int = None, 
                 database: str = None,
                 user: str = None, 
                 password: str = None):
        """
        Initialize PostgreSQL connection.

        Uses CALCULATOR_DB_* environment variables first, then falls back
        to POSTGRES_* for backward compatibility.
        """
        self.host = host or os.getenv("CALCULATOR_DB_HOST") or os.getenv("POSTGRES_HOST", "localhost")
        self.port = port or int(os.getenv("CALCULATOR_DB_PORT") or os.getenv("POSTGRES_PORT", "5432"))
        self.database = database or os.getenv("CALCULATOR_DB_NAME") or os.getenv("POSTGRES_DB", "gdce_calculator")
        self.user = user or os.getenv("CALCULATOR_DB_USER") or os.getenv("POSTGRES_USER", "postgres")
        self.password = password or os.getenv("CALCULATOR_DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD", "postgres")
        self.table_name = os.getenv("POSTGRES_EXCHANGE_RATES_TABLE", "exchange_rates")
        self.conn = None
        self._exchange_rate_cache = {}
        self._connect()

    def _connect(self) -> None:
        """Establish connection to PostgreSQL."""
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            self.psycopg2 = psycopg2
            self.RealDictCursor = RealDictCursor
            
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=5,
            )
            logger.info(f" Connected to PostgreSQL at {self.host}:{self.port} database {self.database}")
        except ImportError:
            logger.error(" psycopg2 not installed. Run: pip install psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f" Failed to connect to PostgreSQL: {e}")
            raise

    def get_exchange_rate(self, currency_code: str, effective_date: str = None) -> Optional[Decimal]:
        """
        Get exchange rate to KHR for given currency.
        
        Query strategy:
        1. If effective_date provided: get rate for that date
        2. Otherwise: get latest available rate
        
        Args:
            currency_code: Currency code (e.g., 'USD', 'EUR', 'THB')
            effective_date: Date for rate lookup (format: YYYY-MM-DD, default: today)
            
        Returns:
            Exchange rate as Decimal (e.g., 4022.0 for USD->KHR)
        """
        if not self.conn:
            logger.warning("PostgreSQL connection not available")
            return None

        try:
            # Check cache first
            cache_key = f"{currency_code}:{effective_date}"
            if cache_key in self._exchange_rate_cache:
                return self._exchange_rate_cache[cache_key]

            cursor = self.conn.cursor(cursor_factory=self.RealDictCursor)

            # Query: Get rate for currency, with optional date filter
            if effective_date:
                query = f"""
                    SELECT local_rate
                    FROM {self.table_name}
                    WHERE currency = %s
                    AND effective_date <= %s
                    ORDER BY effective_date DESC
                    LIMIT 1;
                """
                cursor.execute(query, (currency_code, effective_date))
            else:
                query = f"""
                    SELECT local_rate
                    FROM {self.table_name}
                    WHERE currency = %s
                    ORDER BY effective_date DESC
                    LIMIT 1;
                """
                cursor.execute(query, (currency_code,))

            row = cursor.fetchone()
            cursor.close()

            if row:
                rate = Decimal(str(row['local_rate']))
                self._exchange_rate_cache[cache_key] = rate
                logger.debug(f"Exchange rate {currency_code}->KHR: {rate}")
                return rate
            
            logger.warning(f"No exchange rate found for {currency_code}")
            return None

        except Exception as e:
            logger.error(f"Error querying exchange rate for {currency_code}: {e}")
            return None

    def get_all_exchange_rates(self, effective_date: str = None) -> Optional[Dict[str, Decimal]]:
        """Get all exchange rates for a given date."""
        if not self.conn:
            return None

        try:
            cursor = self.conn.cursor(cursor_factory=self.RealDictCursor)
            
            if effective_date:
                query = f"""
                    SELECT currency, local_rate
                    FROM {self.table_name}
                    WHERE effective_date = %s;
                """
                cursor.execute(query, (effective_date,))
            else:
                query = f"""
                    SELECT DISTINCT currency, local_rate
                    FROM {self.table_name}
                    WHERE effective_date = (SELECT MAX(effective_date) FROM {self.table_name});
                """
                cursor.execute(query)

            rows = cursor.fetchall()
            cursor.close()

            rates = {row['currency']: Decimal(str(row['local_rate'])) for row in rows}
            return rates

        except Exception as e:
            logger.error(f"Error querying all exchange rates: {e}")
            return None

    def check_health(self) -> Dict[str, Any]:
        """Check PostgreSQL connection health."""
        try:
            if self.conn:
                cursor = self.conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {self.table_name};")
                count = cursor.fetchone()[0]
                cursor.close()
                return {
                    "ok": True,
                    "server": f"{self.host}:{self.port}",
                    "database": self.database,
                    "table": self.table_name,
                    "record_count": count,
                    "message": "Connected"
                }
            return {"ok": False, "message": "Connection not initialized"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def close(self) -> None:
        """Close PostgreSQL connection."""
        if self.conn:
            self.conn.close()
            logger.info("PostgreSQL connection closed")
