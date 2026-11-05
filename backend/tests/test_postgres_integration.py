"""Runs against a dedicated disposable PostgreSQL database when TEST_DATABASE_URL is set."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

pytest.importorskip("psycopg")
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.domain.contracts import BrowserMode, RunStatus
from app.infrastructure.database.models import Base, Run
from app.infrastructure.database.repository import RunRepository, utcnow


@pytest.fixture
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("requires TEST_DATABASE_URL for disposable PostgreSQL database")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_create_claim_persist_and_fail(engine):
    with Session(engine) as db:
        row = RunRepository(db).create("arcaptcha-demo", BrowserMode.HEADLESS)
        run_id = row.run_id
    with Session(engine) as db:
        claimed = RunRepository(db).claim_next("worker-a", 30)
        assert claimed.run_id == run_id and claimed.status == RunStatus.RUNNING
    with Session(engine) as db:
        assert RunRepository(db).save_challenge(run_id, "worker-a", "real-observed-123")
    with Session(engine) as db:
        assert RunRepository(db).finish(run_id, "worker-a", RunStatus.BLOCKED,
                                        error_code="CAPTCHA_REQUIRES_HUMAN", failure_stage="captcha")
    with Session(engine) as db:
        final = RunRepository(db).get(run_id)
        assert final.challenge_id == "real-observed-123"
        assert final.status == RunStatus.BLOCKED
        assert final.error_message == "captcha requires human"
        assert not RunRepository(db).finish(run_id, "worker-a", RunStatus.SUCCEEDED, metadata={"evidence": "late"})


def test_concurrent_claim_cannot_take_same_run(engine):
    with Session(engine) as db:
        RunRepository(db).create("local-smoke", BrowserMode.HEADFUL)

    def claim(worker):
        with Session(engine) as db:
            row = RunRepository(db).claim_next(worker, 30)
            return row.run_id if row else None

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(claim, ["worker-1", "worker-2"]))
    assert sum(value is not None for value in ids) == 1


def test_stale_run_expires_and_cannot_complete_late(engine):
    with Session(engine) as db:
        row = RunRepository(db).create("local-smoke", BrowserMode.HEADLESS)
        run_id = row.run_id
        RunRepository(db).claim_next("worker-a", 30)
    with Session(engine) as db:
        run = db.get(Run, run_id)
        run.lease_expires_at = utcnow() - timedelta(seconds=5)
        db.commit()
    with Session(engine) as db:
        assert RunRepository(db).expire_stale() == 1
        assert not RunRepository(db).finish(run_id, "worker-a", RunStatus.SUCCEEDED, metadata={"evidence": "late"})
        assert RunRepository(db).get(run_id).status == RunStatus.TIMED_OUT


def test_status_filter_and_history(engine):
    with Session(engine) as db:
        repo = RunRepository(db)
        repo.create("local-smoke", BrowserMode.HEADFUL)
        repo.create("arcaptcha-demo", BrowserMode.HEADLESS)
        rows, total = repo.list(status=RunStatus.QUEUED, limit=1, offset=0)
        assert total == 2 and len(rows) == 1


def test_expired_lease_cannot_be_renewed_or_write(engine):
    with Session(engine) as db:
        repo = RunRepository(db)
        run = repo.create("local-smoke", BrowserMode.HEADLESS)
        repo.claim_next("owner", 30)
        run.lease_expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert not repo.heartbeat(run.run_id, "owner", 30)
        assert not repo.save_challenge(run.run_id, "owner", "late")
        assert not repo.set_status(run.run_id, "owner", RunStatus.WAITING_FOR_HUMAN)
        assert not repo.finish(run.run_id, "owner", RunStatus.FAILED)
        assert repo.expire_stale() == 1


def test_challenge_immutable_and_visible_in_another_session(engine):
    with Session(engine) as db:
        repo = RunRepository(db)
        run = repo.create("local-smoke", BrowserMode.HEADLESS)
        repo.claim_next("owner", 30)
        assert repo.save_challenge(run.run_id, "owner", "first")
        assert not repo.save_challenge(run.run_id, "owner", "different")
        with Session(engine) as reader:
            assert reader.get(Run, run.run_id).challenge_id == "first"
        with pytest.raises(ValueError):
            repo.save_challenge(run.run_id, "owner", "x" * 257)
        with pytest.raises(ValueError, match="evidence"):
            repo.finish(run.run_id, "owner", RunStatus.SUCCEEDED)


@pytest.mark.parametrize("mode", list(BrowserMode))
def test_worker_commits_id_on_failure_and_cleans_browser(engine, monkeypatch, mode):
    from types import SimpleNamespace

    from sqlalchemy.orm import sessionmaker

    from app.domain.contracts import BotRunError
    from app.worker import main as worker

    class Driver:
        closed = False

        def quit(self):
            self.closed = True

    driver = Driver()

    class Bot:
        def run(self, ctx):
            ctx.record_challenge("worker-real-observed")
            # Verify commit from an independent DB session while bot is still executing.
            with Session(engine) as other:
                assert other.get(Run, run_id).challenge_id == "worker-real-observed"
            raise BotRunError("VERIFICATION_REJECTED", "verification")

    monkeypatch.setattr(worker, "SessionLocal", sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(worker, "SeleniumBrowserFactory", lambda _: SimpleNamespace(start=lambda _: driver))
    monkeypatch.setattr(worker, "build_registry", lambda: SimpleNamespace(get=lambda _: Bot()))
    with Session(engine) as db:
        repo = RunRepository(db)
        run_id = repo.create("arcaptcha-demo", mode).run_id
        repo.claim_next("worker", 45)
    worker.execute(run_id, "arcaptcha-demo", mode, "worker")
    with Session(engine) as db:
        row = db.get(Run, run_id)
        assert row.status is RunStatus.FAILED
        assert row.error_code == "VERIFICATION_REJECTED"
        assert row.failure_stage == "verification"
        assert row.challenge_id == "worker-real-observed"
    assert driver.closed


def test_terminal_transition_requires_finish(engine):
    with Session(engine) as db:
        repo = RunRepository(db)
        run = repo.create("local-smoke", BrowserMode.HEADLESS)
        repo.claim_next("worker", 30)
        with pytest.raises(ValueError, match="Use finish"):
            repo.set_status(run.run_id, "worker", RunStatus.SUCCEEDED)


@pytest.mark.parametrize("timeout", [False, True])
def test_worker_distinguishes_connection_failure_from_timeout(engine, monkeypatch, timeout):
    from sqlalchemy.orm import sessionmaker
    from urllib3.exceptions import NewConnectionError, ReadTimeoutError

    from app.worker import main as worker

    error = ReadTimeoutError(None, "remote", "timeout") if timeout else NewConnectionError(None, "refused")

    class Factory:
        def __init__(self, _):
            pass

        def start(self, _):
            raise error

    monkeypatch.setattr(worker, "SessionLocal", sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(worker, "SeleniumBrowserFactory", Factory)
    with Session(engine) as db:
        repo = RunRepository(db)
        run_id = repo.create("local-smoke", BrowserMode.HEADLESS).run_id
        repo.claim_next("owner", 45)
    worker.execute(run_id, "local-smoke", BrowserMode.HEADLESS, "owner")
    with Session(engine) as db:
        row = db.get(Run, run_id)
        assert row.status is (RunStatus.TIMED_OUT if timeout else RunStatus.FAILED)
        assert row.error_code == ("BROWSER_TRANSPORT_TIMEOUT" if timeout else "BROWSER_CONNECTION_FAILED")


def test_worker_diagnostics_link_actual_terminal_record_without_payloads(engine, monkeypatch, tmp_path):
    import json
    from types import SimpleNamespace

    from sqlalchemy.orm import sessionmaker

    from app.core.config import Settings
    from app.domain.contracts import BotRunError
    from app.infrastructure.browser import diagnostics as diagnostic_module
    from app.worker import main as worker

    driver = SimpleNamespace(capabilities={"browserName": "chrome", "browserVersion": "155.0.0"},
                             current_url="https://demo.arcaptcha.co/?token=secret",
                             execute_cdp_cmd=lambda *_: {}, execute_script=lambda *_: "complete",
                             get_log=lambda _: [], quit=lambda: None)
    class Bot:
        def run(self, ctx):
            ctx.record_checkpoint("SITE_BLOCK_DETECTED", {"stage": "before_checkbox", "site_rejection": True})
            raise BotRunError("CAPTCHA_SITE_BLOCKED", "captcha", RunStatus.BLOCKED)
    settings = Settings(_env_file=None, database_url=str(engine.url), arcaptcha_diagnostics_enabled=True,
                        arcaptcha_diagnostics_directory=tmp_path)
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(diagnostic_module, "grid_version", lambda _: "4.51.0")
    monkeypatch.setattr(diagnostic_module, "dns_result", lambda host: {"host": host, "resolved": True})
    monkeypatch.setattr(worker, "SessionLocal", sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(worker, "SeleniumBrowserFactory", lambda _: SimpleNamespace(start=lambda _: driver))
    monkeypatch.setattr(worker, "build_registry", lambda: SimpleNamespace(get=lambda _: Bot()))
    with Session(engine) as db:
        repo = RunRepository(db)
        run_id = repo.create("arcaptcha-demo", BrowserMode.HEADFUL).run_id
        repo.claim_next("owner", 45)
    worker.execute(run_id, "arcaptcha-demo", BrowserMode.HEADFUL, "owner")
    records = [json.loads(line) for line in (tmp_path / f"{run_id}.jsonl").read_text().splitlines()]
    assert records[-1]["checkpoint"] == "RUN_FINISHED" and records[-1]["persisted"] is True
    assert records[-1]["outcome"] == "BLOCKED" and "secret" not in json.dumps(records)
    with Session(engine) as db:
        row = db.get(Run, run_id)
        assert row.status is RunStatus.BLOCKED and row.error_code == "CAPTCHA_SITE_BLOCKED"
        assert row.result_metadata is None and row.challenge_id is None
