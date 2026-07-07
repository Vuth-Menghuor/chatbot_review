# Implementation Plan: Redis & Historical Chat Management

This plan outlines the implementation details for provisioning Redis as the live, hot session cache, storing historical chat turn streams, and periodically flushing older turns to a Postgres archive table for long-term historical query capability.

## User Review Required

> [!IMPORTANT]
> - **External Network Usage**: The orchestrator's `docker-compose.yml` relies on an external network `gdce-network` (configured as `external: true`). We will add the Redis container on this network. Please ensure `gdce-network` is created prior to running docker-compose (`docker network create gdce-network`).
> - **Postgres Driver Dependency**: We are adding `psycopg2-binary` to `requirements.txt`. If you run in a custom build environment, make sure standard C development headers are available, or that pre-built wheels are supported.

## Open Questions

> [!NOTE]
> None at the moment. The requirements are clear, and the current codebase structure maps cleanly to the requested features.

---

## Proposed Changes

### Docker & Environment Provisioning

#### [MODIFY] [docker-compose.yml](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/docker-compose.yml)
- Define a dedicated `redis` service.
- Enable password protection on Redis by running with `--requirepass ${REDIS_PASSWORD}`.
- Mount a persistent Docker volume `redis-data` (to the internal path `/data`) so session records survive service restarts.
- Bind the service to the `gdce-network` without exposing any ports publicly.
- Add a top-level `volumes` block defining the named volume `redis-data`.

#### [MODIFY] [.env.example](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/.env.example) and [.env](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/.env)
- Add env configurations:
  - `REDIS_HOST=redis` (resolves inside Docker Compose network)
  - `REDIS_PORT=6379`
  - `REDIS_PASSWORD=change_me_in_production`
  - `TRANSCRIPT_FLUSH_INTERVAL=300` (Periodic flusher run interval in seconds, defaults to 5 minutes)
  - `REDIS_RETENTION_TURNS=20` (Number of latest hot turns to retain in Redis per session)
  - `POSTGRES_RETENTION_DAYS=90` (Archive retention period in Postgres)

---

### Python Orchestrator Modifications

#### [MODIFY] [requirements.txt](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/requirements.txt)
- Add `psycopg2-binary>=2.9.0` to enable database operations from the orchestrator app.

#### [MODIFY] [config.py](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/app/core/config.py)
- Load newly introduced Redis and Postgres retention variables from environment variables:
  - `redis_host`, `redis_port`, `redis_password`.
  - `transcript_flush_interval`, `redis_retention_turns`, `postgres_retention_days`.

#### [MODIFY] [session_context.py](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/app/core/session_context.py)
- Refactor `SessionManager`'s Redis client initialization:
  - Keep `self.redis_client` active even if the initial connection test (`ping()`) fails. Redis-py automatically attempts reconnection on subsequent queries.
  - Wrap Redis access in `get_or_create_session` and `_save_session` inside `try-except` blocks. In the event of a Redis outage, log the error and gracefully fall back to local disk storage.

#### [NEW] [session_flusher.py](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/app/core/session_flusher.py)
- Add an initialization function `init_archive_table(config)` to verify and create the `transcript_archive` table in PostgreSQL on startup:
  ```sql
  CREATE TABLE IF NOT EXISTS transcript_archive (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      session_id VARCHAR(255) NOT NULL,
      redis_entry_id VARCHAR(255) NOT NULL,
      role VARCHAR(50) NOT NULL,
      content TEXT NOT NULL,
      ts TIMESTAMP NOT NULL,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );
  CREATE INDEX IF NOT EXISTS idx_transcript_archive_user_id ON transcript_archive(user_id);
  CREATE INDEX IF NOT EXISTS idx_transcript_archive_session_id ON transcript_archive(session_id);
  CREATE INDEX IF NOT EXISTS idx_transcript_archive_ts ON transcript_archive(ts);
  ```
- Implement the periodic background flusher loop `periodic_transcript_flush(app)`:
  - Scan Redis stream keys: `session:*:transcript`.
  - Fetch corresponding user context `session:{session_id}:context` to read the associated `user_id` (fallback to `"default_user"` if missing or expired).
  - Use the existing `flush_session_to_pg` routine to move turns beyond the `keep_last_n` threshold to Postgres and trim the Redis stream.
  - If a session context has expired (no active cache in Redis), flush *all* remaining stream entries to PostgreSQL and delete the stream.
  - Execute a retention query to prune old database records:
    `DELETE FROM transcript_archive WHERE ts < NOW() - INTERVAL '{postgres_retention_days} days'`
  - Handle exceptions gracefully: if Postgres is down, skip trimming the Redis stream so turns can be safely retried during the next run.

#### [MODIFY] [health_checks.py](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/app/infrastructure/health_checks.py)
- Implement `check_redis_health(redis_client)` to ping Redis and verify the session caching state.
- Implement `check_postgres_health(db_config)` to verify Postgres availability by executing a simple query (e.g. `SELECT 1`) or testing a transaction block on `transcript_archive`.

#### [MODIFY] [endpoints.py](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/app/api/endpoints.py)
- Update the `/status` route to run the new Redis and Postgres health checks and report infrastructure state in the JSON response (e.g. `{"redis": "up", "postgres": "up"}`).

#### [MODIFY] [main.py](file:///home/gdce/gdce-chatbot/services_version2/orchestrator/app/main.py)
- Import and call `init_archive_table(config)` in the `startup_event`.
- Launch the background flusher task using `asyncio.create_task(periodic_transcript_flush(app))`.

---

## Verification Plan

### Automated Tests
- Implement unit tests under `services_version2/orchestrator/tests/` to verify:
  1. `SessionManager` fallback behavior when Redis is unreachable (simulated by throwing errors).
  2. Transactional safety of the `flush_session_to_pg` helper (ensuring Redis trimming occurs only after successful PG commit).
  3. Table initialization and retention SQL queries.

### Manual Verification
- **Scenario 1: Redis Up, Postgres Up**
  - Run the stack using `docker-compose`.
  - Perform multiple chat turns via `/query`.
  - Verify that session context is successfully written to Redis and stream entries are updated.
  - Wait/trigger the flusher job, verify older turns are moved to PostgreSQL `transcript_archive`, and verify the tail size in the Redis stream.
- **Scenario 2: Redis Down, Postgres Up**
  - Temporarily stop the Redis container.
  - Execute chat queries and confirm the session is fallback-saved to disk.
  - Confirm the health check status endpoints report `redis` as `down` while the orchestrator continues processing requests.
- **Scenario 3: Redis Up, Postgres Down**
  - Temporarily stop the Postgres service.
  - Run chat queries, verify that turns continue accumulating in the Redis stream.
  - Trigger the flush worker and verify it logs a connection failure and exits gracefully *without* trimming the Redis stream.
  - Restart Postgres, wait for the next run, and confirm all queued turns are successfully flushed.
