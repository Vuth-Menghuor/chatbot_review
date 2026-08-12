#!/usr/bin/env python3
"""
Migration: Seed all 29 NBC exchange rates into PostgreSQL and Redis.
Run this after updating the currency_handler SUPPORTED_CURRENCIES.

Usage: python scripts/migrate_exchange_rates.py
"""

import json
import logging
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Load .env from calculator folder
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ── NBC Exchange Rates (2026-07-31, per unit in KHR) ─────────
# Source: user-provided National Bank of Cambodia rate table
RATES = {
    "USD": {"name": "United States Dollar",     "rate": Decimal("4043.0000"),    "usd_per_unit": Decimal("1.0000")},
    "AUD": {"name": "Australian Dollar",        "rate": Decimal("2826.0000"),    "usd_per_unit": Decimal("1.4306")},
    "CAD": {"name": "Canadian Dollar",          "rate": Decimal("2889.5000"),    "usd_per_unit": Decimal("1.3992")},
    "CNY": {"name": "China Yuan Renminbi",      "rate": Decimal("601.0000"),     "usd_per_unit": Decimal("6.7271")},
    "CNH": {"name": "China in Hong Kong",       "rate": Decimal("601.0000"),     "usd_per_unit": Decimal("6.7271")},
    "GBP": {"name": "Pound Sterling",           "rate": Decimal("5424.0000"),    "usd_per_unit": Decimal("0.7454")},
    "EUR": {"name": "Euro",                     "rate": Decimal("4651.0000"),    "usd_per_unit": Decimal("0.8693")},
    "HKD": {"name": "Hong Kong Dollar",         "rate": Decimal("518.0000"),     "usd_per_unit": Decimal("7.8050")},
    "INR": {"name": "Indian Rupee",             "rate": Decimal("42.4500"),     "usd_per_unit": Decimal("95.2415")},
    "IDR": {"name": "Indonesian Rupee",         "rate": Decimal("0.2250"),      "usd_per_unit": Decimal("17968.8889")},
    "JPY": {"name": "Japanese Yen",             "rate": Decimal("24.8300"),     "usd_per_unit": Decimal("162.8272")},
    "LAK": {"name": "Laotian Kip",              "rate": Decimal("0.1800"),      "usd_per_unit": Decimal("22461.1111")},
    "MMK": {"name": "Myanmar Kyat",             "rate": Decimal("1.9400"),      "usd_per_unit": Decimal("2084.0206")},
    "MYR": {"name": "Malaysian Ringgit",        "rate": Decimal("993.0000"),     "usd_per_unit": Decimal("4.0715")},
    "NZD": {"name": "New Zealand Dollar",       "rate": Decimal("2362.0000"),    "usd_per_unit": Decimal("1.7117")},
    "PHP": {"name": "Philippine Peso",          "rate": Decimal("66.0150"),     "usd_per_unit": Decimal("61.2437")},
    "SGD": {"name": "Singapore Dollar",         "rate": Decimal("3147.5000"),   "usd_per_unit": Decimal("1.2845")},
    "KRW": {"name": "South Korean Won",         "rate": Decimal("2.8250"),      "usd_per_unit": Decimal("1431.1504")},
    "SDR": {"name": "Special Drawing Right",    "rate": Decimal("5508.5000"),   "usd_per_unit": Decimal("0.7340")},
    "SEK": {"name": "Swedish Krona",            "rate": Decimal("421.0000"),     "usd_per_unit": Decimal("9.6033")},
    "CHF": {"name": "Swiss Franc",              "rate": Decimal("4978.0000"),    "usd_per_unit": Decimal("0.8122")},
    "TWD": {"name": "Taiwan Dollar",            "rate": Decimal("125.5000"),     "usd_per_unit": Decimal("32.2151")},
    "THB": {"name": "Thailand Baht",            "rate": Decimal("120.5000"),     "usd_per_unit": Decimal("33.5519")},
    "VND": {"name": "Vietnam Dong",             "rate": Decimal("0.1545"),      "usd_per_unit": Decimal("26168.2848")},
    "AED": {"name": "UAE Dirham",               "rate": Decimal("1106.5000"),   "usd_per_unit": Decimal("3.6539")},
    "ZAR": {"name": "South Africa Rand",        "rate": Decimal("244.0000"),     "usd_per_unit": Decimal("16.5697")},
    "NGN": {"name": "Nigeria Naira",            "rate": Decimal("2.9850"),      "usd_per_unit": Decimal("1354.4389")},
    "DKK": {"name": "Danish Krone",             "rate": Decimal("622.0000"),     "usd_per_unit": Decimal("6.5000")},
    "SAR": {"name": "Saudi Riyal",              "rate": Decimal("1082.5000"),   "usd_per_unit": Decimal("3.7349")},
    "KHR": {"name": "Cambodian Riel",           "rate": Decimal("1.0000"),      "usd_per_unit": Decimal("4043.0000")},
}

