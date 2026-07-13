"""
exchange_rate_fetcher.py

Daily job: fetches exchange rates from data.mef.gov.kh (National Bank of Cambodia)
and stores them in Redis so the Calculator service can read them directly.

Usage:
    python calculator/exchange_rate_fetcher.py

Run once daily via cron / Task Scheduler.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date, datetime
from decimal import Decimal

import requests
import urllib3

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Load .env if present ──────────────────────────────────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(_script_dir, ".env")
if os.path.isfile(_env_path):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        with open(_env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

# ── Configuration ─────────────────────────────────────────────

BASE_URL = "https://data.mef.gov.kh/api/v1/realtime-api/exchange-rate"

# SSL: default True. Set MEF_VERIFY_SSL=false to disable (dev only).
VERIFY_SSL = os.getenv("MEF_VERIFY_SSL", "true").lower() != "false"
if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Redis connection
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Rate TTL in seconds (default: 48 hours)
RATE_TTL_SECONDS = int(os.getenv("RATE_TTL_SECONDS", "172800"))

CURRENCIES = [
    "USD", "THB", "EUR", "GBP", "AUD", "CAD", "CHF", "CNY", "CNH",
    "HKD", "IDR", "INR", "JPY", "KRW", "LAK", "MMK", "MYR", "NZD",
]

REQUEST_DELAY_SECONDS = 0.5

# ── Redis helpers ────────────────────────────────────────────

def _get_redis_client():
    """Connect to Redis."""
    try:
        import redis
    except ImportError:
        logger.error("redis package not installed. Run: pip install redis")
        sys.exit(1)

    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        client.ping()
        logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)


# ── API fetching ────────────────────────────────────────────────

def fetch_one(currency: str, for_date: str = None) -> dict:
    """
    Fetch a single currency's rate from the MEF API.
    """
    if currency == "KHR":
        return {
            "valid_date": (for_date or date.today().isoformat()),
            "currency_id": "KHR",
            "bid": 1.0,
            "ask": 1.0,
            "average": 1.0,
        }

    params: dict[str, str] = {"currency_id": currency}
    if for_date:
        params["date"] = for_date

    resp = requests.get(BASE_URL, params=params, timeout=15, verify=VERIFY_SSL)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data")
    if not data:
        raise ValueError(f"Empty API response for {currency}: {payload}")
    return data


def _store_rate(redis_client, currency: str, data: dict) -> None:
    """Store a rate in Redis with TTL."""
    avg = data.get("average")
    if avg is None:
        raise ValueError(f"No 'average' rate in API response for {currency}")

    rate = float(avg)
    effective_date = data["valid_date"]
    fetched_at = datetime.now().isoformat()

    # Store as JSON for flexibility
    value = json.dumps({
        "rate": rate,
        "bid": float(data.get("bid", avg)),
        "ask": float(data.get("ask", avg)),
        "date": effective_date,
        "fetched_at": fetched_at,
    })

    # Primary key: exchange_rate:{currency} (latest)
    redis_client.setex(f"exchange_rate:{currency}", RATE_TTL_SECONDS, value)

    # Also store by date for historical lookup
    redis_client.setex(
        f"exchange_rate:{currency}:{effective_date}",
        RATE_TTL_SECONDS,
        value,
    )

    logger.info(f"Stored {currency} @ {rate} KHR in Redis (TTL {RATE_TTL_SECONDS}s)")


def fetch_and_store_all() -> None:
    """Loop through all configured currencies and store in Redis."""
    redis_client = _get_redis_client()

    stored, failed = [], []

    for currency in CURRENCIES:
        try:
            data = fetch_one(currency)
            _store_rate(redis_client, currency, data)
            stored.append((currency, data.get("average")))
        except Exception as e:
            failed.append((currency, str(e)))
            logger.warning(f"Failed to fetch/store {currency}: {e}")
        time.sleep(REQUEST_DELAY_SECONDS)

    # Always ensure KHR is present (1 KHR = 1 KHR)
    try:
        data = fetch_one("KHR")
        _store_rate(redis_client, "KHR", data)
        stored.append(("KHR", 1.0))
    except Exception as e:
        failed.append(("KHR", str(e)))
        logger.warning(f"Failed to store KHR: {e}")

    # Store metadata
    redis_client.setex(
        "exchange_rate:last_updated",
        RATE_TTL_SECONDS,
        datetime.now().isoformat(),
    )
    redis_client.setex(
        "exchange_rate:currencies",
        RATE_TTL_SECONDS,
        json.dumps([c for c, _ in stored]),
    )

    _print_summary(stored, failed)


def _print_summary(stored: list, failed: list) -> None:
    print(f"\n[{datetime.now()}] Run complete.")
    if stored:
        print(f"  Stored in Redis ({len(stored)}):")
        for currency, rate in stored:
            print(f"    {currency}: {rate}")
    if failed:
        print(f"  Failed ({len(failed)}):")
        for currency, err in failed:
            print(f"    {currency}: {err}")


# ── Chatbot-facing lookup (reads from Redis) ───────────────────

def get_exchange_rate(currency: str, for_date: str = None) -> dict | None:
    """
    Read a rate from Redis.

    Returns a dict like:
        {"date": "2026-07-09", "currency": "USD", "rate": 4036.0,
         "bid": 4036.0, "ask": 4036.0, "is_fallback": False}
    or None if no data exists.
    """
    try:
        import redis
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=5,
        )
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return None

    currency = currency.upper()
    target = for_date or date.today().isoformat()

    # Try exact date first
    raw = client.get(f"exchange_rate:{currency}:{target}")
    is_fallback = False

    if not raw:
        # Fallback to latest
        raw = client.get(f"exchange_rate:{currency}")
        is_fallback = True

    if not raw:
        return None

    data = json.loads(raw)
    return {
        "date": data.get("date", target),
        "currency": currency,
        "rate": data["rate"],
        "bid": data.get("bid", data["rate"]),
        "ask": data.get("ask", data["rate"]),
        "is_fallback": is_fallback,
    }


# ── Scheduler loop ───────────────────────────────────────────

def run_scheduler(interval_hours: float = 24.0) -> None:
    """
    Run the fetcher in an infinite loop, sleeping between intervals.

    Args:
        interval_hours: How many hours to wait between fetches.
    """
    interval_seconds = interval_hours * 3600
    logger.info(
        f"Starting exchange rate scheduler. "
        f"Fetching every {interval_hours} hour(s)."
    )
    while True:
        try:
            fetch_and_store_all()
        except Exception as e:
            logger.error(f"Scheduled fetch failed: {e}")
        logger.info(f"Sleeping for {interval_hours} hour(s)...")
        time.sleep(interval_seconds)


# ── Entry point ──────────────────────────────────────────────

if __name__ == "__main__":
    interval = os.getenv("FETCH_INTERVAL_HOURS")
    if interval:
        run_scheduler(float(interval))
    else:
        fetch_and_store_all()
        print("\nSample lookup — USD today:", get_exchange_rate("USD"))
        print("Sample lookup — KHR today:", get_exchange_rate("KHR"))
