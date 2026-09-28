"""Health check route used to confirm the backend is running."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Simple liveness response for Day 1 foundation checks."""
    return {"status": "ok"}
