"""PostgreSQL-claimed single-process worker; safe for concurrent worker replicas."""
import logging
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from selenium.common.exceptions import TimeoutException, WebDriverException
from sqlalchemy.exc import SQLAlchemyError
from urllib3.exceptions import HTTPError, MaxRetryError, NewConnectionError
from urllib3.exceptions import TimeoutError as TransportTimeout

from app.application.registry import build_registry
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.domain.contracts import BotContext, BotRunError, BrowserMode, RunStatus
from app.infrastructure.browser.diagnostics import RunDiagnostics
from app.infrastructure.browser.selenium_factory import SeleniumBrowserFactory
from app.infrastructure.database.repository import RunRepository
from app.infrastructure.database.session import SessionLocal

log = logging.getLogger("worker")


def execute(run_id: UUID, bot_id: str, mode: BrowserMode, worker_id: str) -> None:
    s = get_settings()
    deadline = datetime.now(timezone.utc) + timedelta(seconds=s.run_timeout_seconds)
    diagnostics = (RunDiagnostics(s.arcaptcha_diagnostics_directory, run_id, str(mode))
                   if bot_id == "arcaptcha-demo" and s.arcaptcha_diagnostics_enabled else None)
    stop = threading.Event()
    heartbeat_error = threading.Event()

    def persist(method: str, *args, **kwargs):
        with SessionLocal() as db:
            fn = getattr(RunRepository(db), method)
            return fn(run_id, worker_id, *args, **kwargs)

    def heartbeat() -> None:
        while not stop.wait(s.heartbeat_seconds):
            try:
                if not persist("heartbeat", s.lease_seconds):
                    heartbeat_error.set()
                    return
            except SQLAlchemyError:
                heartbeat_error.set()
                log.error("heartbeat_database_failure")
                return

    def check_deadline() -> None:
        if datetime.now(timezone.utc) >= deadline:
            raise BotRunError("RUN_DEADLINE_EXCEEDED", "worker", RunStatus.TIMED_OUT)
        if heartbeat_error.is_set():
            raise BotRunError("LEASE_LOST", "worker")

    def save_challenge(value: str) -> None:
        if not persist("save_challenge", value):
            raise BotRunError("CHALLENGE_PERSISTENCE_REJECTED", "database")

    def human_wait() -> None:
        if not persist("set_status", RunStatus.WAITING_FOR_HUMAN):
            raise BotRunError("WAIT_TRANSITION_REJECTED", "worker")

    def resume_running() -> None:
        if not persist("set_status", RunStatus.RUNNING):
            raise BotRunError("RESUME_TRANSITION_REJECTED", "worker")

    thread = threading.Thread(target=heartbeat, name="heartbeat", daemon=True)
    thread.start()
    driver = None
    status = RunStatus.FAILED
    failure_stage = None
    error_code = None
    metadata = None
    try:
        check_deadline()
        factory = SeleniumBrowserFactory(s.selenium_url)
        if diagnostics is not None:
            factory.capture_console = True
        driver = factory.start(mode)
        if diagnostics is not None:
            diagnostics.browser_created(driver, s.selenium_url)
        check_deadline()
        bot = build_registry().get(bot_id)
        result = bot.run(BotContext(mode=mode, driver=driver, deadline=deadline,
                                    record_challenge=save_challenge,
                                    report_manual_wait=human_wait,
                                    check_deadline=check_deadline, report_running=resume_running,
                                    record_checkpoint=diagnostics.checkpoint if diagnostics else None))
        check_deadline()
        status, metadata = result.status, {**result.metadata, "evidence": result.evidence}
    except BotRunError as error:
        status, error_code, failure_stage = error.status, error.code, error.stage
    except TimeoutException:
        status, error_code, failure_stage = (RunStatus.TIMED_OUT,
                                             "BROWSER_TIMEOUT", "browser")
    except HTTPError as error:
        cause = error.reason if isinstance(error, MaxRetryError) else error
        timed_out = isinstance(cause, TransportTimeout) and not isinstance(cause, NewConnectionError)
        status = RunStatus.TIMED_OUT if timed_out else RunStatus.FAILED
        error_code = "BROWSER_TRANSPORT_TIMEOUT" if timed_out else "BROWSER_CONNECTION_FAILED"
        failure_stage = "browser"
    except WebDriverException:
        status, error_code, failure_stage = (RunStatus.FAILED,
                                             "BROWSER_ERROR", "browser")
    except SQLAlchemyError:
        status, error_code, failure_stage = (RunStatus.FAILED,
                                             "DATABASE_UNAVAILABLE", "database")
    except Exception:
        # Defensive process boundary: no raw stack/error data (may contain secrets).
        status, error_code, failure_stage = (RunStatus.FAILED,
                                             "UNEXPECTED_WORKER_FAILURE", "worker")
    finally:
        if diagnostics is not None:
            diagnostics.snapshot()
        try:
            if driver is not None:
                driver.quit()
        except (WebDriverException, HTTPError):
            log.warning("browser_cleanup_failed")
        stop.set()
        thread.join(timeout=2)
        finalized = False
        try:
            finalized = persist("finish", status, error_code=error_code, failure_stage=failure_stage, metadata=metadata)
            if not finalized:
                log.warning("final_status_rejected_lease_or_terminal")
        except SQLAlchemyError:
            # Recoverable by the lease reaper. No fake terminal result.
            log.error("final_status_persistence_failed")
        if diagnostics is not None:
            diagnostics.finish(str(status), persisted=finalized)
        log.info("run_processed attempted_status=%s", status)


def main() -> None:
    configure_logging()
    s = get_settings()
    worker_id = str(uuid4())
    stopping = False

    def on_signal(_signum, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    log.info("worker_started")
    while not stopping:
        try:
            with SessionLocal() as db:
                repo = RunRepository(db)
                count = repo.expire_stale()
                if count:
                    log.warning("stale_runs_expired count=%d", count)
                run = repo.claim_next(worker_id, s.lease_seconds)
            if run is not None:
                execute(run.run_id, run.bot_id, run.browser_mode, worker_id)
                continue
        except SQLAlchemyError:
            log.error("worker_database_unavailable")
        time.sleep(s.poll_seconds)


if __name__ == "__main__":
    main()
