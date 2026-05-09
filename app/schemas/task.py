"""Pydantic schemas for Task-related requests and responses."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    """Payload accepted by `POST /tasks/execute`.

    `task_type` is a free-form string in this example; in a real system you'd
    constrain it to an enum of known worker task names. `payload` is an
    arbitrary JSON object passed to the task.
    """

    task_type: str = Field(..., min_length=1, max_length=64)
    payload: dict[str, Any] | None = None


class TaskRead(BaseModel):
    """Response shape for both submit and status-check endpoints."""

    id: str
    task_type: str
    status: str
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_by: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TaskSubmitResponse(BaseModel):
    """Lightweight response returned immediately after task submission.

    Returning only the ID and status (rather than the full TaskRead object)
    makes the contract clearer: the client gets a handle, it does not yet
    get a result.
    """

    task_id: str
    status: str
