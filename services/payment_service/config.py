"""
config.py — payment-service configuration

All settings are loaded from environment variables (or .env file).
No passwords or secrets are ever hard-coded here.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Reads configuration from environment variables.
    Prefix all variables with PAYMENT_ to avoid collisions between services.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",           # ignore unrelated env vars
    )

    # ── Service identity ──────────────────────────────────────────────────
    service_name: str = "payment-service"
    service_port: int = 8001
    log_level: str = "INFO"

    # ── PostgreSQL ────────────────────────────────────────────────────────
    # Example: postgresql://postgres:postgres@postgres:5432/healthcheck
    payment_db_url: str = "postgresql://postgres:postgres@postgres:5432/healthcheck"

    # ── Redis ─────────────────────────────────────────────────────────────
    # Example: redis://redis:6379/0
    payment_redis_url: str = "redis://redis:6379/0"

    # ── Readiness probe timeouts (seconds) ────────────────────────────────
    db_connect_timeout: float = 0.5
    redis_connect_timeout: float = 0.5


# Module-level singleton — import this everywhere
settings = Settings()
