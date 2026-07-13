"""
GDCE Calculator Service - Redis Exchange Rate Client
=====================================================
Reads exchange rates from Redis (written by exchange_rate_fetcher.py).

Usage:
    from app.data.redis_exchange_rate_client import RedisExchangeRateClient
    client = RedisExchangeRateClient()
    rate = client.get_exchange_rate("USD")
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)


class RedisExchangeRateClient:
    """Client for reading exchange rates from Redis."""

    def __init__(
        self,
        host: str = None,
        port: int = None,
        db: int = None,
        password: str = None,
    ):
        """
        Initialize Redis connection.

        Uses REDIS_* environment variables first, then defaults.
        """
        self.host = host or os.getenv("REDIS_HOST", "localhost")
        self.port = port or int(os.getenv("REDIS_PORT", "6379"))
        self.db = db if db is not None else int(os.getenv("REDIS_DB", "0"))
        self.password = password or os.getenv("REDIS_PASSWORD") or None
        self._client = None
        self._connect()

    def _connect(self) -> None:
        """Establish connection to Redis."""
        try:
            import redis
            self._client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            self._client.ping()
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
        except ImportError:
            logger.error("redis package not installed. Run: pip install redis")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def get_exchange_rate(
        self,
        currency_code: str,
        effective_date: str = None,
    ) -> Optional[Decimal]:
        """
        Get exchange rate to KHR for given currency.

        Args:
            currency_code: Currency code (e.g., 'USD', 'THB')
            effective_date: Optional date string (YYYY-MM-DD). If None, returns latest.

        Returns:
            Exchange rate as Decimal (e.g., 4036.0 for USD->KHR)
        """
        if not self._client:
            logger.warning("Redis client not available")
            return None

        if currency_code.upper() == "KHR":
            return Decimal("1.0")

        try:
            currency = currency_code.upper()

            # Try exact date first
            if effective_date:
                raw = self._client.get(f"exchange_rate:{currency}:{effective_date}")
                if raw:
                    data = json.loads(raw)
                    rate = Decimal(str(data["rate"]))
                    logger.debug(f"Redis rate {currency}->{rate} KHR (date={effective_date})")
                    return rate

            # Fallback to latest
            raw = self._client.get(f"exchange_rate:{currency}")
            if raw:
                data = json.loads(raw)
                rate = Decimal(str(data["rate"]))
                logger.debug(f"Redis rate {currency}->{rate} KHR (latest)")
                return rate

            logger.warning(f"No exchange rate found in Redis for {currency}")
            return None

        except Exception as e:
            logger.error(f"Error reading exchange rate from Redis: {e}")
            return None

    def get_all_exchange_rates(self) -> Optional[dict[str, Decimal]]:
        """Get all latest exchange rates from Redis."""
        if not self._client:
            return None

        try:
            currencies_raw = self._client.get("exchange_rate:currencies")
            if not currencies_raw:
                return None

            currencies = json.loads(currencies_raw)
            rates = {}
            for currency in currencies:
                raw = self._client.get(f"exchange_rate:{currency}")
                if raw:
                    data = json.loads(raw)
                    rates[currency] = Decimal(str(data["rate"]))
            return rates
        except Exception as e:
            logger.error(f"Error reading all rates from Redis: {e}")
            return None

    def check_health(self) -> dict:
        """Check Redis connection health."""
        try:
            if self._client:
                self._client.ping()
                info = self._client.get("exchange_rate:last_updated")
                return {
                    "ok": True,
                    "server": f"{self.host}:{self.port}",
                    "last_updated": info,
                    "message": "Connected",
                }
            return {"ok": False, "message": "Connection not initialized"}
        except Exception as e:
            return {"ok": False, "message": str(e)}
