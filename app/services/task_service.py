"""Task-related business logic and the in-process task runner.

This module uses FastAPI's BackgroundTasks to run work after the HTTP
response is returned. Task state is persisted in the database so clients
can poll for status and results.

If the API process is killed while work is running, that task may remain
in PENDING/RUNNING state indefinitely. In a production setup this runner
would be replaced with a queue-based worker system, but the task registry
keeps the rest of the module unchanged.
"""
import json
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate


# ---------------------------------------------------------------------------
# Task runner registry
# ---------------------------------------------------------------------------
#
# Each `task_type` string maps to a runner function here. To add a new task,
# define the function and add it to the registry. The route layer stays
# unaware of the concrete task implementations.

TaskRunner = Callable[[dict[str, Any] | None], dict[str, Any]]


def _runner_long_computation(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Demo task: sleeps for `duration` seconds (default 5) then returns sum.

    This task simulates work so the endpoint returns immediately while the
    job finishes in the background.
    """
    duration = (payload or {}).get("duration", 5)
    numbers = (payload or {}).get("numbers", [1, 2, 3, 4, 5])
    time.sleep(duration)
    return {"sum": sum(numbers), "slept_seconds": duration}


def _runner_echo(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Trivial task that echoes its payload — useful for smoke tests."""
    return {"echoed": payload or {}}


TASK_REGISTRY: dict[str, TaskRunner] = {
    "long_computation": _runner_long_computation,
    "echo": _runner_echo,
}


# ---------------------------------------------------------------------------
# Task lifecycle
# ---------------------------------------------------------------------------


def create_task(db: Session, payload: TaskCreate, user_id: int) -> Task:
    """Persist a new task in PENDING state and return it.

    The caller is expected to schedule `run_task_sync(task.id)` on a
    BackgroundTasks instance after this returns.
    """
    if payload.task_type not in TASK_REGISTRY:
        # Surfaced by the route as a 400 — the task type doesn't exist.
        raise ValueError(
            f"Unknown task_type '{payload.task_type}'. "
            f"Known: {sorted(TASK_REGISTRY)}"
        )

    task = Task(
        id=str(uuid.uuid4()),
        task_type=payload.task_type,
        status=TaskStatus.PENDING.value,
        payload=json.dumps(payload.payload) if payload.payload else None,
        created_by=user_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, task_id: str) -> Task | None:
    """Fetch a task by ID, or return None if not found."""
    return db.query(Task).filter(Task.id == task_id).first()


def task_to_dict(task: Task) -> dict[str, Any]:
    """Materialise a Task ORM object into the shape `TaskRead` expects.

    Decodes the JSON-encoded `payload` and `result` columns so the API
    returns proper objects instead of escaped strings.
    """
    return {
        "id": task.id,
        "task_type": task.task_type,
        "status": task.status,
        "payload": json.loads(task.payload) if task.payload else None,
        "result": json.loads(task.result) if task.result else None,
        "error": task.error,
        "created_by": task.created_by,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }


# A module-level pointer to the session factory the runner should use.
# Tests override this at startup so background tasks share the same
# in-memory database as the test client.
_session_factory = SessionLocal


def set_session_factory(factory) -> None:
    """Override the session factory used by `run_task_sync`.

    Used by the test suite to redirect background-task DB writes to the
    same in-memory SQLite instance that the rest of the test app uses.
    """
    global _session_factory
    _session_factory = factory


def run_task_sync(task_id: str) -> None:
    """Execute a task and update its row in the database.

    BackgroundTasks schedules this after the response is sent. It uses its
    own DB session because the request session is closed before the task runs.
    """
    db = _session_factory()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task is None:
            # The task row was deleted between scheduling and running.
            # Nothing to do — silently return.
            return

        runner = TASK_REGISTRY.get(task.task_type)
        if runner is None:
            task.status = TaskStatus.FAILED.value
            task.error = f"Unknown task_type '{task.task_type}'"
            task.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        # Mark RUNNING so a polling client can see the task is in progress.
        task.status = TaskStatus.RUNNING.value
        task.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            payload = json.loads(task.payload) if task.payload else None
            result = runner(payload)
            task.status = TaskStatus.SUCCESS.value
            task.result = json.dumps(result)
        except Exception as exc:  # noqa: BLE001 — we want to capture *anything*
            # Store the full traceback for debugging, but keep the response
            # message short. In production you'd also log this.
            task.status = TaskStatus.FAILED.value
            task.error = f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}"
        finally:
            task.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
