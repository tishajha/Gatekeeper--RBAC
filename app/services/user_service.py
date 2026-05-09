"""User-related business logic.

Routes call into this layer rather than touching the ORM directly. This
keeps routes thin and means the same logic is reusable from CLI scripts,
background jobs, or other entry points.
"""
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


def get_user_by_username(db: Session, username: str) -> User | None:
    """Look up a user by their unique username, or return None."""
    return db.query(User).filter(User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    """Look up a user by primary key."""
    return db.query(User).filter(User.id == user_id).first()


def list_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    """Return a page of users ordered by ID."""
    return db.query(User).order_by(User.id).offset(skip).limit(limit).all()


def create_user(db: Session, payload: UserCreate) -> User:
    """Create a new user, hashing the password before storage.

    Caller is responsible for catching uniqueness violations (the route
    layer does this so it can return a clean 409).
    """
    user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role=payload.role.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Return the user if credentials are valid, else None.

    This returns None for both missing users and wrong passwords so the
    caller can keep the error response identical and avoid exposing which
    part of the login failed.
    """
    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
