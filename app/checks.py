"""The monitoring logic: request a URL, time it, record the result.

Used by both the API (POST /checks/run) and the standalone checker job
(app/checker.py), which Kubernetes will run on a schedule as a CronJob.
"""
import logging
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import config
from app.models import Check, Site

log = logging.getLogger("uptime.checks")


def check_url(url: str, timeout: float | None = None) -> dict:
    """Request one URL. Any status below 400 counts as up."""
    timeout = timeout or config.CHECK_TIMEOUT_SECONDS
    start = time.perf_counter()
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        # Timeouts, DNS failures, refused connections, TLS errors...
        return {
            "is_up": False,
            "status_code": None,
            "response_ms": None,
            "error": f"{type(exc).__name__}: {exc}"[:500],
        }
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return {
        "is_up": resp.status_code < 400,
        "status_code": resp.status_code,
        "response_ms": elapsed_ms,
        "error": None,
    }


def run_all_checks(db: Session) -> list[Check]:
    """Check every site once and save the results."""
    results = []
    for site in db.scalars(select(Site).order_by(Site.id)).all():
        outcome = check_url(site.url)
        check = Check(site_id=site.id, **outcome)
        db.add(check)
        results.append(check)
        log.info(
            "checked site",
            extra={"site": site.name, "url": site.url, **outcome},
        )
    db.commit()
    return results


def latest_check(db: Session, site_id: int) -> Check | None:
    stmt = (
        select(Check)
        .where(Check.site_id == site_id)
        .order_by(Check.checked_at.desc(), Check.id.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()
