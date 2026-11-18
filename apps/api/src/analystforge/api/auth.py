"""Password hashing, JWT tokens, TOTP and API key utilities."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from analystforge.api.config import Settings

_ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)

ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def create_access_token(
    *,
    subject: str,
    tenant_id: str,
    role: str,
    settings: Settings,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.access_token_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "tid": tenant_id,
        "role": role,
        "iat": now,
        "exp": expire,
        "jti": uuid.uuid4().hex,
        **(extra or {}),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    return dict(jwt.decode(token, settings.secret_key.get_secret_value(), algorithms=[ALGORITHM]))


def create_refresh_token() -> str:
    """Create a cryptographically random refresh token (opaque)."""
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    """SHA-256 hash of an opaque token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def safe_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str, issuer: str = "AnalystForge") -> str:
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


# ---------------------------------------------------------------------------
# TOTP encryption (Fernet via derived key)
# ---------------------------------------------------------------------------


def encrypt_totp_secret(raw_secret: str, settings: Settings) -> str:
    """Encrypt a TOTP secret using Fernet symmetric encryption."""
    from cryptography.fernet import Fernet

    fernet = Fernet(settings.fernet_key)
    return fernet.encrypt(raw_secret.encode()).decode()


def decrypt_totp_secret(encrypted: str, settings: Settings) -> str:
    """Decrypt a TOTP secret."""
    from cryptography.fernet import Fernet

    fernet = Fernet(settings.fernet_key)
    return fernet.decrypt(encrypted.encode()).decode()


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

API_KEY_PREFIX_LEN = 8
API_KEY_SECRET_LEN = 40


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, hash).

    full_key is shown once to the user: ``af_{prefix}_{secret}``
    """
    prefix = secrets.token_hex(API_KEY_PREFIX_LEN // 2)
    secret = secrets.token_urlsafe(API_KEY_SECRET_LEN)
    full_key = f"af_{prefix}_{secret}"
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, prefix, key_hash


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


def slugify(text: str) -> str:
    import re

    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "tenant"
