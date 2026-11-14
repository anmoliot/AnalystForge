"""Authentication endpoints: register, login, refresh, logout, 2FA, API keys."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.auth import (
    create_access_token,
    create_refresh_token,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_api_key,
    generate_totp_secret,
    get_totp_uri,
    hash_password,
    hash_token,
    slugify,
    verify_password,
    verify_totp,
)
from analystforge.api.deps import CurrentUser, SessionDep, SettingsDep, get_settings
from analystforge.api.errors import (
    AuthenticationError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from analystforge.api.models.core import ApiKey, AuditLog, RefreshToken, TOTPSecret, Tenant, User

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    tenant_name: str = Field(min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def _strong_password(cls, value: str) -> str:
        if not any(c.isdigit() for c in value) or not any(c.isalpha() for c in value):
            raise ValueError("Password must contain letters and digits")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    tenant_id: uuid.UUID
    totp_enabled: bool = False

    model_config = {"from_attributes": True}


class TOTPSetupResponse(BaseModel):
    secret: str
    uri: str


class TOTPVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TOTPDisableRequest(BaseModel):
    password: str


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    expires_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None

    model_config = {"from_attributes": True}


class ApiKeyCreateResponse(ApiKeyResponse):
    full_key: str  # shown exactly once


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _refresh_cookie_kwargs(settings: SettingsDep) -> dict[str, Any]:  # type: ignore[type-arg]
    return {
        "key": "refresh_token",
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "max_age": settings.refresh_token_days * 86400,
        "domain": settings.cookie_domain,
        "path": "/api/v1/auth/refresh",
    }


async def _write_audit(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    tenant_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    request: Request | None = None,
) -> None:
    log = AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )
    session.add(log)


async def _get_active_totp(session: AsyncSession, user_id: uuid.UUID) -> TOTPSecret | None:
    result = await session.execute(
        select(TOTPSecret).where(
            TOTPSecret.user_id == user_id, TOTPSecret.is_verified.is_(True)
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
) -> UserResponse:
    # Create or find tenant
    slug = slugify(body.tenant_name)
    tenant_result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name=body.tenant_name, slug=slug)
        session.add(tenant)
        await session.flush()

    # Check email uniqueness within tenant
    existing = await session.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == body.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("Email already registered for this tenant.")

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        full_name=body.full_name,
        password_hash=hash_password(body.password),
        role="ADMIN",  # first user in a tenant gets ADMIN
    )
    session.add(user)
    await session.flush()

    await _write_audit(
        session,
        action="user.register",
        entity_type="user",
        entity_id=str(user.id),
        tenant_id=tenant.id,
        actor_id=user.id,
        request=request,
    )

    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        tenant_id=user.tenant_id,
        totp_enabled=False,
    )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        await _write_audit(
            session,
            action="user.login.failed",
            entity_type="user",
            entity_id=body.email,
            request=request,
        )
        raise AuthenticationError("Invalid credentials.")

    if not user.is_active:
        raise AuthenticationError("Account is inactive.")

    # Check TOTP if enabled
    totp_rec = await _get_active_totp(session, user.id)
    if totp_rec is not None:
        if not body.totp_code:
            raise AuthenticationError("TOTP code required.")
        raw_secret = decrypt_totp_secret(totp_rec.encrypted_secret, settings)
        if not verify_totp(raw_secret, body.totp_code):
            raise AuthenticationError("Invalid TOTP code.")

    # Issue tokens
    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role,
        settings=settings,
    )
    raw_refresh = create_refresh_token()
    family = uuid.uuid4().hex

    db_refresh = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        family=family,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    session.add(db_refresh)

    await _write_audit(
        session,
        action="user.login",
        entity_type="user",
        entity_id=str(user.id),
        tenant_id=user.tenant_id,
        actor_id=user.id,
        request=request,
    )

    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_days * 86400,
        domain=settings.cookie_domain,
        path="/api/v1/auth/refresh",
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_minutes * 60,
    )


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> TokenResponse:
    if not refresh_token:
        raise AuthenticationError("Refresh token missing.")

    token_hash = hash_token(refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    db_token = result.scalar_one_or_none()

    if db_token is None:
        raise AuthenticationError("Invalid refresh token.")

    if db_token.is_revoked:
        # Potential token reuse attack — revoke the whole family
        await session.execute(
            select(RefreshToken).where(RefreshToken.family == db_token.family)
        )
        db_token.is_revoked = True
        raise AuthenticationError("Refresh token already used.")

    expires_at = db_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise AuthenticationError("Refresh token expired.")

    # Rotate: revoke old, issue new
    db_token.is_revoked = True

    user_result = await session.execute(select(User).where(User.id == db_token.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive.")

    access_token = create_access_token(
        subject=str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role,
        settings=settings,
    )
    raw_refresh = create_refresh_token()

    new_token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw_refresh),
        family=db_token.family,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    session.add(new_token)

    response.set_cookie(
        key="refresh_token",
        value=raw_refresh,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.refresh_token_days * 86400,
        domain=settings.cookie_domain,
        path="/api/v1/auth/refresh",
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.access_token_minutes * 60,
    )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    if refresh_token:
        token_hash = hash_token(refresh_token)
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        db_token = result.scalar_one_or_none()
        if db_token and not db_token.is_revoked:
            db_token.is_revoked = True

    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth/refresh",
    )


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------


@router.get("/me")
async def me(
    current_user: CurrentUser,
    session: SessionDep,
) -> UserResponse:
    totp_rec = await _get_active_totp(session, current_user.id)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        tenant_id=current_user.tenant_id,
        totp_enabled=totp_rec is not None,
    )


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------


@router.post("/totp/setup")
async def totp_setup(
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> TOTPSetupResponse:
    # Remove any existing unverified secret
    existing = await session.execute(
        select(TOTPSecret).where(TOTPSecret.user_id == current_user.id)
    )
    for rec in existing.scalars():
        await session.delete(rec)

    raw_secret = generate_totp_secret()
    encrypted = encrypt_totp_secret(raw_secret, settings)
    totp_rec = TOTPSecret(
        user_id=current_user.id,
        encrypted_secret=encrypted,
        is_verified=False,
    )
    session.add(totp_rec)

    return TOTPSetupResponse(
        secret=raw_secret,
        uri=get_totp_uri(raw_secret, current_user.email),
    )


@router.post("/totp/verify", status_code=204)
async def totp_verify(
    body: TOTPVerifyRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    result = await session.execute(
        select(TOTPSecret).where(
            TOTPSecret.user_id == current_user.id,
            TOTPSecret.is_verified.is_(False),
        )
    )
    totp_rec = result.scalar_one_or_none()
    if totp_rec is None:
        raise NotFoundError("No pending TOTP setup. Call /totp/setup first.")

    raw_secret = decrypt_totp_secret(totp_rec.encrypted_secret, settings)
    if not verify_totp(raw_secret, body.code):
        raise ValidationFailedError("Invalid TOTP code.")

    totp_rec.is_verified = True

    await _write_audit(
        session,
        action="user.totp.enabled",
        entity_type="user",
        entity_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
        actor_id=current_user.id,
        request=request,
    )


@router.post("/totp/disable", status_code=204)
async def totp_disable(
    body: TOTPDisableRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    if not current_user.password_hash or not verify_password(body.password, current_user.password_hash):
        raise AuthenticationError("Password confirmation failed.")

    result = await session.execute(
        select(TOTPSecret).where(
            TOTPSecret.user_id == current_user.id, TOTPSecret.is_verified.is_(True)
        )
    )
    totp_rec = result.scalar_one_or_none()
    if totp_rec is None:
        raise NotFoundError("2FA is not enabled.")

    await session.delete(totp_rec)

    await _write_audit(
        session,
        action="user.totp.disabled",
        entity_type="user",
        entity_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
        actor_id=current_user.id,
        request=request,
    )


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------


@router.post("/api-keys", status_code=201)
async def create_api_key(
    body: ApiKeyCreateRequest,
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
) -> ApiKeyCreateResponse:
    full_key, prefix, key_hash = generate_api_key()
    expires_at = (
        datetime.now(UTC) + timedelta(days=body.expires_days) if body.expires_days else None
    )
    api_key = ApiKey(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        name=body.name,
        key_prefix=prefix,
        key_hash=key_hash,
        expires_at=expires_at,
    )
    session.add(api_key)
    await session.flush()

    await _write_audit(
        session,
        action="api_key.created",
        entity_type="api_key",
        entity_id=str(api_key.id),
        tenant_id=current_user.tenant_id,
        actor_id=current_user.id,
        request=request,
    )

    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        full_key=full_key,
    )


@router.get("/api-keys")
async def list_api_keys(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[ApiKeyResponse]:
    result = await session.execute(
        select(ApiKey).where(
            ApiKey.user_id == current_user.id, ApiKey.is_active.is_(True)
        )
    )
    keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            created_at=k.created_at,
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    result = await session.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise NotFoundError("API key not found.")

    api_key.is_active = False

    await _write_audit(
        session,
        action="api_key.revoked",
        entity_type="api_key",
        entity_id=str(key_id),
        tenant_id=current_user.tenant_id,
        actor_id=current_user.id,
        request=request,
    )
