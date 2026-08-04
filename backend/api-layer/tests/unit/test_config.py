from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


# This file protects production startup validation from accidental weakening.


# Build the minimum strong production settings shared by the validation tests.
def production_settings(**overrides):
    values = {
        "environment": "production",
        "debug": False,
        "enable_docs": False,
        "jwt_secret_key": "x" * 32,
        "frontend_origins": ["https://chat.example.com"],
        "database_url": "postgresql+asyncpg://api_user:strong-password@prod-postgres:5432/api_layer_db",
        "redis_url": "redis://prod-redis:6379/0",
        "minio_secret_key": "strong-minio-secret",
        "rabbitmq_password": "strong-rabbitmq-secret",
    }
    values.update(overrides)
    return Settings(**values)


# Local development should keep working with the existing convenient defaults.
def test_development_allows_default_settings():
    settings = Settings()

    assert settings.environment == "development"
    assert settings.enable_docs is True


# Production should accept a fully explicit, strong configuration.
def test_production_accepts_strong_settings():
    settings = production_settings()

    assert settings.environment == "production"
    assert settings.enable_docs is False


# Production should reject the known default JWT secret.
def test_production_rejects_default_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        production_settings(jwt_secret_key="change-me")


# Production should reject short JWT secrets even if they are not the default string.
def test_production_rejects_short_jwt_secret():
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        production_settings(jwt_secret_key="short-secret")


# Production should never expose debug behavior.
def test_production_rejects_debug_enabled():
    with pytest.raises(ValidationError, match="DEBUG"):
        production_settings(debug=True)


# Production should not expose interactive API docs by default.
def test_production_rejects_docs_enabled():
    with pytest.raises(ValidationError, match="ENABLE_DOCS"):
        production_settings(enable_docs=True)


# Production CORS must name trusted frontend origins explicitly.
def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError, match="FRONTEND_ORIGINS"):
        production_settings(frontend_origins=["*"])


# Production should not use default/example database credentials.
def test_production_rejects_default_database_credentials():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        production_settings(database_url="postgresql+asyncpg://api_user:api_password@api-postgres:5432/api_layer_db")


# Production should use an explicitly configured Redis endpoint.
def test_production_rejects_default_redis_url():
    with pytest.raises(ValidationError, match="REDIS_URL"):
        production_settings(redis_url="redis://api-redis:6379/0")


# Production should not allow the common MinIO default secret.
def test_production_rejects_default_minio_secret():
    with pytest.raises(ValidationError, match="MINIO_SECRET_KEY"):
        production_settings(minio_secret_key="minioadmin")


# Production should not allow default/example RabbitMQ passwords.
def test_production_rejects_default_rabbitmq_password():
    with pytest.raises(ValidationError, match="RABBITMQ_PASSWORD"):
        production_settings(rabbitmq_password="guest")
