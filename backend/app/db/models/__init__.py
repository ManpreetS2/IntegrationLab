"""ORM model package.

Import models here so Alembic and Base.metadata see them.
"""

from app.db.models.integration import IntegrationORM

__all__ = ["IntegrationORM"]
