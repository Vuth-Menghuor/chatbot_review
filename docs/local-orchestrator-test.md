# Local Orchestrator Integration Test

This setup is for local frontend/backend API testing only. It keeps the service-team source code and service-owned compose files unchanged.

Use the root compose file:

```bash
docker compose -f docker-compose.integration.yml up -d --build
```

If older containers from the per-service compose files are already running, stop those stacks first so container names and ports do not conflict.

## Main URLs

- Orchestrator: `http://127.0.0.1:8001`
- Calculator: `http://127.0.0.1:8002`
- Retrieval: `http://127.0.0.1:8003`
- Trade: `http://127.0.0.1:8004`
- General: `http://127.0.0.1:8005`
- DAL: `http://127.0.0.1:8010`

## DAL Data

The integration compose follows the DAL handoff flow:

1. Start metadata and operational PostgreSQL.
2. Run `alembic upgrade head`.
3. Restore `local_data/dal_metadata.backup`.
4. Restore `local_data/dal_operational.backup`.
5. Start the DAL API.

Those backup files are required for trade data. If they are missing, DAL can start with sample seed scripts, but trade will not match the data-team handoff state.

After restoring DAL data, clear stale orchestrator cache before retesting trade:

```bash
docker exec redis-general redis-cli FLUSHALL
docker restart orchestrator-service
```

## Calculator Database

The integration compose restores the calculator database from:

```text
gdce_postgre_db/dump-gdce_calculator-202607031116.sql
```

Local connection details:

```text
host: 127.0.0.1
port: 5435
database: gdce_calculator
user: calc_app
password: calc_app_password
```

## Bruno

The Bruno collection lives in `bruno/` and uses real local URLs. Start with:

- `00 Health`
- `01 Orchestrator/00 Ask Orchestrator Question`
- `01 Orchestrator/03 Query - Calculator`
- `01 Orchestrator/04 Query - Trade`

## Known Current Limits

- General and retrieval answers still need the `gdce_docs` Qdrant data loaded.
- Some natural-language calculator paths may still be slow because model/prewarm behavior lives inside service-team code.
- Trade routing depends on the DAL backups. If `trade_volume` is still missing after restore, ask the data team for the exact `dal_metadata.backup` and `dal_operational.backup` used by their working DAL.
