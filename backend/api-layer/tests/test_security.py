from uuid import uuid4

from app.core.security import create_access_token, decode_token, hash_password, hash_secret, verify_password


def test_password_hash_round_trip():
    encoded = hash_password("password123")
    assert encoded != "password123"
    assert verify_password("password123", encoded)
    assert not verify_password("wrong-password", encoded)


def test_access_token_claims():
    user_id = uuid4()
    token, jti, _ = create_access_token(user_id, "user")
    claims = decode_token(token)
    assert claims["sub"] == str(user_id)
    assert claims["jti"] == jti
    assert claims["type"] == "access"


def test_secret_hash_is_stable_and_not_plaintext():
    assert hash_secret("secret") == hash_secret("secret")
    assert hash_secret("secret") != "secret"
