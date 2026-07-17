import os
import logging
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

logger = logging.getLogger(__name__)

Base = declarative_base()

# Retrieve credentials
pg_host = os.getenv("POSTGRES_HOST") or os.getenv("PG_HOST", "127.0.0.1")
pg_port = int(os.getenv("POSTGRES_PORT") or os.getenv("PG_PORT", 5433))
pg_database = os.getenv("POSTGRES_DB") or os.getenv("PG_DATABASE", "chatbot_main_db")
pg_user = os.getenv("POSTGRES_USER") or os.getenv("PG_USER", "postgres")
pg_password = os.getenv("POSTGRES_PASSWORD") or os.getenv("PG_PASSWORD", "postgres")
pg_pool_size = int(os.getenv("DB_POOL_SIZE", 10))
pg_max_overflow = int(os.getenv("DB_MAX_OVERFLOW", 20))

DATABASE_URL = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"

engine = create_engine(
    DATABASE_URL,
    pool_size=pg_pool_size,
    max_overflow=pg_max_overflow,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI request-scoped dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """Context manager for detached background tasks (e.g. summarizer, flusher)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_and_create_db():
    """Checks if the chatbot_main_db database exists on PostgreSQL, and creates it if not."""
    conn = None
    try:
        logger.info(f"Checking if database '{pg_database}' exists on PostgreSQL {pg_host}:{pg_port}...")
        conn = psycopg2.connect(
            host=pg_host,
            port=pg_port,
            database="postgres",
            user=pg_user,
            password=pg_password,
            connect_timeout=5
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (pg_database,))
            exists = cur.fetchone()
            if not exists:
                logger.info(f"Database '{pg_database}' does not exist. Creating database...")
                cur.execute(f'CREATE DATABASE "{pg_database}"')
                logger.info(f"Database '{pg_database}' created successfully.")
            else:
                logger.info(f"Database '{pg_database}' already exists.")
    except Exception as e:
        logger.error(f"Error checking or creating database '{pg_database}': {e}")
    finally:
        if conn:
            conn.close()


# ContextVars to dynamically track current session and message details across threads
from contextvars import ContextVar
from typing import Optional

session_id_var: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
message_id_var: ContextVar[Optional[int]] = ContextVar("message_id", default=None)

