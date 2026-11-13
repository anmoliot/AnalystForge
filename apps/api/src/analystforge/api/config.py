"""Typed configuration validated at startup.

Environment variables are the only configuration source. Missing or unsafe
production settings fail loudly with an actionable message rather than silently
falling back to an insecure default.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(RuntimeError):
    """Raised when configuration is unusable; message is shown to operators."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AnalystForge"
    version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    port: int = 8000
    public_base_url: str = "http://localhost:8080"

    secret_key: SecretStr
    encryption_key: SecretStr | None = None
    database_url: str
    redis_url: str | None = None

    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    cookie_secure: bool = False
    cookie_domain: str | None = None

    access_token_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_days: int = Field(default=30, ge=1, le=365)
    max_login_attempts: int = Field(default=5, ge=1, le=100)
    login_lockout_minutes: int = Field(default=15, ge=1)

    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    google_redirect_url: str = "http://localhost:8000/api/v1/auth/oauth/google/callback"

    sec_user_agent: str = "AnalystForge/0.1 (contact@example.com)"
    fred_api_key: SecretStr | None = None
    alphavantage_api_key: SecretStr | None = None
    twelvedata_api_key: SecretStr | None = None
    polygon_api_key: SecretStr | None = None
    fmp_api_key: SecretStr | None = None
    newsapi_api_key: SecretStr | None = None

    price_providers: str = "yahoo,stooq"
    news_rss_feeds: str = (
        "https://www.sec.gov/news/pressreleases.rss,"
        "https://www.federalreserve.gov/feeds/press_all.xml,"
        "https://www.ecb.europa.eu/rss/press.html"
    )
    provider_cooldown_seconds: float = Field(default=300.0, ge=0, le=3600)
    price_history_years: int = Field(default=10, ge=1, le=30)

    llm_provider: Literal["none", "anthropic", "openai"] = "anthropic"
    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = Field(default=1200, ge=128, le=8192)
    finbert_enabled: bool = False
    finbert_model: str = "ProsusAI/finbert"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    email_enabled: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "AnalystForge <alerts@analystforge.local>"
    smtp_tls: bool = False

    sentry_dsn: str | None = None
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None
    log_level: str = "INFO"
    log_json: bool = True

    demo_mode: bool = False
    data_dir: Path = Path("./var")
    max_upload_mb: int = Field(default=25, ge=1, le=500)
    upload_dir: Path = Path("./var/uploads")
    http_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @field_validator("secret_key")
    @classmethod
    def _secret_key_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. "
                'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return value

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return normalized

    @model_validator(mode="after")
    def _production_hardening(self) -> Settings:
        if self.environment != "production":
            return self
        problems: list[str] = []
        if not self.database_url.startswith(("postgresql+asyncpg://", "postgresql://")):
            problems.append("DATABASE_URL must be a PostgreSQL URL in production")
        if not self.redis_url:
            problems.append("REDIS_URL is required in production (jobs, cache, rate limiting)")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS must not be '*' in production")
        if self.debug:
            problems.append("DEBUG must be false in production")
        if not self.encryption_key:
            problems.append(
                "ENCRYPTION_KEY is required in production to encrypt TOTP secrets at rest"
            )
        if self.demo_mode:
            problems.append("DEMO_MODE must be false in production")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def price_provider_list(self) -> list[str]:
        return [item.strip() for item in self.price_providers.split(",") if item.strip()]

    @property
    def news_feed_list(self) -> list[str]:
        return [item.strip() for item in self.news_rss_feeds.split(",") if item.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def fernet_key(self) -> bytes:
        """Explicit encryption key, or one deterministically derived in dev/test."""
        if self.encryption_key:
            return self.encryption_key.get_secret_value().encode()
        if self.is_production:  # pragma: no cover - blocked by validator
            raise ConfigError("ENCRYPTION_KEY is required in production")
        digest = hashlib.sha256(self.secret_key.get_secret_value().encode()).digest()
        return base64.urlsafe_b64encode(digest)

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def provider_key(self, name: str) -> str | None:
        keys = {
            "fred": self.fred_api_key,
            "alphavantage": self.alphavantage_api_key,
            "twelvedata": self.twelvedata_api_key,
            "polygon": self.polygon_api_key,
            "fmp": self.fmp_api_key,
            "newsapi": self.newsapi_api_key,
            "anthropic": self.anthropic_api_key,
        }
        value = keys.get(name)
        return value.get_secret_value() if value else None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except Exception as exc:  # pydantic ValidationError is verbose; surface guidance
        raise ConfigError(
            "AnalystForge cannot start because configuration is invalid.\n"
            f"{exc}\n\n"
            "Copy .env.example to .env, fill in required values, or run `make env` "
            "to generate secure development secrets."
        ) from exc
