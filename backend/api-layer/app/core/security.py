import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_token(user_id: UUID, token_type: str, lifetime: timedelta, role: str = "user") -> tuple[str, str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + lifetime
    jti = str(uuid4())
    payload = {"sub": str(user_id), "type": token_type, "role": role, "jti": jti, "iat": now, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm), jti, expires_at


def create_access_token(user_id: UUID, role: str) -> tuple[str, str, datetime]:
    return create_token(user_id, "access", timedelta(minutes=settings.access_token_expire_minutes), role)


def create_refresh_token(user_id: UUID, role: str) -> tuple[str, str, datetime]:
    return create_token(user_id, "refresh", timedelta(days=settings.refresh_token_expire_days), role)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def generate_api_key() -> str:
    return f"cb_{secrets.token_urlsafe(36)}"
