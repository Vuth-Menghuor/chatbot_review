from datetime import datetime, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import redis_client
from app.core.security import decode_token, hash_secret
from app.models import ApiKey, User

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    raw_api_key: str | None = Security(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> User:
    user: User | None = None
    if credentials:
        try:
            payload = decode_token(credentials.credentials)
            if payload.get("type") != "access":
                raise ValueError("wrong token type")
            try:
                if await redis_client.exists(f"token_blacklist:{payload['jti']}"):
                    raise ValueError("revoked token")
            except ConnectionError:
                pass
            user = await db.get(User, UUID(payload["sub"]))
            request.state.token_jti = payload["jti"]
            request.state.token_exp = payload["exp"]
        except (jwt.PyJWTError, KeyError, ValueError, TypeError):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired access token")
    elif raw_api_key:
        result = await db.execute(select(ApiKey).where(ApiKey.key_hash == hash_secret(raw_api_key), ApiKey.is_active.is_(True)))
        key = result.scalar_one_or_none()
        if key:
            user = await db.get(User, key.user_id)
            key.last_used_at = datetime.now(timezone.utc)
            await db.commit()

    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    request.state.user_id = user.id
    return user
