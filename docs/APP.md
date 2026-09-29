# Uptime Monitor: how the app works

A small FastAPI service that watches websites and records whether they're up.
The app is deliberately simple: it exists to be deployed, monitored and operated.

## Files

| File | What it does |
| --- | --- |
| `app/config.py` | Reads all settings from environment variables |
| `app/database.py` | Connects to the database; one session per request |
| `app/models.py` | Tables: `sites` and `checks` |
| `app/schemas.py` | Shapes of request/response JSON (validation + `/docs`) |
| `app/checks.py` | Requests a URL, times it, saves the result |
| `app/main.py` | The API endpoints |
| `app/checker.py` | Runs one round of checks and exits (future Kubernetes CronJob) |
| `app/metrics.py` | Prometheus metrics definitions |
| `app/logging_setup.py` | JSON logs to stdout |
| `tests/` | pytest tests (in-memory SQLite, no real HTTP calls) |

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./uptime.db` | e.g. `postgresql+psycopg://user:pass@db:5432/uptime` |
| `CHECK_TIMEOUT_SECONDS` | `5` | A site slower than this counts as down |
| `LOG_LEVEL` | `INFO` | |

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness probe (no DB call) |
| GET | `/ready` | Readiness probe (checks the DB) |
| GET | `/metrics` | Prometheus metrics, incl. `site_up` and `site_response_ms` |
| POST | `/sites` | Add a site `{"name": "...", "url": "https://..."}` |
| GET | `/sites` | List sites |
| GET | `/sites/{id}` | One site |
| DELETE | `/sites/{id}` | Remove a site and its history |
| GET | `/sites/{id}/checks?limit=20` | Check history, newest first |
| GET | `/status` | Every site with its latest result |
| POST | `/checks/run` | Check every site now |

## Run it

```bash
pip install -r requirements-dev.txt
pytest                                                   # run the tests
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 # start the API
python -m app.checker                                    # one round of checks
```
