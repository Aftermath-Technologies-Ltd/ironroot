# Author: Bradley R. Kinnard
"""application settings with strict validation."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default password shipped in .env.example. Refused in non-debug mode.
INSECURE_DEFAULT_PASSWORDS: frozenset[str] = frozenset({"", "changeme", "password", "postgres"})


class Settings(BaseSettings):
    """centralized config, loaded from env vars with IRONROOT_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="IRONROOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Allow non-IRONROOT_ vars in .env
    )

    # api
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = Field(default=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # postgres
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = Field(default="ironroot")
    db_user: str = Field(default="ironroot")
    db_password: str = Field(default="changeme")

    # redis
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379, ge=1, le=65535)
    redis_db: int = Field(default=0, ge=0, le=15)

    # artifact store
    artifact_store: Literal["local", "s3"] = Field(default="local")
    artifact_path: Path = Field(default=Path("./artifacts"))

    # optional s3
    s3_endpoint: str | None = Field(default=None)
    s3_bucket: str | None = Field(default=None)
    s3_access_key: str | None = Field(default=None)
    s3_secret_key: str | None = Field(default=None)

    # CORS allowlist used in non-debug mode. Debug mode is hard-coded to a
    # bounded set of `http://localhost:*` origins (see cors_allowed_origins).
    # Empty list in production means "deny all cross-origin requests".
    cors_origins: list[str] = Field(default_factory=list)

    # Phase 3.4: API token authentication on /api/v1/*.
    #
    # `auth_enabled` defaults to False in debug mode (so the local
    # test suite and dev loop keep working) and True in non-debug.
    # Operators can flip the flag explicitly via
    # `IRONROOT_AUTH_ENABLED=true|false`.
    #
    # `auth_rate_limit_per_minute` caps the per-token request rate
    # against the auth dependency. Zero disables limiting. The
    # in-process limiter is "good enough" for v1 — production
    # deploys are expected to put a real rate limiter at the edge
    # (nginx, Cloudflare). The setting exists so the limit is at
    # least visible from one place.
    auth_enabled: bool | None = Field(default=None)
    auth_rate_limit_per_minute: int = Field(default=600, ge=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow comma-separated origin lists from env vars."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @model_validator(mode="after")
    def _reject_insecure_password_in_prod(self) -> "Settings":
        """Refuse to start in non-debug mode with a default/empty DB password.

        The project ships `IRONROOT_DB_PASSWORD=changeme` in .env.example as
        an explicit demo placeholder. Allowing that value to reach a
        production deploy was the documented anti-pattern. This validator
        makes the failure happen at import time, not at first request.
        """
        if not self.debug and self.db_password in INSECURE_DEFAULT_PASSWORDS:
            raise ValueError(
                "refusing to start: IRONROOT_DB_PASSWORD is empty or one of "
                f"the known-insecure defaults ({sorted(INSECURE_DEFAULT_PASSWORDS)!r}). "
                "Set a real password, or run with IRONROOT_DEBUG=true for local "
                "development."
            )
        return self

    @property
    def auth_required(self) -> bool:
        """Resolved auth-required flag.

        Defaults: in non-debug mode auth is required; in debug mode it
        is optional. Operators can override either way via
        ``IRONROOT_AUTH_ENABLED``.
        """
        if self.auth_enabled is None:
            return not self.debug
        return self.auth_enabled

    @property
    def database_url(self) -> str:
        """async postgres connection string."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def sync_database_url(self) -> str:
        """sync postgres connection string for migrations."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_url(self) -> str:
        """redis connection string."""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def cors_allowed_origins(self) -> list[str]:
        """Origins permitted by the CORS middleware.

        In debug mode this is the explicit set of `http://localhost:<port>`
        origins that local frontends typically run on. In non-debug mode
        the result is the operator-supplied `IRONROOT_CORS_ORIGINS` list
        (empty by default → deny all cross-origin requests).

        Important: never return `["*"]` together with `allow_credentials=True`
        — that combination is rejected by the browser fetch spec.
        """
        if self.debug:
            return [
                "http://localhost",
                "http://localhost:3000",
                "http://localhost:5173",
                "http://localhost:8000",
                "http://localhost:8080",
                "http://127.0.0.1",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:8000",
                "http://127.0.0.1:8080",
            ]
        return list(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    """cached settings instance, validates on first access."""
    return Settings()
