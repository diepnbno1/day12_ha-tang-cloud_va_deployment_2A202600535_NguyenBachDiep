"""Redis-backed sliding-window rate limiter."""

from __future__ import annotations

import time
import uuid

from fastapi import HTTPException
from redis import RedisError

from .config import settings
from .redis_client import get_redis


WINDOW_SECONDS = 60


def check_rate_limit(user_id: str, role: str = "user") -> dict[str, int]:
    limit = (
        settings.admin_rate_limit_per_minute
        if role == "admin"
        else settings.rate_limit_per_minute
    )
    now = time.time()
    key = f"rate:{user_id}"
    redis_client = get_redis()

    try:
        redis_client.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
        current = int(redis_client.zcard(key))

        if current >= limit:
            oldest = redis_client.zrange(key, 0, 0, withscores=True)
            retry_after = WINDOW_SECONDS
            if oldest:
                retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "window_seconds": WINDOW_SECONDS,
                    "retry_after_seconds": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        redis_client.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
        redis_client.expire(key, WINDOW_SECONDS + 5)
        return {"limit": limit, "remaining": max(0, limit - current - 1), "reset_seconds": WINDOW_SECONDS}
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Rate limiter storage unavailable") from exc
