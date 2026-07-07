"""Core configuration loaded from environment variables."""

from functools import lru_cache
from pydantic_settings import BaseSettings
from urllib.parse import quote_plus


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env file."""

    # --- Application ---
    app_name: str = "dal"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    docs_enabled: bool = True

    # --- Metadata Database ---
    metadata_db_host: str = "localhost"
    metadata_db_port: int = 5433
    metadata_db_user: str = "dal_meta"
    metadata_db_password: str = "dal_meta_secret"
    metadata_db_name: str = "dal_metadata"

    # --- Operational Database ---
    operational_db_host: str = "localhost"
    operational_db_port: int = 5434
    operational_db_user: str = "dal_ops"
    operational_db_password: str = "dal_ops_secret"
    operational_db_name: str = "dal_operational"

    # --- Redis ---
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # --- Rate Limiting ---
    default_rate_limit_per_minute: int = 10
    crud_rate_limit_per_minute: int = 10

    # --- Local Development Auth ---
    local_api_key: str = "dal-local-api-key"

    # --- Query Defaults ---
    default_query_limit: int = 100
    max_query_limit: int = 10000

    # --- Computed properties ---
    @property
    def metadata_db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.metadata_db_user}:{quote_plus(self.metadata_db_password)}"
            f"@{self.metadata_db_host}:{self.metadata_db_port}/{self.metadata_db_name}"
        )

    @property
    def metadata_db_url_sync(self) -> str:
        """Sync URL for Alembic migrations."""
        return (
            f"postgresql://{self.metadata_db_user}:{quote_plus(self.metadata_db_password)}"
            f"@{self.metadata_db_host}:{self.metadata_db_port}/{self.metadata_db_name}"
        )

    @property
    def operational_db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.operational_db_user}:{quote_plus(self.operational_db_password)}"
            f"@{self.operational_db_host}:{self.operational_db_port}/{self.operational_db_name}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{quote_plus(self.redis_password)}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    """Cached singleton settings instance."""
    return Settings()
