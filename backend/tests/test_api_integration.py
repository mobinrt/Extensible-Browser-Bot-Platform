"""Opt-in API integration against a separate test PostgreSQL database."""
import os

import pytest

pytest.importorskip("psycopg")
pytest.importorskip("selenium")


def test_rest_api_create_history_and_detail(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires TEST_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", url)
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine

    from app.core.config import get_settings
    from app.infrastructure.database.models import Base

    get_settings.cache_clear()
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    try:
        from app.api.main import app
        with TestClient(app) as client:
            assert client.get("/api/v1/health/live").status_code == 200
            assert client.get("/api/v1/health/ready").status_code == 200
            bots = client.get("/api/v1/bots")
            assert bots.status_code == 200
            assert {b["bot_id"] for b in bots.json()} >= {"local-smoke", "arcaptcha-demo"}
            response = client.post("/api/v1/runs", json={
                "bot_id": "local-smoke", "browser_mode": "HEADLESS"})
            assert response.status_code == 202
            run_id = response.json()["run_id"]
            assert response.json()["status"] == "QUEUED"
            assert client.get(f"/api/v1/runs/{run_id}").json()["run_id"] == run_id
            history = client.get("/api/v1/runs?status=QUEUED&limit=2")
            assert history.status_code == 200
            assert history.json()["total"] >= 1
            assert client.post("/api/v1/runs", json={"bot_id":"unknown"}).status_code == 422
            assert client.post("/api/v1/runs", json={"bot_id":"local-smoke","target_url":"https://evil.example"}).status_code == 422
            assert client.get("/api/v1/runs/not-a-uuid").status_code == 422
            assert client.get("/api/v1/runs/00000000-0000-0000-0000-000000000000").status_code == 404
            assert client.get("/api/v1/runs?status=BOGUS").status_code == 422
            assert client.get("/api/v1/runs?limit=101").status_code == 422
            from sqlalchemy.exc import SQLAlchemyError

            from app.infrastructure.database.repository import RunRepository
            monkeypatch.setattr(RunRepository, "create", lambda *_: (_ for _ in ()).throw(SQLAlchemyError("private")))
            unavailable = client.post("/api/v1/runs", json={"bot_id": "local-smoke"})
            assert unavailable.status_code == 503 and "private" not in unavailable.text
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
