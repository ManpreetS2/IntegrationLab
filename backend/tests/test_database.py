"""Database and repository-level tests."""

import pytest

from app.models.integration import IntegrationCreate, IntegrationProvider
from app.repositories.integrations import integration_repository
from app.scripts.seed import seed_integrations
from tests.conftest import TEST_DATABASE_URL, assert_safe_test_database


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


def test_safe_test_database_accepts_names_ending_in_test() -> None:
    assert assert_safe_test_database(TEST_DATABASE_URL) == TEST_DATABASE_URL
    assert (
        assert_safe_test_database(
            "postgresql+psycopg://integrationlab:integrationlab@localhost:5432/my_feature_test"
        )
        is not None
    )


@pytest.mark.parametrize(
    "unsafe_name",
    ["integrationlab", "production", "contest_data", "latest"],
)
def test_safe_test_database_rejects_unsafe_names(unsafe_name: str) -> None:
    url = f"postgresql+psycopg://integrationlab:integrationlab@localhost:5432/{unsafe_name}"
    with pytest.raises(RuntimeError, match="ends with '_test'"):
        assert_safe_test_database(url)
