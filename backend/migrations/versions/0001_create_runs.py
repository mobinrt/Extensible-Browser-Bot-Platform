"""Initial database-backed job queue and history.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    mode = ENUM("HEADLESS", "HEADFUL", name="browsermode", create_type=False)
    status = ENUM("QUEUED", "RUNNING", "WAITING_FOR_HUMAN", "SUCCEEDED",
                  "FAILED", "BLOCKED", "TIMED_OUT", name="runstatus",
                  create_type=False)
    mode.create(op.get_bind(), checkfirst=True)
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "runs",
        sa.Column("run_id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("bot_id", sa.String(80), nullable=False),
        sa.Column("browser_mode", mode, nullable=False),
        sa.Column("status", status, nullable=False, server_default="QUEUED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("challenge_id", sa.String(256)),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.String(256)),
        sa.Column("failure_stage", sa.String(80)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("result_metadata", JSONB()),
        sa.Column("worker_id", sa.String(80)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_runs_bot_id", "runs", ["bot_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_worker_id", "runs", ["worker_id"])
    op.create_index("ix_runs_lease_expires_at", "runs", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_table("runs")
    sa.Enum(name="runstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="browsermode").drop(op.get_bind(), checkfirst=True)
