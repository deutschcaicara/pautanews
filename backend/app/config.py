"""Centralised settings — reads .env / env vars via pydantic-settings."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration for Radar Hard News, sourced from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Postgres ──
    DATABASE_URL: str = (
        "postgresql+asyncpg://radar:radar_secret@postgres:5432/radar_news"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql+psycopg2://radar:radar_secret@postgres:5432/radar_news"
    )

    # ── RabbitMQ / Celery ──
    CELERY_BROKER_URL: str = "amqp://radar:radar_secret@rabbitmq:5672//"

    # ── Redis ──
    REDIS_URL: str = "redis://redis:6379/0"

    # ── App ──
    APP_ENV: str = "development"
    APP_LOG_LEVEL: str = "INFO"
    APP_CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # ── SLOs (seconds) ──
    SLO_FAST_PATH_S: int = 60
    SLO_RENDER_PATH_S: int = 120
    SLO_DEEP_PATH_S: int = 300

    # ── QUARANTINE TTL (seconds) ──
    QUARANTINE_TTL_S: int = 900  # 15 min

    # ── Alert cooldown (seconds) ──
    ALERT_COOLDOWN_S: int = 300


settings = Settings()
