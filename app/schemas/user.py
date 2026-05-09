"""Pydantic schemas for User-related requests and responses.

Request and response schemas are kept separate. The response schema has no
`password` field, which makes it impossible to accidentally leak a hash.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.roles import Role


class UserBase(BaseModel):
    """Shared fields between Create and Read schemas."""

    username: str = Field(..., min_length=3, max_length=64)
    role: Role = Role.VIEWER


class UserCreate(UserBase):
    """Payload accepted by `POST /users/`."""

    password: str = Field(..., min_length=6, max_length=128)


class UserRead(UserBase):
    """Public-facing user representation. Never contains the password hash."""

    id: int
    is_active: bool
    created_at: datetime

    # Allows Pydantic to read attributes off SQLAlchemy ORM objects directly.
    model_config = ConfigDict(from_attributes=True)
