"""
PostgreSQL Adapter - Database connectivity
Handles exchange rates, trade data caching, and utility functions
"""

import logging
from typing import Optional, Dict, Any, List
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


class PostgresAdapter:
    """
    PostgreSQL database adapter.
    Manages connections and queries for HS codes, exchange rates, duty rates.
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        connection_timeout: int = 10
    ):
        """
        Initialize PostgreSQL adapter.
        
        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
            connection_timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.connection_timeout = connection_timeout
        self.connection = None
        
        logger.info(f"PostgreSQL Adapter initialized for {host}:{port}/{database}")
    
    def connect(self) -> bool:
        """
        Establish database connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=self.connection_timeout
            )
            logger.info(f"Connected to PostgreSQL: {self.host}:{self.port}/{self.database}")
            return True
        except psycopg2.Error as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            return False
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("PostgreSQL connection closed")
    
    def is_connected(self) -> bool:
        """Check if connected to database."""
        try:
            if not self.connection:
                return False
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return True
        except Exception as e:
            logger.warning(f"Connection check failed: {e}")
            return False
    
    def execute_query(self, query: str, params: Optional[tuple] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Execute SELECT query.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            List of result rows as dictionaries
        """
        try:
            if not self.is_connected():
                self.connect()
            
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                logger.debug(f"Query returned {len(results)} rows")
                return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return None
    
    def execute_update(self, query: str, params: Optional[tuple] = None) -> bool:
        """
        Execute INSERT/UPDATE/DELETE query.
        
        Args:
            query: SQL query
            params: Query parameters
            
        Returns:
            True if successful
        """
        try:
            if not self.is_connected():
                self.connect()
            
            with self.connection.cursor() as cursor:
                cursor.execute(query, params)
                self.connection.commit()
                logger.debug(f"Update executed: {cursor.rowcount} rows affected")
                return True
        except Exception as e:
            self.connection.rollback()
            logger.error(f"Update failed: {e}")
            return False
    
    def get_exchange_rate(self, from_currency: str = "USD", to_currency: str = "KHR") -> Optional[float]:
        """
        Get exchange rate from database or return fallback default rates.
        
        Args:
            from_currency: Source currency (default: USD)
            to_currency: Target currency (default: KHR)
            
        Returns:
            Exchange rate or None
        """
        # Default exchange rates to KHR (as of April 2026)
        # These are fallback rates used when database lookup fails
        default_rates = {
            ("USD", "KHR"): 4022,
            ("CNY", "KHR"): 560,
            ("SGD", "KHR"): 3000,
            ("THB", "KHR"): 110,
            ("MYR", "KHR"): 880,
            ("VND", "KHR"): 0.16,
            ("JPY", "KHR"): 27,
            ("KRW", "KHR"): 3.1,
            ("EUR", "KHR"): 4500,
            ("GBP", "KHR"): 5100,
            ("IDR", "KHR"): 0.26,
            ("PHP", "KHR"): 70,
            ("INR", "KHR"): 48,
            ("CAD", "KHR"): 3000,
            ("AUD", "KHR"): 2700,
            ("HKD", "KHR"): 520,
            ("TWD", "KHR"): 130,
            ("BDT", "KHR"): 38,
            ("PKR", "KHR"): 13,
            ("LKR", "KHR"): 12,
            ("LAK", "KHR"): 0.18,
            ("MMK", "KHR"): 1.9,
            ("SAR", "KHR"): 1073,
            ("AED", "KHR"): 1095,
            ("QAR", "KHR"): 1105,
            ("KWD", "KHR"): 13085,
            ("BHD", "KHR"): 10680,
            ("OMR", "KHR"): 10450,
            ("CHF", "KHR"): 4550,
            ("SEK", "KHR"): 385,
            ("NOK", "KHR"): 380,
            ("DKK", "KHR"): 605,
            ("PLN", "KHR"): 1010,
            ("CZK", "KHR"): 175,
            ("HUF", "KHR"): 11.5,
            ("RON", "KHR"): 855,
            ("RUB", "KHR"): 42,
            ("UAH", "KHR"): 98,
            ("BRL", "KHR"): 815,
            ("MXN", "KHR"): 235,
            ("ARS", "KHR"): 4.3,
            ("CLP", "KHR"): 4.8,
            ("EGP", "KHR"): 82,
            ("ZAR", "KHR"): 215,
            ("NGN", "KHR"): 2.6,
            ("ETB", "KHR"): 78,
            ("KES", "KHR"): 31,
            ("NZD", "KHR"): 2450,
        }
        
        try:
            # Try to get from database first
            query = """
                SELECT rate, updated_at
                FROM exchange_rates
                WHERE from_currency = %s AND to_currency = %s
                ORDER BY updated_at DESC
                LIMIT 1
            """
            results = self.execute_query(query, (from_currency, to_currency))
            
            if results:
                rate = float(results[0].get('rate', 0))
                logger.info(f"Exchange rate {from_currency}/{to_currency}: {rate} (from database)")
                return rate
            else:
                # Fall back to hardcoded default rates
                key = (from_currency, to_currency)
                if key in default_rates:
                    rate = default_rates[key]
                    logger.info(f"Exchange rate {from_currency}/{to_currency}: {rate} (using default fallback)")
                    return rate
                else:
                    logger.warning(f"Exchange rate not found for {from_currency}/{to_currency}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching exchange rate: {e}")
            # Fall back to hardcoded rates on error
            key = (from_currency, to_currency)
            if key in default_rates:
                rate = default_rates[key]
                logger.info(f"Exchange rate {from_currency}/{to_currency}: {rate} (using default fallback due to error)")
                return rate
            return None
    
    def cache_exchange_rate(self, from_currency: str, to_currency: str, rate: float) -> bool:
        """
        Cache exchange rate.
        
        Args:
            from_currency: Source currency
            to_currency: Target currency
            rate: Exchange rate value
            
        Returns:
            True if successful
        """
        try:
            query = """
                INSERT INTO exchange_rates (from_currency, to_currency, rate, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (from_currency, to_currency) 
                DO UPDATE SET rate = EXCLUDED.rate, updated_at = EXCLUDED.updated_at
            """
            return self.execute_update(query, (from_currency, to_currency, rate, datetime.utcnow()))
        except Exception as e:
            logger.error(f"Error caching exchange rate: {e}")
            return False
    
    def get_hs_code_data(self, hs_code: str) -> Optional[Dict[str, Any]]:
        """
        Get HS code data (duty rates, descriptions).
        
        Args:
            hs_code: HS code
            
        Returns:
            HS code data dictionary
        """
        try:
            query = """
                SELECT code, description, duty_rate, vat_rate, special_tax_rate
                FROM hs_codes
                WHERE code = %s
                LIMIT 1
            """
            results = self.execute_query(query, (hs_code,))
            
            if results:
                logger.debug(f"Found HS code data for {hs_code}")
                return results[0]
            else:
                logger.debug(f"HS code {hs_code} not found")
                return None
        except Exception as e:
            logger.error(f"Error fetching HS code data: {e}")
            return None
    
    def get_duty_rates(self, hs_code: str, origin_country: Optional[str] = None) -> Optional[Dict[str, float]]:
        """
        Get duty rates for HS code.
        
        Args:
            hs_code: HS code
            origin_country: Optional origin country code
            
        Returns:
            Dictionary with duty rates
        """
        try:
            if origin_country:
                query = """
                    SELECT duty_rate, vat_rate, special_tax_rate, excise_tax_rate
                    FROM duty_rates
                    WHERE hs_code = %s AND origin_country = %s
                    LIMIT 1
                """
                results = self.execute_query(query, (hs_code, origin_country))
            else:
                query = """
                    SELECT duty_rate, vat_rate, special_tax_rate, excise_tax_rate
                    FROM duty_rates
                    WHERE hs_code = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                """
                results = self.execute_query(query, (hs_code,))
            
            if results:
                row = results[0]
                rates = {
                    "duty_rate": float(row.get('duty_rate', 0)),
                    "vat_rate": float(row.get('vat_rate', 0)),
                    "special_tax_rate": float(row.get('special_tax_rate', 0)),
                    "excise_tax_rate": float(row.get('excise_tax_rate', 0)),
                }
                logger.debug(f"Duty rates for {hs_code}: {rates}")
                return rates
            else:
                logger.debug(f"Duty rates not found for {hs_code}")
                return None
        except Exception as e:
            logger.error(f"Error fetching duty rates: {e}")
            return None


# Global adapter instance
_adapter: Optional[PostgresAdapter] = None


def get_postgres_adapter() -> Optional[PostgresAdapter]:
    """Get or create PostgreSQL adapter from environment variables."""
    global _adapter
    
    if _adapter is None:
        try:
            _adapter = PostgresAdapter(
                host=os.getenv("PG_HOST", "localhost"),
                port=int(os.getenv("PG_PORT", "5432")),
                database=os.getenv("PG_DATABASE", "gdce_hs_code"),
                user=os.getenv("PG_USER", "postgres"),
                password=os.getenv("PG_PASSWORD", ""),
            )
            _adapter.connect()
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL adapter: {e}")
            return None
    
    return _adapter
