"""Tests for the check logic and the standalone checker job."""
import httpx

from app import checker, checks
from app.database import SessionLocal
from app.models import Check, Site


def test_check_url_up(monkeypatch):
    monkeypatch.setattr(checks.httpx, "get", lambda url, **kw: httpx.Response(200))
    result = checks.check_url("https://example.com/")
    assert result["is_up"] is True
    assert result["status_code"] == 200
    assert result["response_ms"] >= 0
    assert result["error"] is None


def test_check_url_server_error_counts_as_down(monkeypatch):
    monkeypatch.setattr(checks.httpx, "get", lambda url, **kw: httpx.Response(503))
    result = checks.check_url("https://example.com/")
    assert result["is_up"] is False
    assert result["status_code"] == 503


def test_check_url_connection_error(monkeypatch):
    def boom(url, **kw):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(checks.httpx, "get", boom)
    result = checks.check_url("https://example.com/")
    assert result["is_up"] is False
    assert result["status_code"] is None
    assert "ConnectError" in result["error"]


def test_checker_job_records_a_check_per_site(client, fake_checks):
    # "client" gives us fresh tables; add sites directly in the database.
    with SessionLocal() as db:
        db.add_all([Site(name="A", url="https://a.example/"), Site(name="B", url="https://b.example/")])
        db.commit()

    assert checker.main() == 0

    with SessionLocal() as db:
        assert db.query(Check).count() == 2
