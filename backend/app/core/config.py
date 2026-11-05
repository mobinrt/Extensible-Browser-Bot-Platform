from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", env_prefix="")

    database_url: str = Field(default="", repr=False)
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "bots"
    postgres_user: str = "bots"
    postgres_password: SecretStr = SecretStr("")
    selenium_url: str = "http://localhost:4444/wd/hub"
    demo_url: str = "https://demo.arcaptcha.co"
    demo_username: str = ""
    demo_password: SecretStr = SecretStr("")
    poll_seconds: float = Field(default=1.5, ge=0.2, le=30)
    lease_seconds: int = Field(default=45, ge=15, le=600)
    heartbeat_seconds: int = Field(default=10, ge=1, le=100)
    run_timeout_seconds: int = Field(default=180, ge=10, le=3600)
    manual_timeout_seconds: int = Field(default=90, ge=5, le=900)
    selenium_wait_seconds: int = Field(default=12, ge=1, le=120)
    # Confirmed from the demo bundle; metadata/verification use read-only adapters.
    arcaptcha_checkbox_selector: str = "#arc-checkbox, #ar-checkbox"
    # Deprecated legacy fields are accepted for compatibility, never trusted as evidence.
    arcaptcha_challenge_selector: str = ""
    arcaptcha_username_selector: str = "#email"
    arcaptcha_password_selector: str = "#password"
    arcaptcha_submit_selector: str = "form button"
    arcaptcha_solved_selector: str = ""
    arcaptcha_success_selector: str = ""
    arcaptcha_failure_selector: str = ""
    arcaptcha_diagnostics_enabled: bool = False
    arcaptcha_diagnostics_directory: Path = Path("diagnostics")
    allowed_origins: str = "http://localhost:5173,http://localhost:8080"

    @field_validator("demo_url")
    @classmethod
    def fixed_target(cls, value: str) -> str:
        if value.rstrip("/") != "https://demo.arcaptcha.co":
            raise ValueError("The Arcaptcha bot is restricted to the assigned demo host")
        return value

    @model_validator(mode="after")
    def validate_timing(self) -> "Settings":
        if not self.database_url:
            if not self.postgres_password.get_secret_value():
                raise ValueError("DATABASE_URL or POSTGRES_PASSWORD is required")
            self.database_url = URL.create(
                "postgresql+psycopg", username=self.postgres_user,
                password=self.postgres_password.get_secret_value(), host=self.postgres_host,
                port=self.postgres_port, database=self.postgres_db).render_as_string(hide_password=False)
        if self.heartbeat_seconds >= self.lease_seconds // 2:
            raise ValueError("Heartbeat must be less than half the lease")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
