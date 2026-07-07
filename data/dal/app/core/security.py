"""Security helpers — API key hashing and verification."""

import bcrypt


def hash_api_key(plain_key: str) -> str:
    """Hash an API key for storage. Never store plaintext keys."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain_key.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    """Verify a plaintext key against its stored hash."""
    return bcrypt.checkpw(plain_key.encode("utf-8"), hashed_key.encode("utf-8"))
