from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from analystforge.api.config import Settings


def base_kwargs(tmp_path: Path) -> dict[str, object]:
    return {
        "_env_file": None,
        "secret_key": SecretStr("x" * 40),
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "environment": "production",
        "cookie_secure": True,
        "data_dir": tmp_path / "var",
        "upload_dir": tmp_path / "var" / "uploads",
        "encryption_key": SecretStr("MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="),
    }


def test_production_rejects_sqlite(tmp_path: Path) -> None:
    kwargs = base_kwargs(tmp_path)
    kwargs["database_url"] = "sqlite+aiosqlite:///local.db"
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_production_requires_redis(tmp_path: Path) -> None:
    kwargs = base_kwargs(tmp_path)
    kwargs["redis_url"] = None
    with pytest.raises(ValidationError, match="REDIS_URL"):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_production_requires_secure_cookies(tmp_path: Path) -> None:
    kwargs = base_kwargs(tmp_path)
    kwargs["cookie_secure"] = False
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_production_rejects_demo_mode(tmp_path: Path) -> None:
    kwargs = base_kwargs(tmp_path)
    kwargs["demo_mode"] = True
    with pytest.raises(ValidationError, match="DEMO_MODE"):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_short_secret_is_rejected(tmp_path: Path) -> None:
    kwargs = base_kwargs(tmp_path)
    kwargs["secret_key"] = SecretStr("short")
    kwargs["environment"] = "development"
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_development_derives_encryption_key(tmp_path: Path) -> None:
    kwargs = base_kwargs(tmp_path)
    kwargs["environment"] = "development"
    kwargs["encryption_key"] = None
    kwargs["cookie_secure"] = False
    settings = Settings(**kwargs)  # type: ignore[arg-type]
    assert len(settings.fernet_key) == 44


def test_cors_origins_are_parsed(tmp_path: Path) -> None:
    kwargs = base_kwargs(tmp_path)
    kwargs["environment"] = "development"
    kwargs["cookie_secure"] = False
    kwargs["cors_origins"] = "http://a.test, http://b.test"
    settings = Settings(**kwargs)  # type: ignore[arg-type]
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]
