"""Re-export models so `Base.metadata` is populated with every table.

When the seed script (or tests) calls `Base.metadata.create_all()`, it
only knows about models that have been imported somewhere in the process.
Importing all models here from a single place guarantees that simply
importing `app.models` is enough to register every table.
"""
from app.models.task import Task, TaskStatus
from app.models.user import User

__all__ = ["User", "Task", "TaskStatus"]
