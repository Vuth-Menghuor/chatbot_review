from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis import redis_client
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, hash_secret, verify_password
from app.dependencies.auth import get_current_user
from app.models import RefreshToken, User
from app.schemas.common import LoginRequest, TokenResponse, UserCreate, UserRead, UserUpdate
from app.services.audit_service import add_audit_log
from app.services.rate_limit_service import enforce_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def issue_tokens(user: User) -> tuple[str, str, RefreshToken]:
    access, _, _ = create_access_token(user.id, user.role)
    refresh, _, expires_at = create_refresh_token(user.id, user.role)
    return access, refresh, RefreshToken(user_id=user.id, token_hash=hash_secret(refresh), expires_at=expires_at)


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Store the long-lived token outside the JavaScript-accessible browser APIs."""
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        httponly=True,
        secure=settings.environment == "production",
        samesite=settings.refresh_cookie_samesite,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path="/api/v1/auth",
        domain=settings.refresh_cookie_domain,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/api/v1/auth",
        domain=settings.refresh_cookie_domain,
        secure=settings.environment == "production",
        samesite=settings.refresh_cookie_samesite,
    )


@router.post("/register", response_model=UserRead, status_code=201)
async def register(payload: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"register:{client_ip(request)}", 5, request=request)
    email = payload.email.lower()
    if (await db.execute(select(User.id).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email is already registered")
    user = User(full_name=payload.full_name.strip(), email=email, hashed_password=hash_password(payload.password))
    db.add(user)
    await db.flush()
    add_audit_log(db, "user_registered", "user", user.id, ip_address=client_ip(request))
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit(f"login:{client_ip(request)}", 5, request=request)
    user = (await db.execute(select(User).where(User.email == payload.email.lower()))).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    access, refresh, token_row = issue_tokens(user)
    db.add(token_row)
    add_audit_log(db, "user_login", "user", user.id, ip_address=client_ip(request))
    await db.commit()
    set_refresh_cookie(response, refresh)
    return TokenResponse(access_token=access, user=UserRead.model_validate(user))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    try:
        claims = decode_token(refresh_token)
        if claims.get("type") != "refresh":
            raise ValueError
        row = (await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_secret(refresh_token)))).scalar_one_or_none()
        if not row or row.revoked_at or row.expires_at <= datetime.now(timezone.utc):
            raise ValueError
        user = await db.get(User, row.user_id)
        if not user or not user.is_active:
            raise ValueError
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    row.revoked_at = datetime.now(timezone.utc)
    access, refresh_value, new_row = issue_tokens(user)
    db.add(new_row)
    await db.commit()
    set_refresh_cookie(response, refresh_value)
    return TokenResponse(access_token=access, user=UserRead.model_validate(user))


@router.post("/logout")
async def logout(request: Request, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if refresh_token:
        row = (await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_secret(refresh_token), RefreshToken.user_id == user.id))).scalar_one_or_none()
        if row and not row.revoked_at:
            row.revoked_at = datetime.now(timezone.utc)
    jti = getattr(request.state, "token_jti", None)
    exp = getattr(request.state, "token_exp", None)
    if jti and exp:
        ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
        try:
            await redis_client.setex(f"token_blacklist:{jti}", ttl, "1")
        except Exception:
            pass
    add_audit_log(db, "user_logout", "user", user.id, ip_address=client_ip(request))
    await db.commit()
    clear_refresh_cookie(response)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return user

    if "full_name" in changes:
        changes["full_name"] = changes["full_name"].strip()
        if not changes["full_name"]:
            raise HTTPException(status_code=422, detail="Full name cannot be empty")

    if "email" in changes and changes["email"] is not None:
        email = str(changes["email"]).lower()
        existing = (
            await db.execute(
                select(User.id).where(User.email == email, User.id != user.id),
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Email is already registered")
        changes["email"] = email

    for field in ("nickname", "phone", "address", "avatar_url"):
        if field in changes and isinstance(changes[field], str):
            changes[field] = changes[field].strip() or None

    for key, value in changes.items():
        setattr(user, key, value)

    add_audit_log(
        db,
        "user_profile_updated",
        "user",
        user.id,
        {"fields": list(changes)},
        ip_address=client_ip(request),
    )
    await db.commit()
    await db.refresh(user)
    return user
