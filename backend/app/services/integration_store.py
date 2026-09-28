"""In-memory store for integrations.

This is intentionally temporary. Data lives only in process memory and
disappears when the backend restarts. Day 2+ will replace this with
PostgreSQL persistence.
"""

from datetime import datetime, timezone
from typing import List
from uuid import uuid4

from app.models.integration import (
    Integration,
    IntegrationCreate,
    IntegrationProvider,
    IntegrationStatus,
)


class IntegrationStore:
    """Simple list-backed store used for Day 1 learning and demos."""

    def __init__(self) -> None:
        self._integrations: List[Integration] = []
        self._seed()

    def _seed(self) -> None:
        """Load the two starter integrations shown in the dashboard."""
        now = datetime.now(timezone.utc)
        self._integrations = [
            Integration(
                id=uuid4(),
                name="GitHub",
                provider=IntegrationProvider.GITHUB,
                status=IntegrationStatus.NOT_CONNECTED,
                created_at=now,
                last_checked_at=None,
            ),
            Integration(
                id=uuid4(),
                name="Stripe",
                provider=IntegrationProvider.STRIPE,
                status=IntegrationStatus.NOT_CONNECTED,
                created_at=now,
                last_checked_at=None,
            ),
        ]

    def list_all(self) -> List[Integration]:
        """Return every integration currently in memory."""
        return list(self._integrations)

    def create(self, payload: IntegrationCreate) -> Integration:
        """Create a new integration with generated id and defaults."""
        integration = Integration(
            id=uuid4(),
            name=payload.name,
            provider=payload.provider,
            status=IntegrationStatus.NOT_CONNECTED,
            created_at=datetime.now(timezone.utc),
            last_checked_at=None,
        )
        self._integrations.append(integration)
        return integration


# Module-level singleton so all routes share the same Day 1 store.
store = IntegrationStore()
