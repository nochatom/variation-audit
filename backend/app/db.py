"""Database engine + session factory.

`session_factory` is a callable usable as a context manager:
    with session_factory() as session:
        ...
matching what the worker's run_once/run_forever expect.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)

session_factory: sessionmaker[Session] = sessionmaker(
    bind=engine, expire_on_commit=False, class_=Session, future=True
)