DB_CONFIG = {
    "host": os.getenv("CALCULATOR_DB_HOST", "localhost"),
    "port": int(os.getenv("CALCULATOR_DB_PORT", "5432")),
    "database": os.getenv("CALCULATOR_DB_NAME", "gdce_calculator_local"),
    "user": os.getenv("CALCULATOR_DB_USER", "postgres"),
    "password": os.getenv("CALCULATOR_DB_PASSWORD", ""),
}

REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", "6379")),
    "db": int(os.getenv("REDIS_DB", "0")),
    "password": os.getenv("REDIS_PASSWORD") or None,
}


def _connect_db():
    import psycopg2
    return psycopg2.connect(**DB_CONFIG)


def _connect_redis():
    import redis
    client = redis.Redis(
        host=REDIS_CONFIG["host"],
        port=REDIS_CONFIG["port"],
        db=REDIS_CONFIG["db"],
        password=REDIS_CONFIG["password"],
        decode_responses=True,
        socket_connect_timeout=5,
    )
    client.ping()
    return client


def migrate_database():
    """Clear old exchange_rates and insert all 29 NBC rates."""
    conn = _connect_db()
    cur = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")

    # Clear existing rates (optional: keep history, but for clean seed we truncate)
    cur.execute("TRUNCATE TABLE exchange_rates RESTART IDENTITY;")
    logger.info("Cleared old exchange_rates")

    for code, info in RATES.items():
        cur.execute(
            """
            INSERT INTO exchange_rates (currency, usd_unit, foreign_rate, foreign_unit, local_rate, effective_date, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """,
            (
                code,
                f"1{code}",
                float(info["usd_per_unit"]),
                code,
                float(info["rate"]),
                today,
            ),
        )
        logger.info(f"  Inserted {code}: {info['rate']} KHR")

    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Database updated: {len(RATES)} currencies")


def migrate_redis():
    """Store all 29 NBC rates in Redis."""
    client = _connect_redis()
    today = datetime.now().strftime("%Y-%m-%d")
    fetched_at = datetime.now().isoformat()

    ttl = 48 * 3600  # 48 hours

    currencies = []
    for code, info in RATES.items():
        rate = float(info["rate"])
        value = json.dumps({
            "rate": rate,
            "bid": rate,
            "ask": rate,
            "date": today,
            "fetched_at": fetched_at,
        })

        client.setex(f"exchange_rate:{code}", ttl, value)
        client.setex(f"exchange_rate:{code}:{today}", ttl, value)
        currencies.append(code)
        logger.info(f"  Redis stored {code}: {rate} KHR")

    # Metadata
    client.setex("exchange_rate:last_updated", ttl, fetched_at)
    client.setex("exchange_rate:currencies", ttl, json.dumps(currencies))

    logger.info(f"Redis updated: {len(currencies)} currencies")


def main():
    logger.info("=" * 60)
    logger.info("Migrating NBC Exchange Rates (29 currencies)")
    logger.info("=" * 60)

    logger.info("\n[1/2] Updating PostgreSQL...")
    migrate_database()

    logger.info("\n[2/2] Updating Redis...")
    migrate_redis()

    logger.info("\n" + "=" * 60)
    logger.info("Migration complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
