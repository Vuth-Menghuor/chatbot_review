#!/bin/sh
set -e

CALC_PASSWORD="${CALCULATOR_DB_PASSWORD:-16112005}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'calc_app') THEN
    CREATE ROLE calc_app LOGIN PASSWORD '${CALC_PASSWORD}';
  ELSE
    ALTER ROLE calc_app WITH LOGIN PASSWORD '${CALC_PASSWORD}';
  END IF;
END
\$\$;
SQL

pg_restore \
  --clean \
  --if-exists \
  --create \
  --no-owner \
  --dbname=postgres \
  /docker-entrypoint-initdb.d/gdce_calculator.dump

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname gdce_calculator <<SQL
GRANT ALL PRIVILEGES ON DATABASE gdce_calculator TO calc_app;
GRANT ALL PRIVILEGES ON SCHEMA public TO calc_app;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO calc_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO calc_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO calc_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO calc_app;
SQL
