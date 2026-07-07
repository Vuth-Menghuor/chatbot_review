"""Unit tests for the auth service (key verification logic)."""

import uuid

import pytest

from app.core.errors import DALError
from app.core.security import hash_api_key, verify_api_key
from app.schemas.auth import AuthenticatedClient
from app.services import auth_service


class _DummyScalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _DummyExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _DummyScalars(self._values)


class _DummySession:
    def __init__(self, values):
        self._values = values

    async def execute(self, _statement):
        return _DummyExecuteResult(self._values)


class TestKeyHashing:
    def test_hash_returns_string(self):
        hashed = hash_api_key("test-key-123")
        assert isinstance(hashed, str)

    def test_hash_is_not_plaintext(self):
        plain = "test-key-123"
        hashed = hash_api_key(plain)
        assert hashed != plain

    def test_verify_correct_key(self):
        plain = "test-key-123"
        hashed = hash_api_key(plain)
        assert verify_api_key(plain, hashed) is True

    def test_verify_wrong_key(self):
        hashed = hash_api_key("correct-key")
        assert verify_api_key("wrong-key", hashed) is False

    def test_same_key_different_hashes(self):
        """bcrypt should produce different hashes for the same input (salted)."""
        plain = "test-key-123"
        h1 = hash_api_key(plain)
        h2 = hash_api_key(plain)
        assert h1 != h2  # Different salts
        # Both should verify
        assert verify_api_key(plain, h1) is True
        assert verify_api_key(plain, h2) is True


class TestCrudTierAuthorization:
    def _client(self, tier: str) -> AuthenticatedClient:
        return AuthenticatedClient(
            key_id=uuid.uuid4(),
            client_id="test-client",
            status="active",
            tier=tier,
            rate_limit_per_minute=10,
            scopes_by_dataset={},
            accessible_dataset_ids=[],
        )

    def test_admin_tier_allowed(self):
        auth_service.authorize_crud_tier(self._client("admin"))

    def test_developer_tier_allowed(self):
        auth_service.authorize_crud_tier(self._client("developer"))

    def test_standard_tier_forbidden(self):
        with pytest.raises(DALError):
            auth_service.authorize_crud_tier(self._client("standard"))

    def test_premium_tier_forbidden(self):
        with pytest.raises(DALError):
            auth_service.authorize_crud_tier(self._client("premium"))


class TestLocalDevelopmentApiKey:
    @pytest.mark.asyncio
    async def test_local_api_key_bypasses_db_auth(self, monkeypatch):
        dataset_ids = [uuid.uuid4(), uuid.uuid4()]
        monkeypatch.setattr(auth_service.settings, "app_env", "development")
        monkeypatch.setattr(auth_service.settings, "local_api_key", "dal-local-api-key")

        client = await auth_service.authenticate(
            "dal-local-api-key",
            _DummySession(dataset_ids),
        )

        assert client.client_id == "local_dev_client"
        assert client.tier == "developer"
        assert set(client.accessible_dataset_ids) == set(dataset_ids)
        assert all(scopes == ["query:read"] for scopes in client.scopes_by_dataset.values())
