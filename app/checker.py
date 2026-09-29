"""Standalone checker: run one round of checks, then exit.

Run:  python -m app.checker

In Phase 6 this runs as a Kubernetes CronJob (e.g. every 5 minutes), using the
same container image as the API but a different command. It writes to the same
database, so the API's /status and /metrics show its results.
"""
import logging
import sys

from app.checks import run_all_checks
from app.database import SessionLocal, init_db
from app.logging_setup import setup_logging

log = logging.getLogger("uptime.checker")


def main() -> int:
    setup_logging()
    init_db()
    with SessionLocal() as db:
        results = run_all_checks(db)
    down = sum(1 for c in results if not c.is_up)
    log.info("check round finished", extra={"checked": len(results), "down": down})
    # A site being down is not a failure of this job, so exit 0 either way.
    # A crash (e.g. database unreachable) exits non-zero and Kubernetes will
    # mark the job as failed.
    return 0


if __name__ == "__main__":
    sys.exit(main())
