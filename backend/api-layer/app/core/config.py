from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Chatbot API Layer"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://api_user:api_password@api-postgres:5432/api_layer_db"
    redis_url: str = "redis://api-redis:6379/0"
    main_chatbot_service_url: str = "http://orchestrator-service-orches:8001"
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    frontend_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])
    api_response_cache_seconds: int = 30
    http_timeout_seconds: float = 60.0
    general_rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

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

    @property
    def main_service_url(self) -> str:
        return self.main_chatbot_service_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
