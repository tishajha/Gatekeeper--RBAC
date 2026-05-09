"""User-management endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_roles
from app.core.roles import Role
from app.schemas.user import UserCreate, UserRead
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "/",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(Role.ADMIN))],
)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
) -> UserRead:
    """Create a new user. Admin only.

    Returns 409 Conflict if the username is already taken.
    """
    if user_service.get_user_by_username(db, payload.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' already exists",
        )

    try:
        user = user_service.create_user(db, payload)
    except IntegrityError:
        # Race condition: another request created the same username between
        # our check above and our insert. Roll back and report cleanly.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{payload.username}' already exists",
        )
    return UserRead.model_validate(user)


@router.get(
    "/",
    response_model=list[UserRead],
    dependencies=[Depends(require_roles(Role.ADMIN, Role.MANAGER))],
)
def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[UserRead]:
    """List all users. Accessible to admins and managers."""
    users = user_service.list_users(db, skip=skip, limit=limit)
    return [UserRead.model_validate(u) for u in users]
