"""Application settings loaded from environment / .env file.

All configuration is validated at startup via pydantic-settings; a missing or
malformed value crashes boot rather than surfacing at request time.
"""

from pydantic import SecretStr, field_validator
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

    # ── discogsography integration (P1, D-18) ────────────────────────────────
    # No default — missing value crashes boot (mirrors DATABASE_URL convention).
    # Prod = http://discogsography-api:8004; dev compose = http://fake-discogsography:8004.
    DISCOGSOGRAPHY_BASE_URL: str

    # ── MQTT ─────────────────────────────────────────────────────────────────
    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = "gruvax"
    # Empty default = anonymous; real deployments override via env / .env / compose.yaml.
    # Mirrors compose.yaml ``${MQTT_PASSWORD:-}`` substitution.
    MQTT_PASSWORD: str = ""
    # Topic prefix separates dev and prod retained messages (D-14, Pitfall 3).
    # Dev: "gruvax/v1/dev/leds"  Prod: "gruvax/v1/leds"
    MQTT_TOPIC_PREFIX: str = "gruvax/v1/dev/leds"
    # Default retained-state expiry in seconds (D-12 — 4h default, "no expiry" rejected).
    MQTT_STATE_EXPIRY_SECONDS: int = 14400  # 4 * 3600

    # ── Admin auth (Phase 3) ──────────────────────────────────────────────────
    # SESSION_SECRET has no default — a missing value crashes at startup rather
    # than silently using an insecure shared default (mirrors DATABASE_URL pattern,
    # T-03-01 mitigation).
    # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
    SESSION_SECRET: str

    # Sliding idle TTL for admin sessions in seconds (D-04, default 10 min).
    SESSION_TTL_SECONDS: int = 600

    # ── Fernet encryption for PAT-at-rest (P1, D-01) ─────────────────────────
    # URL-safe base64-encoded 32 random bytes. No default — boot fails with a
    # clear pydantic ValidationError when missing or malformed. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # ``SecretStr`` hides the value from ``repr``/``str`` so it never lands in
    # logs by accident (T-01-secret-leak-via-repr mitigation).
    GRUVAX_SECRET_KEY: SecretStr

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"

    @field_validator("GRUVAX_SECRET_KEY")
    @classmethod
    def _validate_fernet_key(cls, v: SecretStr) -> SecretStr:
        """Reject malformed Fernet keys at boot, not at first decrypt.

        Constructs ``Fernet(v)`` — the constructor raises ``ValueError`` if the
        key is not 32 url-safe base64 bytes, which pydantic surfaces as a
        precise ValidationError naming this field. Import inside the validator
        to avoid any module-import ordering surprises in tooling that loads
        settings before its third-party deps are ready.
        """
        # Local import: plan 01-01 calls for the Fernet import to live inside
        # the validator so settings-loading tooling can run before its
        # third-party deps resolve. The PLC0415 lint is intentionally silenced.
        from cryptography.fernet import Fernet  # noqa: PLC0415

        Fernet(v.get_secret_value().encode())
        return v


# Module-level singleton — import this everywhere.
settings = Settings()
