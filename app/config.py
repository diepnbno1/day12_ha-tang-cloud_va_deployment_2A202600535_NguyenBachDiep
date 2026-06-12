"""12-factor configuration loaded only from environment variables."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "*") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG"))

    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Production AI Agent"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "mock-llm"))

    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", "dev-key-change-me"))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "dev-jwt-secret"))
    jwt_expire_minutes: int = field(default_factory=lambda: int(os.getenv("JWT_EXPIRE_MINUTES", "60")))
    demo_username: str = field(default_factory=lambda: os.getenv("DEMO_USERNAME", "admin"))
    demo_password: str = field(default_factory=lambda: os.getenv("DEMO_PASSWORD", "secret"))
    allowed_origins: list[str] = field(default_factory=lambda: _env_list("ALLOWED_ORIGINS"))

    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))
    admin_rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("ADMIN_RATE_LIMIT_PER_MINUTE", "100"))
    )

    monthly_budget_usd: float = field(default_factory=lambda: float(os.getenv("MONTHLY_BUDGET_USD", "10.0")))
    price_per_1k_input_tokens: float = field(
        default_factory=lambda: float(os.getenv("PRICE_PER_1K_INPUT_TOKENS", "0.00015"))
    )
    price_per_1k_output_tokens: float = field(
        default_factory=lambda: float(os.getenv("PRICE_PER_1K_OUTPUT_TOKENS", "0.0006"))
    )

    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    history_max_messages: int = field(default_factory=lambda: int(os.getenv("HISTORY_MAX_MESSAGES", "20")))
    history_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("HISTORY_TTL_SECONDS", "2592000")))

    def validate(self) -> "Settings":
        logger = logging.getLogger(__name__)
        if self.environment == "production":
            if self.agent_api_key == "dev-key-change-me":
                raise ValueError("AGENT_API_KEY must be set in production")
            if self.jwt_secret == "dev-jwt-secret":
                raise ValueError("JWT_SECRET must be set in production")
            if self.demo_password == "secret":
                logger.warning("DEMO_PASSWORD should be changed or login disabled in production")
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY is not set; using the local mock LLM")
        return self


settings = Settings().validate()
