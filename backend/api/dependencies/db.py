from __future__ import annotations
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.config.settings import get_settings

_settings = get_settings()
_engine = create_engine(_settings.database_url, pool_pre_ping=True)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a database session, close on exit."""
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()
