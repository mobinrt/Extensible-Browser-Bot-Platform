import pytest
from pydantic import ValidationError

from app.core.config import Settings

DB = "postgresql+psycopg://user:password@localhost:5432/test"


def test_config_defaults_and_secret_str():
    settings = Settings(database_url=DB, demo_password="private-text")
    assert settings.demo_url == "https://demo.arcaptcha.co"
    assert "private-text" not in repr(settings)
    assert settings.demo_password.get_secret_value() == "private-text"
    assert settings.arcaptcha_success_selector == ""
    assert settings.browser_backend == "selenium-grid"


def test_optional_browser_backend_is_explicit_and_validated():
    assert Settings(database_url=DB, browser_backend="undetected-chrome").browser_backend == "undetected-chrome"
    with pytest.raises(ValidationError):
        Settings(database_url=DB, browser_backend="playwright")


@pytest.mark.parametrize("url", ["https://evil.example", "http://demo.arcaptcha.co"])
def test_demo_target_is_pinned(url):
    with pytest.raises(ValidationError):
        Settings(database_url=DB, demo_url=url)


def test_heartbeat_shorter_than_half_lease():
    with pytest.raises(ValidationError):
        Settings(database_url=DB, lease_seconds=20, heartbeat_seconds=10)


def test_no_database_url_is_rejected(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, postgres_password="")


def test_database_password_reserved_characters_roundtrip():
    from sqlalchemy.engine import make_url
    settings = Settings(_env_file=None, database_url="", postgres_password="a@:/#%?$")
    assert make_url(settings.database_url).password == "a@:/#%?$"
    assert "a@:/#%?$" not in repr(settings)
