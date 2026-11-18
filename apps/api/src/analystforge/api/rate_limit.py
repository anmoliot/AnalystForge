"""Shared fixed-window quotas with a bounded single-process fallback."""

from __future__ import annotations

import math
import time
from collections import OrderedDict

from fastapi import Request
from redis.asyncio import Redis

from analystforge.api.deps import CurrentUserOptional, SettingsDep
from analystforge.api.errors import RateLimitError
from analystforge.api.logging import get_logger

logger = get_logger("rate_limit")
_INCREMENT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], 60) end
return {count, redis.call('TTL', KEYS[1])}
"""


class RateLimiter:
    def __init__(self, redis: Redis | None) -> None:
        self.redis = redis
        self.retry_redis_at = 0.0
        self.windows: OrderedDict[str, tuple[float, int]] = OrderedDict()

    async def check(self, key: str, limit: int) -> None:
        now = time.monotonic()
        if self.redis is not None and now >= self.retry_redis_at:
            try:
                count, ttl = await self.redis.eval(_INCREMENT, 1, "af:limit:" + key)
                retry = max(1, int(ttl)) if int(count) > limit else 0
            except Exception as exc:
                self.retry_redis_at = now + 5
                logger.warning("rate_limit.local_fallback", reason=type(exc).__name__)
            else:
                if retry:
                    raise RateLimitError(retry)
                return
        # No await in this section. Each event-loop process updates its counters atomically.
        now = time.monotonic()
        while self.windows and next(iter(self.windows.values()))[0] <= now:
            self.windows.popitem(last=False)
        if key not in self.windows and len(self.windows) >= 65536:
            raise RateLimitError(max(1, math.ceil(next(iter(self.windows.values()))[0] - now)))
        expires, count = self.windows.get(key, (now + 60, 0))
        if count >= limit:
            raise RateLimitError(max(1, math.ceil(expires - now)))
        self.windows[key] = expires, count + 1


async def enforce_rate_limit(
    request: Request, user: CurrentUserOptional, settings: SettingsDep
) -> None:
    auth_write = request.method != "GET" and request.url.path.startswith("/api/v1/auth/")
    limit = settings.rate_limit_auth_per_minute if auth_write else settings.rate_limit_per_minute
    identity = "ip:" + (request.client.host if request.client else "unknown")
    if user is not None and (not auth_write or request.url.path.endswith("/api-keys")):
        key_id = getattr(request.state, "api_key_id", None)
        identity = f"key:{key_id}" if key_id else f"user:{user.id}"
    bucket = "auth" if auth_write else "api"
    await request.app.state.rate_limiter.check(f"{bucket}:{identity}", limit)
