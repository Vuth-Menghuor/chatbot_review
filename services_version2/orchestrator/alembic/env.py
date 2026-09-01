import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
from dotenv import load_dotenv

# Ensure the app directory is in the python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env variables
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None and config.get_main_option("programmatic") != "true":
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from app.infrastructure.models import Base
target_metadata = Base.metadata


def get_url():
    pg_host = os.getenv("POSTGRES_HOST") or os.getenv("PG_HOST", "127.0.0.1")
    pg_port = int(os.getenv("POSTGRES_PORT") or os.getenv("PG_PORT", 5433))
    pg_database = os.getenv("POSTGRES_DB") or os.getenv("PG_DATABASE", "chatbot_main_db")
    pg_user = os.getenv("POSTGRES_USER") or os.getenv("PG_USER", "postgres")
    pg_password = os.getenv("POSTGRES_PASSWORD") or os.getenv("PG_PASSWORD", "postgres")
    return f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

