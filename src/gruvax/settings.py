"""Application settings loaded from environment / .env file.

All configuration is validated at startup via pydantic-settings; a missing or
malformed value crashes boot rather than surfacing at request time.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """GRUVAX runtime configuration.

    Values are read from environment variables (case-insensitive) and from
    the ``.env`` file in the project root (lower precedence than env vars).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Database ─────────────────────────────────────────────────────────────
    # SQLAlchemy / Alembic async form: postgresql+psycopg://user:pass@host/db
    DATABASE_URL: str

    # The discogsography schema visible through gruvax.v_collection.
    # Dev/CI: "gruvax_dev" (synthetic tables).  Prod: "discogsography".
    OBSERVED_DISCOGSOGRAPHY_SCHEMA: str = "gruvax_dev"

    # ── MQTT ─────────────────────────────────────────────────────────────────
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = "gruvax"
    MQTT_PASSWORD: str = "gruvax"

    # ── Admin auth (Phase 3) ──────────────────────────────────────────────────
    # SESSION_SECRET has no default — a missing value crashes at startup rather
    # than silently using an insecure shared default (mirrors DATABASE_URL pattern,
    # T-03-01 mitigation).
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    SESSION_SECRET: str

    # Sliding idle TTL for admin sessions in seconds (D-04, default 10 min).
    SESSION_TTL_SECONDS: int = 600

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"


# Module-level singleton — import this everywhere.
settings = Settings()
