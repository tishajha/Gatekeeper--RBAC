"""Pydantic schemas for authentication tokens."""
from pydantic import BaseModel


class Token(BaseModel):
    """Response body of the login endpoint."""

    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Decoded JWT payload. Useful for type-safe access to claims in tests."""

    sub: str
    role: str
    exp: int | None = None
