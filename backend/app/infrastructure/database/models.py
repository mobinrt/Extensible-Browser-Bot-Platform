from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, func, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.contracts import BrowserMode, RunStatus


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True,
                                        server_default=text("gen_random_uuid()"))
    bot_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    browser_mode: Mapped[BrowserMode] = mapped_column(SQLEnum(BrowserMode), nullable=False)
    status: Mapped[RunStatus] = mapped_column(SQLEnum(RunStatus), nullable=False,
                                             server_default="QUEUED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    challenge_id: Mapped[str | None] = mapped_column(String(256))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(String(256))
    failure_stage: Mapped[str | None] = mapped_column(String(80))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    result_metadata: Mapped[dict | None] = mapped_column(JSONB)
    worker_id: Mapped[str | None] = mapped_column(String(80), index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
