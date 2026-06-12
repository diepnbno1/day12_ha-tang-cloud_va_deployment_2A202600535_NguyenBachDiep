"""API key and optional JWT authentication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from .config import settings


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_auth = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    auth_method: str


def create_access_token(username: str, role: str = "admin") -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def authenticate_demo_user(username: str, password: str) -> Principal:
    if username != settings.demo_username or password != settings.demo_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return Principal(subject=username, role="admin", auth_method="password")


def _verify_bearer(credentials: HTTPAuthorizationCredentials) -> Principal:
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="JWT token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=403, detail="Invalid JWT token") from exc

    return Principal(
        subject=str(payload.get("sub", "unknown")),
        role=str(payload.get("role", "user")),
        auth_method="jwt",
    )


def verify_auth(
    x_api_key: str | None = Security(api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_auth),
) -> Principal:
    if x_api_key:
        if x_api_key != settings.agent_api_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return Principal(subject="api-key-user", role="user", auth_method="api_key")

    if credentials:
        return _verify_bearer(credentials)

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Send X-API-Key or Authorization: Bearer <token>",
        headers={"WWW-Authenticate": "Bearer"},
    )
