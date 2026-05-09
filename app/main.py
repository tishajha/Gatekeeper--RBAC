"""FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import auth, health, tasks, users
from app.core.config import settings
from app.db.session import Base, engine


import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup and shutdown hooks for the app.

    On startup we create any missing tables. This is safe to run on every
    boot — `create_all` is a no-op for tables that already exist. For a
    real production deployment you'd replace this with Alembic migrations.
    """
    Base.metadata.create_all(bind=engine)
    yield
    # No shutdown work needed: the DB engine handles its own pool cleanup.


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Production-grade backend providing role-based access control "
        "over protected APIs, with background task execution."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Routers are mounted explicitly here (rather than auto-discovered) so the
# wiring is greppable: any new endpoint must be visible in this file.
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(tasks.router)
