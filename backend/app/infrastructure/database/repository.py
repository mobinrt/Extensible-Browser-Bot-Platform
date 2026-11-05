from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Integer, cast, func, select, true, update
from sqlalchemy.orm import Session

from app.domain.contracts import TERMINAL, BrowserMode, RunStatus, transition_allowed
from app.infrastructure.database.models import Run


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunRepository:
    def __init__(self, session: Session):
        self.db = session

    def create(self, bot_id: str, mode: BrowserMode) -> Run:
        run = Run(bot_id=bot_id, browser_mode=mode, status=RunStatus.QUEUED)
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get(self, run_id: UUID) -> Run | None:
        return self.db.get(Run, run_id)

    def list(self, *, status: RunStatus | None, limit: int, offset: int) -> tuple[list[Run], int]:
        cond = (Run.status == status) if status else true()
        count = self.db.scalar(select(func.count()).select_from(Run).where(cond)) or 0
        items = list(self.db.scalars(select(Run).where(cond).order_by(Run.created_at.desc(),
                                     Run.run_id.desc()).offset(offset).limit(limit)))
        return items, count

    def claim_next(self, worker_id: str, lease_seconds: int) -> Run | None:
        # Atomic Postgres row lock. Workers skip rows claimed by competing transactions.
        row = self.db.scalar(select(Run).where(Run.status == RunStatus.QUEUED)
                             .order_by(Run.created_at, Run.run_id)
                             .with_for_update(skip_locked=True).limit(1))
        if row is None:
            self.db.rollback()
            return None
        now = utcnow()
        row.status = RunStatus.RUNNING
        row.worker_id = worker_id
        row.started_at = now
        row.heartbeat_at = now
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self.db.commit()
        return row

    def heartbeat(self, run_id: UUID, worker_id: str, lease_seconds: int) -> bool:
        now = utcnow()
        statement = (update(Run).where(Run.run_id == run_id, Run.worker_id == worker_id,
                   Run.status.in_([RunStatus.RUNNING, RunStatus.WAITING_FOR_HUMAN]),
                   Run.lease_expires_at > now)
                   .values(heartbeat_at=now,
                           lease_expires_at=now + timedelta(seconds=lease_seconds)))
        changed = self.db.execute(statement).rowcount
        self.db.commit()
        return changed == 1

    def save_challenge(self, run_id: UUID, worker_id: str, challenge_id: str) -> bool:
        # Commit independently before continuing to the form, never defer to final result.
        if not challenge_id or len(challenge_id) > 256:
            raise ValueError("Invalid challenge identifier length")
        statement = (update(Run).where(Run.run_id == run_id, Run.worker_id == worker_id,
                   Run.status.in_([RunStatus.RUNNING, RunStatus.WAITING_FOR_HUMAN]),
                   Run.lease_expires_at > utcnow(),
                   (Run.challenge_id.is_(None) | (Run.challenge_id == challenge_id)))
                   .values(challenge_id=challenge_id))
        changed = self.db.execute(statement).rowcount
        self.db.commit()
        return changed == 1

    def set_status(self, run_id: UUID, worker_id: str, new: RunStatus) -> bool:
        if new in TERMINAL:
            raise ValueError("Use finish for terminal transitions")
        row = self.db.scalar(select(Run).where(Run.run_id == run_id, Run.worker_id == worker_id)
                             .with_for_update())
        if (row is None or not transition_allowed(row.status, new)
                or row.lease_expires_at is None or row.lease_expires_at <= utcnow()):
            self.db.rollback()
            return False
        row.status = new
        self.db.commit()
        return True

    def finish(self, run_id: UUID, worker_id: str, status: RunStatus,
               *, error_code: str | None = None, failure_stage: str | None = None,
               metadata: dict | None = None) -> bool:
        if status is RunStatus.SUCCEEDED and not (metadata and metadata.get("evidence")):
            raise ValueError("Success requires evidence")
        if status not in TERMINAL:
            raise ValueError("Not terminal")
        row = self.db.scalar(select(Run).where(Run.run_id == run_id, Run.worker_id == worker_id)
                             .with_for_update())
        if (row is None or not transition_allowed(row.status, status)
                or row.lease_expires_at is None or row.lease_expires_at <= utcnow()):
            self.db.rollback()
            return False
        now = utcnow()
        row.status = status
        row.finished_at = now
        row.lease_expires_at = None
        row.worker_id = None
        row.error_code = error_code
        row.failure_stage = failure_stage
        # Only allow known server-authored codes, never raw exception/page strings.
        row.error_message = error_code.replace("_", " ").lower() if error_code else None
        row.duration_ms = int((now - row.started_at).total_seconds() * 1000) if row.started_at else None
        row.result_metadata = metadata
        self.db.commit()
        return True

    def expire_stale(self) -> int:
        now = utcnow()
        # Deliberately terminal, not requeued: replaying a form submission may duplicate effects.
        statement = (update(Run).where(Run.status.in_([
            RunStatus.RUNNING, RunStatus.WAITING_FOR_HUMAN]),
            Run.lease_expires_at < now).values(
            status=RunStatus.TIMED_OUT, finished_at=now,
            error_code="WORKER_LEASE_EXPIRED", error_message="worker lease expired",
            failure_stage="worker", worker_id=None, lease_expires_at=None,
            duration_ms=cast(func.extract("epoch", now - Run.started_at) * 1000, Integer)))
        changed = self.db.execute(statement).rowcount
        self.db.commit()
        return changed
