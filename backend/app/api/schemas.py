from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.contracts import BrowserMode, RunStatus


class BotOut(BaseModel):
    bot_id: str
    name: str
    description: str
    requires_credentials: bool


class CreateRun(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bot_id: str = Field(min_length=1, max_length=80)
    browser_mode: BrowserMode = BrowserMode.HEADLESS


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: UUID
    bot_id: str
    browser_mode: BrowserMode
    status: RunStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    challenge_id: str | None
    error_code: str | None
    error_message: str | None
    failure_stage: str | None
    duration_ms: int | None
    result_metadata: dict | None


class RunsPage(BaseModel):
    items: list[RunOut]
    total: int
    limit: int
    offset: int
