from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Chatbot API Layer"
    environment: Literal["development", "local", "dev", "testing", "staging", "production"] = "development"
    debug: bool = False
    enable_chat_response_debug: bool = False
    enable_docs: bool = True
    database_url: str = "postgresql+asyncpg://api_user:api_password@api-postgres:5432/api_layer_db"
    redis_url: str = "redis://api-redis:6379/0"
    main_chatbot_service_url: str = "http://orchestrator-service-orches:8001"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    refresh_cookie_name: str = "gdce_refresh"
    # Keep the cookie scoped to auth endpoints; the browser never exposes it to JS.
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_domain: str | None = None
    frontend_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])
    api_response_cache_seconds: int = 30
    http_timeout_seconds: float = 60.0
    # By default /chat/stream proxies the orchestrator's live /query/stream.
    # Enable only when a deployment must wait for the completed /query response.
    use_standard_chat_stream: bool = False
    general_rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    retention_cleanup_enabled: bool = True
    retention_cleanup_interval_seconds: int = 24 * 60 * 60
    chat_retention_days: int = 90
    deleted_chat_retention_days: int = 30
    deleted_file_retention_days: int = 30
    audit_log_retention_days: int = 365

    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "chatbot-files"
    minio_secure: bool = False

    rabbitmq_host: str = "rabbitmq"
    rabbitmq_port: int = 5672
    rabbitmq_user: str = "guest"
    rabbitmq_password: str = "guest"
    rabbitmq_image_queue: str = "image_jobs"

    max_image_size_mb: int = 5
    allowed_image_types: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    )

    @field_validator("debug", "enable_docs", mode="before")
    @classmethod
    def parse_bool_flags(cls, value):
        if isinstance(value, str) and value.strip().lower() in {"release", "prod", "production"}:
            return False
        return value

    @field_validator("allowed_image_types", mode="before")
    @classmethod
    def parse_allowed_image_types(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def max_image_size_bytes(self) -> int:
        return self.max_image_size_mb * 1024 * 1024

    @property
    def allowed_image_extensions(self) -> set[str]:
        mapping = {
            "image/jpeg": {"jpg", "jpeg"},
            "image/jpg": {"jpg", "jpeg"},
            "image/png": {"png"},
            "image/webp": {"webp"},
        }
        extensions: set[str] = set()
        for content_type in self.allowed_image_types:
            extensions.update(mapping.get(content_type.lower(), set()))
        return extensions

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_origins(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.environment != "production":
            return self

        errors: list[str] = []
        if self.debug:
            errors.append("DEBUG cannot be enabled in production")
        if self.enable_docs:
            errors.append("ENABLE_DOCS cannot be enabled in production")
        if self.jwt_secret_key == "change-me" or len(self.jwt_secret_key) < 32:
            errors.append("JWT_SECRET_KEY must be at least 32 characters and not use the default value")
        if "*" in self.frontend_origins:
            errors.append("FRONTEND_ORIGINS cannot contain '*' in production")
        if "api_password" in self.database_url or "your-db-password" in self.database_url:
            errors.append("DATABASE_URL cannot use default development credentials in production")
        if self.redis_url == "redis://api-redis:6379/0":
            errors.append("REDIS_URL must be explicitly configured for production")
        if self.minio_secret_key in {"minioadmin", "your-minio-secret-key"}:
            errors.append("MINIO_SECRET_KEY cannot use a default/example value in production")
        if self.rabbitmq_password in {"guest", "your-rabbitmq-password"}:
            errors.append("RABBITMQ_PASSWORD cannot use a default/example value in production")
        if errors:
            raise ValueError("; ".join(errors))
        return self

    @property
    def main_service_url(self) -> str:
        return self.main_chatbot_service_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
