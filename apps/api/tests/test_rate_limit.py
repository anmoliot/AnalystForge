from unittest.mock import AsyncMock

import pytest

from analystforge.api.errors import RateLimitError
from analystforge.api.rate_limit import RateLimiter


async def test_local_window_expires(monkeypatch):
    limiter = RateLimiter(None)
    with monkeypatch.context() as patch:
        # Patch the module clock without changing asyncio's clock.
        from types import SimpleNamespace

        clock = SimpleNamespace(monotonic=lambda: 100.0)
        patch.setattr("analystforge.api.rate_limit.time", clock)
        await limiter.check("one", 1)
        with pytest.raises(RateLimitError) as exc:
            await limiter.check("one", 1)
        assert exc.value.retry_after == 60
        await limiter.check("two", 1)
        clock.monotonic = lambda: 160.0
        await limiter.check("one", 1)


async def test_shared_redis_response():
    redis = AsyncMock()
    redis.eval.side_effect = [(1, 60), (2, 43)]
    limiter = RateLimiter(redis)
    await limiter.check("user:123", 1)
    with pytest.raises(RateLimitError) as exc:
        await limiter.check("user:123", 1)
    assert exc.value.retry_after == 43
    assert not limiter.windows


async def test_auth_limit_when_redis_fails(client, app):
    app.state.settings.rate_limit_auth_per_minute = 1
    redis = AsyncMock()
    app.state.rate_limiter.redis = redis
    redis.eval.side_effect = ConnectionError()
    assert (await client.post("/api/v1/auth/refresh")).status_code == 401
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 60
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    assert response.json()["error"]["code"] == "rate_limited"
    assert (await client.get("/api/v1/meta")).status_code == 200
    assert redis.eval.await_count == 1


async def test_api_keys_have_independent_limits(client, app):
    account = {"email": "limiter@example.com", "password": "TestAccount123"}
    assert (
        await client.post(
            "/api/v1/auth/register",
            json={
                **account,
                "full_name": "Tester",
                "tenant_name": "Limiter Test",
            },
        )
    ).status_code == 201
    login = await client.post("/api/v1/auth/login", json=account)
    auth = {"Authorization": "Bearer " + login.json()["access_token"]}
    keys = []
    for name in ("first", "second"):
        response = await client.post("/api/v1/auth/api-keys", headers=auth, json={"name": name})
        assert response.status_code == 201
        keys.append({"Authorization": "Bearer " + response.json()["full_key"]})
    app.state.settings.rate_limit_per_minute = 1
    for headers in keys:
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 429
