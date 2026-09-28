"""Repositories for OAuth, GitHub profiles, and provider request logs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.oauth import (
    GitHubProfileORM,
    OAuthCredentialORM,
    OAuthSessionORM,
    ProviderRequestLogORM,
)


class OAuthSessionRepository:
    def create(
        self,
        session: Session,
        *,
        integration_id: UUID,
        provider: str,
        state_hash: str,
        code_verifier_encrypted: str,
        expires_at: datetime,
    ) -> OAuthSessionORM:
        row = OAuthSessionORM(
            id=uuid4(),
            integration_id=integration_id,
            provider=provider,
            state_hash=state_hash,
            code_verifier_encrypted=code_verifier_encrypted,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            used_at=None,
        )
        session.add(row)
        session.flush()
        return row

    def get_by_state_hash(self, session: Session, state_hash: str) -> OAuthSessionORM | None:
        statement = select(OAuthSessionORM).where(OAuthSessionORM.state_hash == state_hash)
        return session.scalars(statement).first()

    def mark_used(self, session: Session, oauth_session: OAuthSessionORM) -> None:
        oauth_session.used_at = datetime.now(timezone.utc)
        session.add(oauth_session)


class OAuthCredentialRepository:
    def get_by_integration_id(
        self,
        session: Session,
        integration_id: UUID,
    ) -> OAuthCredentialORM | None:
        statement = select(OAuthCredentialORM).where(
            OAuthCredentialORM.integration_id == integration_id
        )
        return session.scalars(statement).first()

    def upsert(
        self,
        session: Session,
        *,
        integration_id: UUID,
        provider: str,
        access_token_encrypted: str,
        token_type: str | None,
        granted_scopes: str | None,
    ) -> OAuthCredentialORM:
        existing = self.get_by_integration_id(session, integration_id)
        now = datetime.now(timezone.utc)
        if existing is None:
            row = OAuthCredentialORM(
                id=uuid4(),
                integration_id=integration_id,
                provider=provider,
                access_token_encrypted=access_token_encrypted,
                token_type=token_type,
                granted_scopes=granted_scopes,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            return row

        existing.provider = provider
        existing.access_token_encrypted = access_token_encrypted
        existing.token_type = token_type
        existing.granted_scopes = granted_scopes
        existing.updated_at = now
        session.add(existing)
        session.flush()
        return existing


class GitHubProfileRepository:
    def get_by_integration_id(
        self,
        session: Session,
        integration_id: UUID,
    ) -> GitHubProfileORM | None:
        return session.get(GitHubProfileORM, integration_id)

    def upsert(
        self,
        session: Session,
        *,
        integration_id: UUID,
        github_user_id: int,
        login: str,
        avatar_url: str | None,
        html_url: str | None,
        public_repos: int | None,
    ) -> GitHubProfileORM:
        existing = self.get_by_integration_id(session, integration_id)
        now = datetime.now(timezone.utc)
        if existing is None:
            row = GitHubProfileORM(
                integration_id=integration_id,
                github_user_id=github_user_id,
                login=login,
                avatar_url=avatar_url,
                html_url=html_url,
                public_repos=public_repos,
                connected_at=now,
                last_synced_at=now,
            )
            session.add(row)
            session.flush()
            return row

        existing.github_user_id = github_user_id
        existing.login = login
        existing.avatar_url = avatar_url
        existing.html_url = html_url
        existing.public_repos = public_repos
        existing.last_synced_at = now
        session.add(existing)
        session.flush()
        return existing


class ProviderRequestLogRepository:
    def create(
        self,
        session: Session,
        *,
        integration_id: UUID | None,
        provider: str,
        method: str,
        endpoint: str,
        status_code: int | None,
        latency_ms: int,
        error_message: str | None = None,
        rate_limit_remaining: int | None = None,
        is_simulated: bool = False,
        scenario: str | None = None,
    ) -> ProviderRequestLogORM:
        row = ProviderRequestLogORM(
            id=uuid4(),
            integration_id=integration_id,
            provider=provider,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            latency_ms=latency_ms,
            timestamp=datetime.now(timezone.utc),
            error_message=error_message,
            rate_limit_remaining=rate_limit_remaining,
            is_simulated=is_simulated,
            scenario=scenario,
        )
        session.add(row)
        session.flush()
        return row

    def list_recent(
        self,
        session: Session,
        *,
        provider: str | None = None,
        integration_id: UUID | None = None,
        limit: int = 50,
        is_simulated: bool | None = None,
        scenario: str | None = None,
    ) -> list[ProviderRequestLogORM]:
        statement = select(ProviderRequestLogORM).order_by(
            ProviderRequestLogORM.timestamp.desc()
        )
        if provider:
            statement = statement.where(ProviderRequestLogORM.provider == provider)
        if integration_id is not None:
            statement = statement.where(
                ProviderRequestLogORM.integration_id == integration_id
            )
        if is_simulated is not None:
            statement = statement.where(ProviderRequestLogORM.is_simulated == is_simulated)
        if scenario:
            statement = statement.where(ProviderRequestLogORM.scenario == scenario)
        statement = statement.limit(limit)
        return list(session.scalars(statement).all())


oauth_session_repository = OAuthSessionRepository()
oauth_credential_repository = OAuthCredentialRepository()
github_profile_repository = GitHubProfileRepository()
provider_request_log_repository = ProviderRequestLogRepository()
