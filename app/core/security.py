"""Security helpers for password hashing and JWT handling.

The code does not import FastAPI so these helpers can be reused from
non-HTTP contexts such as scripts, tests, or admin tools.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Bcrypt is a solid default: slow by design, salted automatically, and
# widely supported. `deprecated="auto"` lets passlib rehash hashes when the
# scheme changes.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if the plaintext matches the stored hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str | int,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        subject: Identifier for the user. Stored in the standard `sub` claim.
        role: The user's role; embedded so we don't have to hit the DB on
            every request to know what someone is allowed to do.
        expires_delta: Override for the default token lifetime.

    Returns:
        A JWT string signed with the configured secret and algorithm.
    """
    expire_minutes = (
        expires_delta.total_seconds() / 60
        if expires_delta is not None
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    to_encode: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT.

    Raises:
        JWTError: If the token is malformed, expired, or signed with the
            wrong key. Callers should translate this into an HTTP 401.
    """
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        # Re-raise so the auth dependency can turn this into a 401 response.
        raise
