from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest_asyncio
from pydantic import SecretStr

from analystforge.api.config import Settings
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
async def client(tmp_path: Path) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(tmp_path))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            yield http
