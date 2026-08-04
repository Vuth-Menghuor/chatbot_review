from __future__ import annotations

from datetime import timedelta, timezone
from uuid import uuid4

from app.core.security import (
    create_token,
    decode_token,
    generate_api_key,
    hash_password,
    hash_secret,
    verify_password,
)


# This file protects security helpers that auth, refresh tokens, and API keys depend on.


# API keys and refresh tokens are stored as hashes, so hashing must stay deterministic and non-reversible.
def test_hash_secret_is_stable_sha256_hex_digest():
    digest = hash_secret("secret-value")

    assert digest == hash_secret("secret-value")
    assert digest != "secret-value"
    assert len(digest) == 64


# Password verification must accept the original password and reject any other value.
def test_password_hash_verifies_only_original_password():
    password_hash = hash_password("strong-password")

    assert verify_password("strong-password", password_hash)
    assert not verify_password("wrong-password", password_hash)


# JWT creation and decoding must preserve the claims used by auth dependencies.
def test_create_token_round_trips_claims():
    user_id = uuid4()

    token, jti, expires_at = create_token(user_id, "access", timedelta(minutes=5), role="admin")
    payload = decode_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"
    assert payload["role"] == "admin"
    assert payload["jti"] == jti
    assert expires_at.tzinfo == timezone.utc


# Generated API keys must keep the public prefix and include enough randomness.
def test_generate_api_key_uses_expected_prefix_and_entropy():
    key = generate_api_key()

    assert key.startswith("cb_")
    assert len(key) > 40
    assert key != generate_api_key()
