# Code Structure: aws-k8s-platform

## Repository Layout

```text
.
├── app/                         Python package: Uptime Monitor API + checker
├── tests/                       pytest suite
├── helm/uptime-monitor/         Helm chart (values.yaml, values-aws.yaml, values-gitops.yaml, templates/)
├── gitops/uptime-app.yaml       Argo CD Application (minikube)
├── k8s/                         Raw manifests (Phase 5 predecessor of the chart)
├── monitoring/                  Values for kube-prometheus-stack, Loki, Alloy + Grafana dashboard JSON
├── infra/                       Terraform: bootstrap/, envs/{dev,prod}/, modules/{network,compute,registry}/
├── scripts/deploy-on-server.sh  Runs on EC2 via SSM: helm upgrade --atomic
├── .github/workflows/           ci.yml, deploy.yml
├── .devcontainer/               Codespace definition
├── docs/                        APP, RUNBOOK, SECURITY, TROUBLESHOOTING, incidents/, aidlc/ (intent)
├── Dockerfile, .dockerignore, docker-compose.yml
├── pytest.ini, ruff.toml, requirements-dev.txt
└── uptime.db                    committed SQLite runtime file (an artifact, not source)
```

This knowledge base leaves out the AI-DLC install (`.claude/`, `aidlc/`), the tool caches, and the `.terraform/` provider
folders. The full coverage record is in `reverse-engineering-timestamp.md`.

## Python Package `app/`

### File Classification

| File | Lines | Category | Responsibility | Internal imports |
|---|---|---|---|---|
| `app/__init__.py` | 0 | Package marker | n/a | n/a |
| `app/config.py` | 16 | Configuration | Reads `DATABASE_URL` (default `sqlite:///./uptime.db`), `CHECK_TIMEOUT_SECONDS` (default 5) and `LOG_LEVEL` (default INFO) from the environment | none |
| `app/database.py` | 58 | Repository / infrastructure | Engine factory, `SessionLocal`, `Base`, the `get_db()` dependency, and `init_db()` (runs `create_all`). The factory rewrites `postgres://` to `postgresql+psycopg://`, uses StaticPool for in-memory SQLite and `pool_pre_ping` for Postgres | `config`; `models` (imported lazily) |
| `app/models.py` | 47 | Model / Entity | SQLAlchemy 2.0 models `Site` and `Check` (see `api-documentation.md` § Data Model) | `database` |
| `app/schemas.py` | 51 | Model / DTO | Pydantic models `SiteCreate`, `SiteOut`, `CheckOut`, `SiteStatus`, `RunResult` | none |
| `app/checks.py` | 65 | Service | `check_url()`, `run_all_checks()`, `latest_check()` | `config`, `models` |
| `app/metrics.py` | 23 | Utility (observability) | Prometheus Counter, Histogram and two Gauges | none |
| `app/logging_setup.py` | 36 | Utility (observability) | `JsonFormatter`, which emits only whitelisted extra fields, and `setup_logging()` to stdout | `config` |
| `app/main.py` | 171 | Controller and Middleware | The FastAPI app, its lifespan (logging and `init_db`), the request-metrics middleware, and 10 routes | `metrics`, `checks`, `database`, `logging_setup`, `models`, `schemas` |
| `app/checker.py` | 33 | Entry point (batch) | `main()` runs one round of checks and returns 0 unless it crashes | `checks`, `database`, `logging_setup` |

### Internal Dependency Graph (adjacency list)

```text
config        -> []
database      -> [config, models (lazy, inside init_db)]
models        -> [database]
schemas       -> []
metrics       -> []
logging_setup -> [config]
checks        -> [config, models]
main          -> [metrics, checks, database, logging_setup, models, schemas]
checker       -> [checks, database, logging_setup]
```

There are no circular imports at load time. The lazy import inside `init_db()` (`app/database.py:56`) breaks the cycle
between `database` and `models`.

### Code Patterns

- **Dependency injection**: FastAPI's `Depends(get_db)` gives each request its own session (`app/database.py:44-50`).
- **Engine created at import time**: `engine` is built when the module loads (`app/database.py:36`). This is why the tests
  must set `DATABASE_URL` before importing the app (`tests/conftest.py:8-9`).
- **One package, two entry points**: `uvicorn app.main:app` (the Dockerfile CMD) and `python -m app.checker` (the CronJob command).
- **Structured logging**: calls take the form `log.info(msg, extra={...})`, and only the keys in `_EXTRA_FIELDS` are emitted
  (`site`, `url`, `is_up`, `status_code`, `response_ms`, `error`, `checked`, `down`; see `app/logging_setup.py:12`).
- **Metric label hygiene**: the middleware labels requests by route template, not by raw path (`app/main.py:47-51`).
- **Error mapping**:
  - `HTTPException` produces 404, 409 and 503 responses.
  - Transport errors during a check become a "down" result, with the message cut to 500 characters (`app/checks.py:25-32`).
  - Other database errors are not handled.
