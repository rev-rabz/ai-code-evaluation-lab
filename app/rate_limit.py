import hashlib
import hmac
import os
import time
from functools import lru_cache
from typing import Any

from fastapi import Depends, HTTPException, Request, Response
from redis import Redis
from redis.exceptions import RedisError

from app.auth import get_current_user
from app.models import User

_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


@lru_cache(maxsize=1)
def get_redis() -> Redis:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
        health_check_interval=30,
    )


def _rate_limit_key(scope: str, identity: str, window_seconds: int, now: float | None = None) -> str:
    secret = os.getenv("RATE_LIMIT_KEY_SECRET") or os.getenv("JWT_SECRET") or "development-only-rate-limit-key"
    digest = hmac.new(secret.encode(), f"{scope}:{identity}".encode(), hashlib.sha256).hexdigest()
    bucket = int((time.time() if now is None else now) // window_seconds)
    return f"rate-limit:{scope}:{digest}:{bucket}"


def enforce_rate_limit(redis_client: Any, scope: str, identity: str, limit: int, window_seconds: int) -> dict[str, str]:
    key = _rate_limit_key(scope, identity, window_seconds)
    try:
        result = redis_client.eval(_RATE_LIMIT_SCRIPT, 1, key, window_seconds)
        count, ttl = int(result[0]), int(result[1])
    except (RedisError, OSError, TypeError, ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Rate limiting is temporarily unavailable. Please retry shortly.",
        ) from exc

    reset_seconds = max(1, ttl if ttl > 0 else window_seconds)
    remaining = max(0, limit - count)
    headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(reset_seconds),
    }
    if count > limit:
        headers["Retry-After"] = str(reset_seconds)
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please retry after the rate limit window.",
            headers=headers,
        )
    return headers


def ip_rate_limit(scope: str, limit: int, window_seconds: int):
    def dependency(request: Request, response: Response, redis_client: Redis = Depends(get_redis)) -> None:
        # Forwarded headers are ignored until explicit trusted-proxy support is configured.
        identity = request.client.host if request.client is not None else "unknown"
        response.headers.update(enforce_rate_limit(redis_client, scope, identity, limit, window_seconds))

    return dependency


def user_rate_limit(scope: str, limit: int, window_seconds: int):
    def dependency(
        response: Response,
        current_user: User = Depends(get_current_user),
        redis_client: Redis = Depends(get_redis),
    ) -> None:
        response.headers.update(enforce_rate_limit(redis_client, scope, str(current_user.id), limit, window_seconds))

    return dependency
