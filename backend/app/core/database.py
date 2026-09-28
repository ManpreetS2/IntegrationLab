"""SQLAlchemy engine and request-scoped session factory.

Engine  = shared connection pool / infrastructure
Session = unit of work for one request
"""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# Application-global engine. Sessions are created per request via get_db().
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    # Fail fast when PostgreSQL is unreachable instead of hanging the request.
    connect_args={"connect_timeout": 3},
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped Session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_connection(session: Session) -> bool:
    """Return True when PostgreSQL answers a simple connectivity probe."""
    session.execute(text("SELECT 1"))
    return True
