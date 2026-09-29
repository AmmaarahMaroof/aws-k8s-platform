"""Shared test setup.

Tests use an in-memory SQLite database and never make real HTTP requests:
the site check is replaced with a fake, so tests are fast and reliable in CI.
"""
import os

# Must be set before the app is imported, because the DB engine is created at import.
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient

from app import models  # noqa: F401
from app.database import Base, engine
from app.main import app


@pytest.fixture
def client():
    # Fresh, empty tables for every test.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:  # "with" runs the app's startup code
        yield c


@pytest.fixture
def fake_checks(monkeypatch):
    """Replace real HTTP checks. Put a URL in the returned dict to control its result;
    any other URL is reported as up (200, 42 ms)."""
    outcomes: dict[str, dict] = {}

    def fake_check_url(url, timeout=None):
        return outcomes.get(
            url, {"is_up": True, "status_code": 200, "response_ms": 42, "error": None}
        )

    monkeypatch.setattr("app.checks.check_url", fake_check_url)
    return outcomes


DOWN = {"is_up": False, "status_code": None, "response_ms": None, "error": "ConnectError: refused"}
