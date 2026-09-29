"""Database connection setup (SQLAlchemy 2.0).

The app talks to the database through a "session". Each API request gets its own
session via get_db(), and it is closed when the request finishes.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app import config


def _normalise_url(url: str) -> str:
    # Accept the common postgres:// and postgresql:// forms and point them at
    # the psycopg (v3) driver we install.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _make_engine(url: str):
    url = _normalise_url(url)
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            # In-memory DB (used by tests): share one connection so every
            # session sees the same tables.
            kwargs["poolclass"] = StaticPool
        return create_engine(url, **kwargs)
    # pool_pre_ping: test connections before use, so the app recovers
    # if PostgreSQL restarts (e.g. its pod is rescheduled).
    return create_engine(url, pool_pre_ping=True)


engine = _make_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: one DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they don't exist yet (fine for a project this size;
    bigger apps would use migrations, e.g. Alembic)."""
    from app import models  # noqa: F401  (registers the tables)

    Base.metadata.create_all(bind=engine)
