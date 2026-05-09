"""Task-execution endpoints."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, require_roles
from app.core.roles import Role
from app.models.user import User
from app.schemas.task import TaskCreate, TaskRead, TaskSubmitResponse
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "/execute",
    response_model=TaskSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def execute_task(
    payload: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(Role.MANAGER)),
) -> TaskSubmitResponse:
    """Submit a task for asynchronous execution. Manager only.

    Returns 202 Accepted immediately with a `task_id` the client can use
    to poll `GET /tasks/{task_id}` for status and result.
    """
    try:
        task = task_service.create_task(db, payload, user_id=current_user.id)
    except ValueError as exc:
        # Unknown task_type — translate the service-layer error into a 400.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Schedule the actual work to run after the response is sent. The
    # runner opens its own DB session, so it doesn't share state with this
    # request.
    background_tasks.add_task(task_service.run_task_sync, task.id)

    return TaskSubmitResponse(task_id=task.id, status=task.status)


@router.get("/{task_id}", response_model=TaskRead)
def get_task_status(
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskRead:
    """Fetch the status and (if available) result of a task.

    Any authenticated user may read task status. In a production system
    you'd normally restrict this to the task's creator or admins.
    """
    task = task_service.get_task(db, task_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found",
        )
    return TaskRead.model_validate(task_service.task_to_dict(task))
