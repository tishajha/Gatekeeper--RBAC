"""Role definitions and the role-permission matrix.

The `Role` enum is the single source of truth for what roles exist in the
system. The `ROLE_HIERARCHY` constant is informational only — actual
permission checks happen via the `require_roles` dependency, which compares
the caller's role against an explicit allowlist per endpoint.
"""
from enum import Enum


class Role(str, Enum):
    """User roles, ordered from highest to lowest privilege.

    Inheriting from `str` makes the enum JSON-serializable and means
    Pydantic can validate role strings directly against this enum.
    """

    ADMIN = "admin"
    MANAGER = "manager"
    OPERATOR = "operator"
    VIEWER = "viewer"


# Documentation only — not used at runtime. Intentionally kept here so a
# new contributor can see the intended privilege ordering at a glance.
ROLE_HIERARCHY: dict[Role, int] = {
    Role.ADMIN: 4,
    Role.MANAGER: 3,
    Role.OPERATOR: 2,
    Role.VIEWER: 1,
}
