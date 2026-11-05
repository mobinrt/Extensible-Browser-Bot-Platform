from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=5,
                       max_overflow=5, pool_timeout=5, connect_args={
                           "connect_timeout": 5,
                           "options": "-c statement_timeout=10000",
                           "keepalives": 1, "keepalives_idle": 5,
                           "keepalives_interval": 5, "keepalives_count": 2,
                           "tcp_user_timeout": 10000,
                       })
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
