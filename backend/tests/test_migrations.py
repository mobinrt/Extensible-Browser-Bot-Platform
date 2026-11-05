"""Dedicated clean PostgreSQL migration smoke test. Requires TEST_DATABASE_URL."""
import os
from pathlib import Path

import pytest

pytest.importorskip("psycopg")


def test_alembic_upgrade_downgrade_against_clean_db(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires a dedicated clean TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", url)
    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings
    get_settings.cache_clear()
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "migrations"))
    # Run against a dedicated test database only: downgrade drops the runs table.
    command.upgrade(cfg, "head")
    from sqlalchemy import create_engine, inspect
    engine = create_engine(url)
    assert "runs" in inspect(engine).get_table_names()
    command.downgrade(cfg, "base")
    assert "runs" not in inspect(engine).get_table_names()
    engine.dispose()
