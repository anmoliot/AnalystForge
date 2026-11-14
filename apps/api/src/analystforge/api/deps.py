"""FastAPI dependency injectors: DB session, settings, current user, RBAC."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Annotated

from fastapi import Cookie, Depends, Header, Request
import jwt
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analystforge.api.auth import decode_access_token, hash_api_key
from analystforge.api.config import Settings
from analystforge.api.db import Database
from analystforge.api.errors import AuthenticationError, PermissionDeniedError
from analystforge.api.models.core import ApiKey, Tenant, User


class Role(StrEnum):
    ADMIN = "ADMIN"
    PORTFOLIO_MANAGER = "PORTFOLIO_MANAGER"
    ANALYST = "ANALYST"
    READ_ONLY = "READ_ONLY"


_ROLE_RANK: dict[str, int] = {
    Role.ADMIN: 40,
    Role.PORTFOLIO_MANAGER: 30,
    Role.ANALYST: 20,
    Role.READ_ONLY: 10,
}


def _rank(role: str) -> int:
    return _ROLE_RANK.get(role, 0)


# ---------------------------------------------------------------------------
# DB / Settings helpers
# ---------------------------------------------------------------------------


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    db: Database = request.app.state.db
    async with db.session() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Auth extraction
# ---------------------------------------------------------------------------


async def _user_from_bearer(
    request: Request,
    authorization: str | None,
    session: AsyncSession,
    settings: Settings,
) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]

    # Try API key first (prefix: af_)
    if token.startswith("af_"):
        key_hash = hash_api_key(token)
        result = await session.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        )
        api_key = result.scalar_one_or_none()
        if api_key is None:
            return None
        from datetime import UTC, datetime

        if api_key.expires_at is not None:
            expires_at = api_key.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at < datetime.now(UTC):
                return None
        # Update last_used_at without triggering a full commit cycle issue
        api_key.last_used_at = datetime.now(UTC)
        user_result = await session.execute(select(User).where(User.id == api_key.user_id))
        user = user_result.scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        return user

    # JWT access token
    try:
        payload = decode_access_token(token, settings)
    except PyJWTError:
        return None
    sub = payload.get("sub")
    if not sub:
        return None
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        return None
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    user = await _user_from_bearer(request, authorization, session, settings)
    if user is None:
        raise AuthenticationError("Authentication required.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    return await _user_from_bearer(request, authorization, session, settings)


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


def require_role(minimum_role: Role):  # type: ignore[no-untyped-def]
    """Dependency factory that enforces a minimum role level."""

    async def _check(user: CurrentUser) -> User:
        if _rank(user.role) < _rank(minimum_role):
            raise PermissionDeniedError(
                f"This action requires the '{minimum_role}' role or higher."
            )
        return user

    return Depends(_check)


async def get_tenant(user: CurrentUser, session: SessionDep) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one_or_none()
    if tenant is None or not tenant.is_active:
        raise AuthenticationError("Tenant not found or inactive.")
    return tenant


TenantDep = Annotated[Tenant, Depends(get_tenant)]
