"""Pytest fixtures shared across the test suite.

Tests replace `get_db` at runtime so the app uses an isolated in-memory
SQLite database. This keeps tests fast, isolated, and free of side effects.
"""
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.roles import Role
from app.db.session import Base
from app.main import app
from app.schemas.user import UserCreate
from app.services import task_service, user_service

# `StaticPool` keeps a single shared connection across the engine, which
# is required when using an in-memory SQLite DB across multiple sessions.
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Redirect the background-task runner to the same in-memory DB as the API.
# Without this, run_task_sync would open a session against the real
# gatekeeper.db file and never find the test's task rows.
task_service.set_session_factory(TestSessionLocal)


def override_get_db() -> Generator:
    """Replacement for `get_db` that hands out test-DB sessions."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_database():
    """Wipe and recreate the schema before every test for full isolation."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide a TestClient wired to the in-memory test database."""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seed_users():
    """Create one user per role in the test database.

    Returns a dict keyed by role name. Passwords are all "password123"
    so tests can log in easily.
    """
    db = TestSessionLocal()
    try:
        users = {}
        for role in Role:
            payload = UserCreate(
                username=f"{role.value}_user",
                password="password123",
                role=role,
            )
            users[role.value] = user_service.create_user(db, payload)
        return users
    finally:
        db.close()


def login_as(client: TestClient, username: str, password: str = "password123") -> str:
    """Helper: log in and return the bearer token."""
    response = client.post(
        "/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    """Build the Authorization header for authenticated requests."""
    return {"Authorization": f"Bearer {token}"}
