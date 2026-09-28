"""ORM model package.

Import models here so Alembic and Base.metadata see them.
"""

from app.db.models.failure_lab import FailureLabRunORM
from app.db.models.integration import IntegrationORM
from app.db.models.oauth import (
    GitHubProfileORM,
    OAuthCredentialORM,
    OAuthSessionORM,
    ProviderRequestLogORM,
)

__all__ = [
    "IntegrationORM",
    "OAuthSessionORM",
    "OAuthCredentialORM",
    "GitHubProfileORM",
    "ProviderRequestLogORM",
    "FailureLabRunORM",
]
