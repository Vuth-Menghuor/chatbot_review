#!/usr/bin/env python3
"""
Calculator Service - Database Initialization Script
Verifies Qdrant database connectivity for duty rate lookups
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


def verify_qdrant_connection():
    """Verify Qdrant database connectivity"""
    
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        logger.error(" qdrant-client not installed. Run: pip install qdrant-client")
        return False
    
    qdrant_host = os.getenv("QDRANT_HOST", "172.25.3.243")
    qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
    
    logger.info(f"Connecting to Qdrant at {qdrant_host}:{qdrant_port}...")
    
    try:
        client = QdrantClient(host=qdrant_host, port=qdrant_port)
        
        # Check collection exists
        collection_name = "gdce_hs_code"
        collections = client.get_collections()
        collection_names = [c.name for c in collections.collections]
        
        if collection_name in collection_names:
            logger.info(f" Connected to Qdrant successfully")
            logger.info(f" Collection '{collection_name}' exists")
            
            # Try to get point count via raw API call (simpler than .get_collection())
            try:
                import requests
                response = requests.get(f"http://{qdrant_host}:{qdrant_port}/collections/{collection_name}/points/count")
                if response.status_code == 200:
                    data = response.json()
                    if 'result' in data and 'count' in data['result']:
                        count = data['result']['count']
                        logger.info(f" Collection has {count} duty rate records")
            except Exception:
                # If raw API call fails, just continue - collection exists
                logger.info(f" Collection is accessible")
            
            return True
        else:
            logger.error(f" Collection '{collection_name}' not found in Qdrant")
            logger.error(f"   Available collections: {collection_names}")
            return False
            
    except ConnectionError as e:
        logger.error(f" Cannot connect to Qdrant: {e}")
        logger.error(f"   Please ensure Qdrant is running at {qdrant_host}:{qdrant_port}")
        logger.error(f"   Or update QDRANT_HOST and QDRANT_PORT in .env")
        return False
    except Exception as e:
        logger.error(f" Error verifying Qdrant: {e}")
        return False


def verify_postgresql_connection():
    """Verify PostgreSQL connection for exchange rates"""
    
    try:
        import psycopg2
    except ImportError:
        logger.error(" psycopg2 not installed. Run: pip install psycopg2-binary")
        return False
    
    pg_host = os.getenv("PG_HOST", "172.25.3.243")
    pg_port = int(os.getenv("PG_PORT", 5432))
    pg_database = os.getenv("PG_DATABASE", "gdce_hs_code")
    pg_user = os.getenv("PG_USER", "postgres")
    pg_password = os.getenv("PG_PASSWORD", "postgres")
    
    logger.info(f"Connecting to PostgreSQL at {pg_host}:{pg_port} database {pg_database}...")
    
    try:
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            database=pg_database,
            user=pg_user,
            password=pg_password
        )
        
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM exchange_rates;")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        logger.info(f" Connected to PostgreSQL successfully")
        logger.info(f" Table 'exchange_rates' accessible with {count} rate records")
        return True
        
    except psycopg2.OperationalError as e:
        logger.error(f" Cannot connect to PostgreSQL: {e}")
        logger.error(f"   Please ensure PostgreSQL is running at {pg_host}:{pg_port}")
        return False
    except Exception as e:
        logger.error(f" Error verifying PostgreSQL: {e}")
        return False


def verify_environment_config():
    """Verify environment configuration"""
    
    logger.info("Verifying environment configuration...")
    
    required_vars = [
        "QDRANT_HOST",
        "QDRANT_PORT",
        "PG_HOST",
        "PG_PORT",
        "PG_DATABASE",
        "PG_USER",
    ]
    
    missing = []
    for var in required_vars:
        value = os.getenv(var)
        if value:
            logger.info(f" {var} = {value}")
        else:
            logger.warning(f"  {var} not set (will use default)")
            
optional_vars = [
    "USD_TO_KHR_RATE_FALLBACK",
    "EXCHANGE_RATE_CACHE_TTL",
]

for var in optional_vars:
    value = os.getenv(var)
    if value:
        logger.info(f" {var} = {value}")
    
    if missing:
        logger.error(f" Missing environment variables: {', '.join(missing)}")
        logger.error("   Update your .env file with:")
        logger.error("   QDRANT_HOST=172.25.3.243")
        logger.error("   QDRANT_PORT=6333")
        return False
    
    return True


def main():
    """Main initialization routine"""
    
    logger.info("=" * 60)
    logger.info("Calculator Service - Database Initialization")
    logger.info("=" * 60)
    
    # Verify environment config
    if not verify_environment_config():
        logger.warning("  Environment configuration incomplete (using defaults)")
    
    # Verify Qdrant connection (primary for duty rates)
    qdrant_ok = verify_qdrant_connection()
    
    # Verify PostgreSQL connection (primary for exchange rates)
    postgres_ok = verify_postgresql_connection()
    
    # Report status
    if not qdrant_ok:
        logger.warning("  Qdrant unavailable - will use CSV fallback for duty rates")
    
    if not postgres_ok:
        logger.warning("  PostgreSQL unavailable - will use fallback for exchange rates")
    
    if not (qdrant_ok or postgres_ok):
        logger.error(" No primary data sources available")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info(" Calculator database initialization complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
