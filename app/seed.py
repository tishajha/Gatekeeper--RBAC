"""One-shot seed script: creates the database tables and a default admin.

Run with:
    python -m app.seed

Idempotent: re-running does nothing if the admin user already exists.
"""
from app.core.config import settings
from app.core.roles import Role
from app.db.session import Base, SessionLocal, engine
from app.schemas.user import UserCreate
from app.services import user_service

# Side-effect import: registers all models on Base.metadata.
import app.models  # noqa: F401


def main() -> None:
    """Create tables (if missing) and ensure a default admin exists."""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = user_service.get_user_by_username(
            db, settings.DEFAULT_ADMIN_USERNAME
        )
        if existing is not None:
            print(
                f"Admin user '{settings.DEFAULT_ADMIN_USERNAME}' already "
                "exists — nothing to do."
            )
            return

        admin = user_service.create_user(
            db,
            UserCreate(
                username=settings.DEFAULT_ADMIN_USERNAME,
                password=settings.DEFAULT_ADMIN_PASSWORD,
                role=Role.ADMIN,
            ),
        )
        print(
            f"Created admin user id={admin.id} username='{admin.username}' "
            f"role='{admin.role}'."
        )
        print(
            f"Login with username '{settings.DEFAULT_ADMIN_USERNAME}' and "
            f"password '{settings.DEFAULT_ADMIN_PASSWORD}'."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
