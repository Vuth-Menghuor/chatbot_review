#!/usr/bin/env python3
"""
Calculator Service - Database Initialization Script (Standalone)
=================================================================
Verifies connectivity to the calculator's primary PostgreSQL database.
Qdrant verification is now OPTIONAL — the calculator is standalone.

Exit codes:
    0 — Calculator DB is up (full functionality)
    1 — No primary data sources available
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables from the calculator service .env file
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)


def verify_calculator_database():
    """Verify connection to the calculator's own PostgreSQL database (PRIMARY)."""
    try:
        import psycopg2
    except ImportError:
        logger.error(" psycopg2 not installed. Run: pip install psycopg2-binary")
        return False

    host = os.getenv("CALCULATOR_DB_HOST", "localhost")
    port = int(os.getenv("CALCULATOR_DB_PORT", "5432"))
    database = os.getenv("CALCULATOR_DB_NAME", "gdce_calculator")
    user = os.getenv("CALCULATOR_DB_USER", "calc_app")
    password = os.getenv("CALCULATOR_DB_PASSWORD", "")

    logger.info(f"Connecting to Calculator DB at {host}:{port} database {database}...")

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            connect_timeout=5,
        )
        cursor = conn.cursor()

        # Verify core tables exist
        cursor.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name IN ('hs_codes', 'duty_rates', 'exchange_rates', 'declared_values')
        """)
        tables = [row[0] for row in cursor.fetchall()]

        # Count records
        cursor.execute("SELECT COUNT(*) FROM duty_rates;")
        duty_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM exchange_rates;")
        exchange_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM hs_codes;")
        hs_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        logger.info(f" Connected to Calculator DB successfully")
        logger.info(f" Core tables: {tables}")
        logger.info(f" duty_rates={duty_count}, exchange_rates={exchange_count}, hs_codes={hs_count}")
        return True

    except psycopg2.OperationalError as e:
        logger.error(f" Cannot connect to Calculator DB: {e}")
        return False
    except Exception as e:
        logger.error(f" Error verifying Calculator DB: {e}")
        return False


def verify_qdrant_connection():
    """Verify Qdrant connectivity (OPTIONAL — only for semantic search)."""
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.warning(" qdrant-client not installed. Semantic search will be unavailable.")
        return False

    qdrant_host = os.getenv("QDRANT_HOST", "172.25.3.243")
    qdrant_port = int(os.getenv("QDRANT_PORT", 6333))

    logger.info(f"Connecting to Qdrant at {qdrant_host}:{qdrant_port} (optional)...")

    try:
        client = QdrantClient(host=qdrant_host, port=qdrant_port)
        collection_name = "gdce_hs_code"
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]

        if collection_name in collection_names:
            logger.info(f" Qdrant connected — collection '{collection_name}' available")
            return True
        else:
            logger.warning(f" Qdrant collection '{collection_name}' not found")
            return False
    except Exception as e:
        logger.warning(f" Qdrant unavailable: {e}")
        return False


def verify_environment_config():
    """Verify environment configuration."""
    logger.info("Verifying environment configuration...")

    # Primary (calculator DB) — required for standalone mode
    primary_vars = [
        ("CALCULATOR_DB_HOST", "localhost"),
        ("CALCULATOR_DB_PORT", "5432"),
        ("CALCULATOR_DB_NAME", "gdce_calculator"),
        ("CALCULATOR_DB_USER", "calc_app"),
    ]
    for var, default in primary_vars:
        value = os.getenv(var, default)
        if value:
            logger.info(f" {var} = {value}")
        else:
            logger.warning(f"  {var} not set (will use default: {default})")

    # Optional vars
    optional_vars = ["QDRANT_HOST", "QDRANT_PORT", "RETRIEVAL_SERVICE_URL"]
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            logger.info(f" {var} = {value}")

    return True


def main():
    """Main initialization routine."""
    logger.info("=" * 60)
    logger.info("Calculator Service - Standalone Database Initialization")
    logger.info("=" * 60)

    verify_environment_config()

    # 1. Verify calculator PostgreSQL (PRIMARY — required)
    calc_db_ok = verify_calculator_database()

    # 2. Verify Qdrant (OPTIONAL — semantic search only)
    qdrant_ok = verify_qdrant_connection()

    # Report status
    if calc_db_ok:
        logger.info("=" * 60)
        logger.info(" Calculator is in STANDALONE mode — all calculations use own DB")
        logger.info("=" * 60)
    else:
        logger.warning("=" * 60)
        logger.warning(" Calculator DB unavailable — will rely on CSV/hardcoded fallbacks")
        logger.warning("=" * 60)

    if not qdrant_ok:
        logger.warning(" Qdrant unavailable — semantic search (/lookup/hs-code-from-product) will fail")

    if not calc_db_ok:
        logger.error(" No primary data source available. Calculator may not function correctly.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(" Calculator database initialization complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
