# PostgreSQL connection pool migrated from the old retrieval service
import os
import logging
from contextlib import contextmanager
from typing import Optional
try:
    import psycopg2
    from psycopg2 import pool
except ImportError:
    raise ImportError("psycopg2 is required. Install it with: pip install psycopg2-binary")
logger = logging.getLogger(__name__)
class PostgreSQLPool:
    def __init__(self, min_connections: int = 1, max_connections: int = 20):
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.pool: Optional[pool.SimpleConnectionPool] = None
        self._initialized = False
    
    def _validate_env_vars(self) -> None:
        required_vars = [
            'DB_HOST',
            'DB_PORT',
            'DB_NAME',
            'DB_USER',
            'DB_PASSWORD'
        ]
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    def _initialize_pool(self) -> None:
        if self._initialized:
            return
        try:
            self._validate_env_vars()
            self.pool = pool.SimpleConnectionPool(
                self.min_connections,
                self.max_connections,
                host=os.getenv('DB_HOST'),
                port=int(os.getenv('DB_PORT')),
                database=os.getenv('DB_NAME'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD')
            )
            self._initialized = True
            logger.info("PostgreSQL connection pool initialized.")
        except Exception as exc:
            logger.error(f"Failed to initialize PostgreSQL pool: {exc}")
            raise
    
    @contextmanager
    def get_connection(self):
        if not self._initialized:
            self._initialize_pool()
        if not self.pool:
            raise RuntimeError("Connection pool is not initialized.")
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

# Lazy initialization: pool is created on first use, not at import time
db_pool = PostgreSQLPool()

def get_db_pool() -> PostgreSQLPool:
    """Get the singleton PostgreSQL pool instance."""
    return db_pool
