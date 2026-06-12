"""Production-ready AI agent for Day 12 Lab."""

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from redis import RedisError
import uvicorn

from app.auth import Principal, authenticate_demo_user, create_access_token, verify_auth
from app.config import settings
from app.cost_guard import check_and_record_cost, estimate_cost_usd, estimate_tokens, get_usage
from app.rate_limiter import check_rate_limit
from app.redis_client import get_redis, redis_ping
from utils.mock_llm import ask as llm_ask


# api_key authentication is implemented in app.auth.verify_auth.
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
INSTANCE_ID = f"agent-{int(START_TIME)}"
_is_ready = False
_request_count = 0
_error_count = 0


def log_event(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, separators=(",", ":")))


def _history_key(user_id: str) -> str:
    return f"history:{user_id}"


def load_history(user_id: str, limit: int | None = None) -> list[dict[str, str]]:
    redis_client = get_redis()
    max_items = limit or settings.history_max_messages
    try:
        raw_messages = redis_client.lrange(_history_key(user_id), -max_items, -1)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Conversation storage unavailable") from exc
    messages: list[dict[str, str]] = []
    for raw in raw_messages:
        try:
            messages.append(json.loads(raw))
        except json.JSONDecodeError:
            logger.warning("Skipping invalid history entry for user_id=%s", user_id)
    return messages


def append_history(user_id: str, role: str, content: str) -> None:
    redis_client = get_redis()
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    key = _history_key(user_id)
    pipe = redis_client.pipeline()
    pipe.rpush(key, json.dumps(message, separators=(",", ":")))
    pipe.ltrim(key, -settings.history_max_messages, -1)
    pipe.expire(key, settings.history_ttl_seconds)
    try:
        pipe.execute()
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Conversation storage unavailable") from exc


def answer_with_history(question: str, history: list[dict[str, str]]) -> str:
    question_lower = question.lower()
    if "what is my name" in question_lower or "what's my name" in question_lower:
        for message in reversed(history):
            if message.get("role") != "user":
                continue
            match = re.search(r"\bmy name is ([A-Za-z][A-Za-z0-9_-]*)", message.get("content", ""), re.I)
            if match:
                return f"You told me your name is {match.group(1)}."

    return llm_ask(question)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    log_event(
        "startup",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        instance_id=INSTANCE_ID,
    )
    _is_ready = redis_ping()
    if not _is_ready:
        logger.error("Redis is not reachable; readiness will fail until Redis is available")

    yield

    _is_ready = False
    # Uvicorn handles SIGTERM; this lifespan block performs graceful cleanup.
    log_event("graceful_shutdown", instance_id=INSTANCE_ID)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    started = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
    except Exception:
        _error_count += 1
        log_event("request_error", method=request.method, path=request.url.path)
        raise

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if "server" in response.headers:
        del response.headers["server"]
    log_event(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round((time.time() - started) * 1000, 1),
    )
    return response


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class AskRequest(BaseModel):
    user_id: str = Field("anonymous", min_length=1, max_length=128)
    question: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    user_id: str
    question: str
    answer: str
    model: str
    history_messages: int
    usage: dict[str, float | str]
    rate_limit: dict[str, int]
    timestamp: str


@app.get("/", tags=["Info"])
def root() -> dict[str, Any]:
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "storage": "redis",
        "endpoints": {
            "health": "GET /health",
            "ready": "GET /ready",
            "ask": "POST /ask",
            "stream": "POST /ask/stream",
            "token": "POST /auth/token",
        },
    }


@app.post("/auth/token", response_model=TokenResponse, tags=["Auth"])
def issue_token(body: LoginRequest) -> TokenResponse:
    principal = authenticate_demo_user(body.username, body.password)
    token = create_access_token(principal.subject, principal.role)
    return TokenResponse(access_token=token, expires_in_minutes=settings.jwt_expire_minutes)


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
def ask_agent(body: AskRequest, request: Request, principal: Principal = Depends(verify_auth)) -> AskResponse:
    rate_info = check_rate_limit(body.user_id, principal.role)

    history = load_history(body.user_id)
    input_tokens = estimate_tokens(body.question)
    check_and_record_cost(body.user_id, estimate_cost_usd(input_tokens=input_tokens))

    append_history(body.user_id, "user", body.question)
    answer = answer_with_history(body.question, history)
    append_history(body.user_id, "assistant", answer)

    output_tokens = estimate_tokens(answer)
    usage = check_and_record_cost(body.user_id, estimate_cost_usd(output_tokens=output_tokens))

    log_event(
        "agent_call",
        user_id=body.user_id,
        auth_method=principal.auth_method,
        role=principal.role,
        question_chars=len(body.question),
        client=str(request.client.host) if request.client else "unknown",
    )

    return AskResponse(
        user_id=body.user_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        history_messages=len(history) + 2,
        usage=usage,
        rate_limit=rate_info,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/ask/stream", tags=["Agent"])
def stream_agent(body: AskRequest, principal: Principal = Depends(verify_auth)) -> StreamingResponse:
    check_rate_limit(body.user_id, principal.role)
    history = load_history(body.user_id)
    input_tokens = estimate_tokens(body.question)
    check_and_record_cost(body.user_id, estimate_cost_usd(input_tokens=input_tokens))
    append_history(body.user_id, "user", body.question)
    answer = answer_with_history(body.question, history)

    def token_stream() -> Generator[str, None, None]:
        for word in answer.split():
            yield word + " "
            time.sleep(0.03)
        append_history(body.user_id, "assistant", answer)
        output_tokens = estimate_tokens(answer)
        check_and_record_cost(body.user_id, estimate_cost_usd(output_tokens=output_tokens))

    return StreamingResponse(token_stream(), media_type="text/plain")


@app.get("/history/{user_id}", tags=["Agent"])
def history(user_id: str, _principal: Principal = Depends(verify_auth)) -> dict[str, Any]:
    messages = load_history(user_id)
    return {"user_id": user_id, "messages": messages, "count": len(messages)}


@app.delete("/history/{user_id}", tags=["Agent"])
def delete_history(user_id: str, _principal: Principal = Depends(verify_auth)) -> dict[str, str]:
    get_redis().delete(_history_key(user_id))
    return {"deleted": user_id}


@app.get("/usage/{user_id}", tags=["Operations"])
def usage(user_id: str, _principal: Principal = Depends(verify_auth)) -> dict[str, float | str]:
    return get_usage(user_id)


@app.get("/health", tags=["Operations"])
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready() -> dict[str, Any]:
    global _is_ready
    _is_ready = redis_ping()
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Redis is not ready")
    return {"ready": True, "storage": "redis", "instance_id": INSTANCE_ID}


@app.get("/metrics", tags=["Operations"])
def metrics(_principal: Principal = Depends(verify_auth)) -> dict[str, Any]:
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "monthly_budget_usd": settings.monthly_budget_usd,
    }


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
