"""FastAPI dependencies for database access, authentication, and RBAC.

Centralising these here keeps route handlers thin: a route just declares
what it needs (an authenticated user, a specific role) via `Depends`, and
the dependency does all the work.
"""
from collections.abc import Callable, Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models.user import User

# `tokenUrl` is the path Swagger UI hits when you click "Authorize" — it
# does NOT need to be a real route on the same router; it just has to be
# the full path to the login endpoint.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and guarantee it's closed afterwards.

    Using `yield` (rather than `return`) means FastAPI treats this as a
    context manager and runs the cleanup code after the response is sent,
    even if the route raised.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer token.

    Raises:
        HTTPException 401: if the token is missing, malformed, expired, or
            references a user that no longer exists / is deactivated.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        # `WWW-Authenticate` is required by RFC 6750 on 401 responses for
        # bearer-token APIs. Swagger UI also relies on it.
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_roles(*allowed_roles: Role) -> Callable[[User], User]:
    """Return a dependency that allows only the listed roles.

    Implemented as a factory so the role list is captured at import time
    and there's no runtime overhead per request beyond a set membership
    check.

    Usage:
        @router.post("/users", dependencies=[Depends(require_roles(Role.ADMIN))])
        def create_user(...): ...

    Or, if you also need the user object inside the handler:
        def create_user(user: User = Depends(require_roles(Role.ADMIN))): ...
    """
    allowed = {r.value for r in allowed_roles}

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{current_user.role}' is not permitted to access "
                    f"this resource. Required: {sorted(allowed)}"
                ),
            )
        return current_user

    return role_checker