- **Gauges rebuilt per scrape**: `/metrics` clears and repopulates the site gauges from the database (`app/main.py:77-85`).
  The "latest check for each site" query is repeated per site in both `/metrics` and `/status`, an N+1 pattern.

## Tests `tests/`

| File | Category | Content |
|---|---|---|
| `tests/conftest.py` | Fixtures | Sets `DATABASE_URL=sqlite://` before the app is imported. Provides the `client` fixture (drop and recreate tables, then a `TestClient`), the `fake_checks` fixture (monkeypatches `app.checks.check_url`) and the `DOWN` constant |
| `tests/test_api.py` | Integration (in-process) | 16 tests: health and ready; site create, list, get and delete; validation (409, 422, 404); check ordering and limit validation; metric gauges and the removal of deleted sites |
| `tests/test_checks.py` | Unit | 4 tests: `check_url` up, 503 counted as down, connection error, and `checker.main()` writing one check per site |

The test baseline and coverage gaps are in `code-quality-assessment.md`.

## Helm Chart `helm/uptime-monitor/`

| File | Kind | Rendered when |
|---|---|---|
| `Chart.yaml` | Chart metadata (`version 0.1.0`, `appVersion "dev"`) | n/a |
| `values.yaml` | Defaults | n/a |
| `values-aws.yaml` | AWS k3s overrides: ECR repository, empty `tag`, `ecr-pull`, ingress on, backup on | used by `deploy-on-server.sh` |
| `values-gitops.yaml` | minikube overrides: ECR repository, **pinned tag**, monitoring on, ingress and backup off | used by Argo CD |
| `templates/api.yaml` | Service `api` (port name `http`, 80 to 8000, label `app: api`) and Deployment `api` | always |
| `templates/checker.yaml` | CronJob `checker` | always |
| `templates/postgres.yaml` | Service `db` and StatefulSet `postgres` (PVC `data`) | always |
| `templates/ingress.yaml` | Ingress `api` | `ingress.enabled` |
| `templates/servicemonitor.yaml` | ServiceMonitor `api` | `monitoring.enabled` |
| `templates/prometheusrule.yaml` | PrometheusRule `uptime-monitor` | `monitoring.enabled` |
| `templates/backup-cronjob.yaml` | CronJob `db-backup` | `backup.enabled` |

The chart has no `_helpers.tpl`, no `NOTES.txt`, and no ServiceAccount, RBAC or NetworkPolicy templates. Resource names
are fixed (`api`, `db`, `checker`) rather than prefixed with the release name. Only the `api` and `postgres` pods
carry an `app` label. The checker and backup Job pods have none, so their `app` label in Loki is empty.

### Where the image tag is set

| Location | Value at HEAD | Consumer |
|---|---|---|
| `helm/uptime-monitor/values.yaml:5-6` | `uptime-monitor:dev` | local or default installs |
| `helm/uptime-monitor/values-gitops.yaml:2-3` | `099021515478.dkr.ecr.eu-west-2.amazonaws.com/uptime-monitor:d01d633f2faad1d4537e6e924a3e0965fd9571cd` | Argo CD (minikube) |
| `helm/uptime-monitor/values-aws.yaml:3-4` | ECR repository, `tag: ""` | overridden by the next row |
| `scripts/deploy-on-server.sh:22` | `--set image.tag="$SHA"` (the merge commit SHA) | AWS k3s |
| `k8s/api.yaml:30`, `k8s/checker-cronjob.yaml:19` | `uptime-monitor:dev` | the legacy raw manifests |

`templates/api.yaml:41` and `templates/checker.yaml:23` both render the same
`"{{ .Values.image.repository }}:{{ .Values.image.tag }}"`.

## Other Directories

| Directory | Content | File categories |
|---|---|---|
| `gitops/` | One Argo CD Application | Configuration |
| `k8s/` | `api.yaml`, `checker-cronjob.yaml`, `postgres.yaml`; namespace `uptime` hard-coded; no Ingress, monitoring or backup | Configuration (legacy) |
| `monitoring/` | `kube-prometheus-stack-values.yaml`, `loki-values.yaml`, `alloy-values.yaml`, and `dashboards/uptime-monitor.json` (6 panels, provisioned by nothing in the repo) | Configuration, Static asset |
| `infra/` | Root modules `bootstrap/`, `envs/dev/`, `envs/prod/`. Child modules: `modules/network` (VPC, public subnet, IGW, SG), `modules/compute` (EC2, IAM role and profile, `user_data.sh`), `modules/registry` (ECR and its lifecycle policy) | Configuration (IaC) |
| `scripts/` | `deploy-on-server.sh` only. `scripts/ui.sh`, which `docs/RUNBOOK.md:205` refers to, does not exist | Utility |
| `.github/workflows/` | `ci.yml`, `deploy.yml` | Configuration (pipeline) |
| `.devcontainer/` | `devcontainer.json` | Configuration |
| `docs/` | Operator documentation and the incident review; `docs/aidlc/` holds the intent | Documentation |

Each of these is described as a component in `component-inventory.md`.
