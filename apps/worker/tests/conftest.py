from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr

from analystforge.api import models  # noqa: F401
from analystforge.api.config import Settings
from analystforge.api.db import Base, Database
from analystforge.api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        debug=False,
        secret_key=SecretStr("test-secret-key-0123456789-abcdefghijklmnop"),
        database_url="sqlite+aiosqlite://",
        redis_url=None,
        log_json=False,
        data_dir=tmp_path / "var",
        upload_dir=tmp_path / "var" / "uploads",
        demo_mode=False,
        email_enabled=False,
        llm_provider="none",
    )


@pytest_asyncio.fixture
async def app(tmp_path: Path) -> AsyncIterator[FastAPI]:
    application = create_app(make_settings(tmp_path))
    async with application.router.lifespan_context(application):
        async with application.state.db.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield application


@pytest_asyncio.fixture
async def db(app: FastAPI) -> Database:
    database: Database = app.state.db
    return database
