"""Idempotent seed of demo integrations (GitHub + Stripe).

Run from the backend directory with the virtualenv active:

    python -m app.scripts.seed

Safe to run multiple times — existing seed rows are left alone.
"""

from __future__ import annotations

import logging
import sys

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.integration import IntegrationCreate, IntegrationProvider
from app.repositories.integrations import integration_repository

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEED_INTEGRATIONS: list[tuple[str, IntegrationProvider]] = [
    ("GitHub", IntegrationProvider.GITHUB),
    ("Stripe", IntegrationProvider.STRIPE),
]


def seed_integrations(session: Session) -> int:
    """Insert missing demo rows. Returns how many rows were created."""
    created = 0
    for name, provider in SEED_INTEGRATIONS:
        existing = integration_repository.find_seed_by_name_and_provider(
            session,
            name=name,
            provider=provider.value,
        )
        if existing is not None:
            logger.info("Seed already present: %s (%s)", name, provider.value)
            continue

        integration_repository.create(
            session,
            IntegrationCreate(name=name, provider=provider),
        )
        created += 1
        logger.info("Seeded: %s (%s)", name, provider.value)
    return created


def main() -> int:
    """CLI entrypoint for demo seeding."""
    session = SessionLocal()
    try:
        created = seed_integrations(session)
        logger.info("Seed complete. New rows: %s", created)
        return 0
    except Exception:
        session.rollback()
        logger.exception("Seed failed")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
