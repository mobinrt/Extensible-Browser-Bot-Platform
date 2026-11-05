from collections.abc import Generator
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.schemas import BotOut, CreateRun, RunOut, RunsPage
from app.application.registry import BotRegistry, build_registry
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.domain.contracts import RunStatus
from app.infrastructure.database.repository import RunRepository
from app.infrastructure.database.session import SessionLocal

configure_logging()
settings = get_settings()
app = FastAPI(title="Browser Bot Platform", version="0.1.0", openapi_url="/api/v1/openapi.json",
              docs_url="/api/v1/docs")
app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins.split(","),
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])


def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def get_registry() -> BotRegistry:
    return build_registry()


@app.get("/api/v1/health/live")
def live() -> dict:
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="database not ready") from error
    return {"status": "ready"}


@app.get("/api/v1/bots", response_model=list[BotOut])
def bots(registry: BotRegistry = Depends(get_registry)):
    return [BotOut.model_validate(bot.__dict__) for bot in registry.list()]


@app.post("/api/v1/runs", response_model=RunOut, status_code=202)
def create_run(data: CreateRun, db: Session = Depends(get_db),
               registry: BotRegistry = Depends(get_registry)):
    try:
        registry.get(data.bot_id)
    except KeyError as error:
        raise HTTPException(status_code=422, detail="unknown bot_id") from error
    try:
        row = RunRepository(db).create(data.bot_id, data.browser_mode)
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return RunOut.model_validate(row)


@app.get("/api/v1/runs", response_model=RunsPage)
def list_runs(status: RunStatus | None = None,
              limit: int = Query(default=25, ge=1, le=100),
              offset: int = Query(default=0, ge=0),
              db: Session = Depends(get_db)):
    try:
        records, count = RunRepository(db).list(status=status, limit=limit, offset=offset)
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    return RunsPage(items=[RunOut.model_validate(r) for r in records], total=count,
                    limit=limit, offset=offset)


@app.get("/api/v1/runs/{run_id}", response_model=RunOut)
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    try:
        run = RunRepository(db).get(run_id)
    except SQLAlchemyError as error:
        raise HTTPException(status_code=503, detail="database unavailable") from error
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return RunOut.model_validate(run)
