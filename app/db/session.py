"""Database engine, session factory, and declarative base.

A single engine is created at module import time. `SessionLocal` is a
factory that produces short-lived sessions tied to the lifetime of one
HTTP request (see `app.api.deps.get_db`).
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

# `check_same_thread=False` is required for SQLite when the same connection
# is shared across threads (FastAPI uses a threadpool for sync routes).
# It's a no-op for other databases.
connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    # Recycles connections after 1 hour to avoid stale-connection issues
    # behind connection-pooling proxies in production deployments.
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    Using SQLAlchemy 2.0's typed `DeclarativeBase` gives us proper type hints
    on model attributes, which Pydantic's `from_attributes=True` then
    consumes to produce well-typed response schemas.
    """
