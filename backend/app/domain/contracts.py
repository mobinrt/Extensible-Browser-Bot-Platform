from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable, Protocol


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_HUMAN = "WAITING_FOR_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    TIMED_OUT = "TIMED_OUT"


class BrowserMode(StrEnum):
    HEADLESS = "HEADLESS"
    HEADFUL = "HEADFUL"


TERMINAL = frozenset({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.BLOCKED,
                      RunStatus.TIMED_OUT})
TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset({RunStatus.RUNNING}),
    RunStatus.RUNNING: frozenset(TERMINAL | {RunStatus.WAITING_FOR_HUMAN}),
    RunStatus.WAITING_FOR_HUMAN: frozenset(TERMINAL | {RunStatus.RUNNING}),
    **{status: frozenset() for status in TERMINAL},
}


def transition_allowed(current: RunStatus, next_status: RunStatus) -> bool:
    return next_status in TRANSITIONS[current]


@dataclass(frozen=True)
class BotDescriptor:
    bot_id: str
    name: str
    description: str
    requires_credentials: bool = False


@dataclass(frozen=True)
class BotResult:
    status: RunStatus
    evidence: str = ""
    metadata: dict[str, str | int | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in TERMINAL:
            raise ValueError("BotResult must be terminal")
        if self.status is RunStatus.SUCCEEDED and not self.evidence:
            raise ValueError("Success requires observed verification evidence")


class BotRunError(Exception):
    def __init__(self, code: str, stage: str, status: RunStatus = RunStatus.FAILED):
        super().__init__(code)
        self.code = code
        self.stage = stage
        self.status = status


@dataclass
class BotContext:
    mode: BrowserMode
    driver: Any  # Browser driver abstraction; Selenium is injected by infrastructure.
    deadline: datetime
    record_challenge: Callable[[str], None]
    report_manual_wait: Callable[[], None]
    check_deadline: Callable[[], None]
    report_running: Callable[[], None] = lambda: None
    record_checkpoint: Callable[[str, dict[str, Any]], None] | None = None


class Bot(Protocol):
    @property
    def descriptor(self) -> BotDescriptor: ...

    def run(self, ctx: BotContext) -> BotResult: ...


class BrowserFactory(Protocol):
    def start(self, mode: BrowserMode) -> Any: ...
