"""HTTP routes for integrations."""

from typing import List

from fastapi import APIRouter, status

from app.models.integration import Integration, IntegrationCreate
from app.services.integration_store import store

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("", response_model=List[Integration])
def list_integrations() -> List[Integration]:
    """Return all integrations currently held in memory."""
    return store.list_all()


@router.post("", response_model=Integration, status_code=status.HTTP_201_CREATED)
def create_integration(payload: IntegrationCreate) -> Integration:
    """Create a new integration from the dashboard form."""
    return store.create(payload)
