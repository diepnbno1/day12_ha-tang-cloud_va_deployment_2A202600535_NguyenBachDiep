"""Redis-backed monthly cost guard."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from redis import RedisError

from .config import settings
from .redis_client import get_redis


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 2)


def estimate_cost_usd(input_tokens: int = 0, output_tokens: int = 0) -> float:
    input_cost = (input_tokens / 1000) * settings.price_per_1k_input_tokens
    output_cost = (output_tokens / 1000) * settings.price_per_1k_output_tokens
    return round(input_cost + output_cost, 8)


def _budget_key(user_id: str) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"budget:{user_id}:{month}"


def get_usage(user_id: str) -> dict[str, float | str]:
    key = _budget_key(user_id)
    redis_client = get_redis()
    try:
        used = float(redis_client.get(key) or 0.0)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable") from exc

    return {
        "user_id": user_id,
        "month": key.rsplit(":", 1)[-1],
        "used_usd": round(used, 6),
        "budget_usd": settings.monthly_budget_usd,
        "remaining_usd": round(max(0.0, settings.monthly_budget_usd - used), 6),
    }


def check_and_record_cost(user_id: str, estimated_cost: float) -> dict[str, float | str]:
    key = _budget_key(user_id)
    redis_client = get_redis()

    try:
        current = float(redis_client.get(key) or 0.0)
        if current + estimated_cost > settings.monthly_budget_usd:
            raise HTTPException(
                status_code=402,
                detail={
                    "error": "Monthly budget exceeded",
                    "used_usd": round(current, 6),
                    "attempted_usd": round(estimated_cost, 6),
                    "budget_usd": settings.monthly_budget_usd,
                    "resets": key.rsplit(":", 1)[-1],
                },
            )

        new_total = float(redis_client.incrbyfloat(key, estimated_cost))
        redis_client.expire(key, 32 * 24 * 3600)
    except HTTPException:
        raise
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable") from exc

    return {
        "user_id": user_id,
        "month": key.rsplit(":", 1)[-1],
        "used_usd": round(new_total, 6),
        "budget_usd": settings.monthly_budget_usd,
        "remaining_usd": round(max(0.0, settings.monthly_budget_usd - new_total), 6),
    }
