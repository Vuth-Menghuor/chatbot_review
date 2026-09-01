import logging
import asyncio
import json
import re
from datetime import datetime
from typing import Any, List, Dict

logger = logging.getLogger(__name__)

# Import psycopg2 defensively to support environments where it may not be installed
try:
    import psycopg2
except ImportError:
    psycopg2 = None


def init_archive_table(config: Any):
    """
    Connects to PostgreSQL and initializes the transcript_archive table and indexes.
    Fails gracefully if database is down or not created.
    """
    if psycopg2 is None:
        logger.warning("psycopg2 is not installed. Database archiving is disabled.")
        return

    logger.info("Initializing PostgreSQL transcript_archive table...")
    conn = None
    try:
        conn = psycopg2.connect(
            host=config.pg_host,
            port=config.pg_port,
            database=config.pg_database,
            user=config.pg_user,
            password=config.pg_password,
            connect_timeout=5
        )
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS transcript_archive (
                    id SERIAL PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    session_id VARCHAR(255) NOT NULL,
                    redis_entry_id VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    ts TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (session_id, redis_entry_id)
                );
                CREATE INDEX IF NOT EXISTS idx_transcript_archive_user_id ON transcript_archive(user_id);
                CREATE INDEX IF NOT EXISTS idx_transcript_archive_session_id ON transcript_archive(session_id);
                CREATE INDEX IF NOT EXISTS idx_transcript_archive_ts ON transcript_archive(ts);
            """)
        conn.commit()
        logger.info("PostgreSQL transcript_archive table initialized successfully.")
    except Exception as e:
        logger.warning(f"Could not connect to PostgreSQL database to initialize transcript_archive table (Postgres offline): {e}")
    finally:
        if conn:
            conn.close()


def flush_session_to_pg(session_id: str, user_id: str, redis_conn: Any, pg_conn: Any, keep_last_n: int = 20) -> bool:
    """
    Flushes older Redis Stream transcript logs to Postgres and trims the Redis tail.
    Returns True if successful, False otherwise.
    """
    stream_key = f"session:{session_id}:transcript"
    try:
        entries = redis_conn.xrange(stream_key)  # [(entry_id, {field: value}), ...]
        if not entries:
            return True

        if len(entries) <= keep_last_n:
            return True  # Nothing old enough to flush yet

        # Keep the hot tail in memory
        to_flush = entries[:-keep_last_n] if keep_last_n > 0 else entries

        with pg_conn.cursor() as cur:
            for entry_id, fields in to_flush:
                ts_val = fields.get("ts")
                try:
                    ts_dt = datetime.fromisoformat(ts_val)
                except (ValueError, TypeError):
                    ts_dt = datetime.utcnow()

                cur.execute(
                    """INSERT INTO transcript_archive
                       (user_id, session_id, redis_entry_id, role, content, ts)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (session_id, redis_entry_id) DO NOTHING""",
                    (user_id, session_id, entry_id, fields.get("role", "user"), fields.get("content", ""), ts_dt),
                )
        pg_conn.commit()  # Confirm write BEFORE trimming Redis stream

        if keep_last_n > 0:
            last_flushed_id = to_flush[-1][0]
            # bump past the last flushed entry so it isn't re-flushed next run
            major, minor = last_flushed_id.split("-")
            next_id = f"{major}-{int(minor) + 1}"
            redis_conn.xtrim(stream_key, minid=next_id, approximate=False)
            logger.info(f"Flushed {len(to_flush)} transcript entries for session {session_id} to Postgres. Stream trimmed.")
        else:
            redis_conn.delete(stream_key)
            logger.info(f"Session context expired. Flushed all {len(to_flush)} entries and deleted Redis stream for session {session_id}.")
        return True
    except Exception as e:
        logger.error(f"Failed to flush stream {session_id} to Postgres: {e}")
        try:
            pg_conn.rollback()
        except:
            pass
        return False


async def periodic_transcript_flush(app: Any):
    """
    Periodic background flusher loop:
    1. Scan Redis keys for streams 'session:*:transcript'.
    2. Retrieve stable user_id from context cache.
    3. Flush older entries to Postgres and trim streams.
    4. Handle expired sessions (flush all remaining turns and delete stream).
    5. Execute database retention pruning query.
    """
    config = app.state.config
    # Wait for startup to fully complete
    await asyncio.sleep(5)
    
    logger.info("Background transcript flusher service started.")
    
    while True:
        try:
            # Run at the configured interval
            await asyncio.sleep(config.transcript_flush_interval)
            
            # Resolve dependencies lazily
            if not hasattr(app.state, 'first_layer_service'):
                continue
            
            redis_client = app.state.first_layer_service.session_manager.redis_client
            if redis_client is None:
                continue
            
            # 1. Scan Redis stream keys
            try:
                stream_keys = []
                cursor = 0
                while True:
                    cursor, batch = redis_client.scan(cursor=cursor, match="session:*:transcript", count=100)
                    stream_keys.extend(batch)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.error(f"[Flusher] Failed to query Redis keys: {e}")
                continue

            if not stream_keys:
                continue

            logger.debug(f"[Flusher] Found {len(stream_keys)} active stream transcript(s) to process.")

            # Connect to PostgreSQL for the current batch run
            pg_conn = None
            if psycopg2 is not None:
                try:
                    pg_conn = psycopg2.connect(
                        host=config.pg_host,
                        port=config.pg_port,
                        database=config.pg_database,
                        user=config.pg_user,
                        password=config.pg_password,
                        connect_timeout=5
                    )
                except Exception as e:
                    logger.warning(f"[Flusher] PostgreSQL is offline. Skipping flusher run: {e}")
                    continue
            else:
                continue

            try:
                for stream_key in stream_keys:
                    # Extract session_id
                    match = re.match(r"^session:(.+):transcript$", stream_key)
                    if not match:
                        continue
                    session_id = match.group(1)

                    # Check if session context exists in Redis
                    context_key = f"session:{session_id}:context"
                    user_id = "default_user"
                    is_expired = True

                    try:
                        raw_context = redis_client.get(context_key)
                        if raw_context:
                            is_expired = False
                            data = json.loads(raw_context)
                            user_id = data.get("user_id", "default_user")
                    except Exception as e:
                        logger.error(f"[Flusher] Failed to read session context for {session_id}: {e}")
                        # Skip if we can't determine state to avoid incorrect pruning
                        continue

                    # Flush entries
                    if is_expired:
                        # Expired: Flush all remaining stream entries (keep_last_n=0)
                        flush_session_to_pg(session_id, user_id, redis_client, pg_conn, keep_last_n=0)
                    else:
                        # Active: Keep hot tail in Redis
                        flush_session_to_pg(
                            session_id, 
                            user_id, 
                            redis_client, 
                            pg_conn, 
                            keep_last_n=config.redis_retention_turns
                        )

                # 5. Database retention pruning query
                try:
                    with pg_conn.cursor() as cur:
                        cur.execute(
                            f"DELETE FROM transcript_archive WHERE ts < NOW() - INTERVAL '{config.postgres_retention_days} days'"
                        )
                        deleted_count = cur.rowcount
                        if deleted_count > 0:
                            logger.info(f"[Flusher] Pruned {deleted_count} old transcript records from Postgres (older than {config.postgres_retention_days} days).")
                    pg_conn.commit()
                except Exception as e:
                    logger.error(f"[Flusher] Failed to run Postgres retention pruning query: {e}")
                    pg_conn.rollback()

            finally:
                if pg_conn:
                    pg_conn.close()

        except asyncio.CancelledError:
            logger.info("Background transcript flusher service stopping.")
            break
        except Exception as e:
            logger.error(f"[Flusher] Unexpected error in flusher loop: {e}", exc_info=True)
