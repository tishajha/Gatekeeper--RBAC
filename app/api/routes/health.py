"""Public health-check endpoint.

Intentionally trivial: just confirms the process is alive and accepting
requests. A real production deployment would extend this with a `/ready`
endpoint that also checks DB connectivity and any downstream dependencies.
"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Return a 200 OK if the service is up. No authentication required."""
    return {"status": "ok"}
