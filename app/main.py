"""Uptime Monitor API.

Run locally:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs:         http://localhost:8000/docs

Endpoints used by the platform (not just by people):
  /health   - liveness probe: is the process alive? (no DB call on purpose)
  /ready    - readiness probe: can it reach the database?
  /metrics  - scraped by Prometheus
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import metrics
from app.checks import latest_check, run_all_checks
from app.database import get_db, init_db
from app.logging_setup import setup_logging
from app.models import Check, Site
from app.schemas import CheckOut, RunResult, SiteCreate, SiteOut, SiteStatus

log = logging.getLogger("uptime.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once when the app starts.
    setup_logging()
    init_db()
    log.info("uptime monitor started")
    yield


app = FastAPI(title="Uptime Monitor", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def record_request_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    # Label by route template (/sites/{site_id}), not the raw path (/sites/7),
    # so the number of metric series stays small.
    route = request.scope.get("route")
    path = getattr(route, "path", "unmatched")
    metrics.HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    metrics.HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
    return response


# ---------- platform endpoints ----------

@app.get("/health", tags=["platform"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["platform"])
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.exception("readiness check failed: database unreachable")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "database unreachable")
    return {"status": "ready"}


@app.get("/metrics", tags=["platform"])
def prometheus_metrics(db: Session = Depends(get_db)):
    # Rebuild the per-site gauges from the database so deleted sites disappear
    # and checks made by the CronJob are included.
    metrics.SITE_UP.clear()
    metrics.SITE_RESPONSE_MS.clear()
    for site in db.scalars(select(Site)).all():
        last = latest_check(db, site.id)
        if last is None:
            continue
        metrics.SITE_UP.labels(site.name).set(1 if last.is_up else 0)
        if last.response_ms is not None:
            metrics.SITE_RESPONSE_MS.labels(site.name).set(last.response_ms)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------- sites ----------

def _get_site_or_404(db: Session, site_id: int) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found")
    return site


@app.post("/sites", response_model=SiteOut, status_code=status.HTTP_201_CREATED, tags=["sites"])
def create_site(payload: SiteCreate, db: Session = Depends(get_db)):
    url = str(payload.url)
    if db.scalar(select(Site).where(Site.url == url)):
        raise HTTPException(status.HTTP_409_CONFLICT, "site with this url already exists")
    site = Site(name=payload.name, url=url)
    db.add(site)
    db.commit()
    db.refresh(site)
    log.info("site added", extra={"site": site.name, "url": site.url})
    return site


@app.get("/sites", response_model=list[SiteOut], tags=["sites"])
def list_sites(db: Session = Depends(get_db)):
    return db.scalars(select(Site).order_by(Site.id)).all()


@app.get("/sites/{site_id}", response_model=SiteOut, tags=["sites"])
def get_site(site_id: int, db: Session = Depends(get_db)):
    return _get_site_or_404(db, site_id)


@app.delete("/sites/{site_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["sites"])
def delete_site(site_id: int, db: Session = Depends(get_db)):
    site = _get_site_or_404(db, site_id)
    db.delete(site)
    db.commit()
    log.info("site deleted", extra={"site": site.name, "url": site.url})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/sites/{site_id}/checks", response_model=list[CheckOut], tags=["checks"])
def site_checks(
    site_id: int,
    limit: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
):
    _get_site_or_404(db, site_id)
    stmt = (
        select(Check)
        .where(Check.site_id == site_id)
        .order_by(Check.checked_at.desc(), Check.id.desc())
        .limit(limit)
    )
    return db.scalars(stmt).all()


# ---------- status and running checks ----------

@app.get("/status", response_model=list[SiteStatus], tags=["checks"])
def overall_status(db: Session = Depends(get_db)):
    result = []
    for site in db.scalars(select(Site).order_by(Site.id)).all():
        last = latest_check(db, site.id)
        result.append(
            SiteStatus(
                id=site.id,
                name=site.name,
                url=site.url,
                is_up=last.is_up if last else None,
                status_code=last.status_code if last else None,
                response_ms=last.response_ms if last else None,
                last_checked=last.checked_at if last else None,
            )
        )
    return result


@app.post("/checks/run", response_model=RunResult, tags=["checks"])
def run_checks_now(db: Session = Depends(get_db)):
    results = run_all_checks(db)
    up = sum(1 for c in results if c.is_up)
    return RunResult(checked=len(results), up=up, down=len(results) - up)
