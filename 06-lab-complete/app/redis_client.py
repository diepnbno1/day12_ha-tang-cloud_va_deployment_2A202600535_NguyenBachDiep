"""Shared Redis connection helpers."""

from __future__ import annotations

import redis

from .config import settings


_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def get_redis() -> redis.Redis:
    return _redis


def redis_ping() -> bool:
    try:
        return bool(_redis.ping())
    except redis.RedisError:
        return False
