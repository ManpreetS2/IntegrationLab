"""Database and repository-level tests."""

from app.models.integration import IntegrationCreate, IntegrationProvider
from app.repositories.integrations import integration_repository
from app.scripts.seed import seed_integrations


def test_repository_create_and_list(db_session) -> None:
    before = integration_repository.list_all(db_session)
    assert len(before) == 2

    created = integration_repository.create(
        db_session,
        IntegrationCreate(name="Repo Create", provider=IntegrationProvider.GITHUB),
    )

    assert created.id is not None
    assert created.name == "Repo Create"
    assert created.provider == "github"
    assert created.status == "not_connected"

    after = integration_repository.list_all(db_session)
    assert len(after) == 3
    assert any(row.id == created.id for row in after)


def test_seed_is_idempotent(db_session) -> None:
    first = seed_integrations(db_session)
    second = seed_integrations(db_session)

    assert first == 0  # already seeded by fixture
    assert second == 0
    assert len(integration_repository.list_all(db_session)) == 2


def test_test_database_name_contains_test() -> None:
    """Guardrail documented in conftest — keep this assertion visible."""
    from tests.conftest import TEST_DATABASE_URL

    assert "test" in TEST_DATABASE_URL.lower()
