# API Documentation: aws-k8s-platform

This file owns every interface contract: the REST API, data model, metrics, alert rules, logs, configuration,
Kubernetes objects and the cloud APIs the pipelines call. It also lists the read surfaces an incident investigator uses.

## 1. Uptime Monitor REST API (FastAPI)

- **Source**: `app/main.py`.
- **Identity**: title "Uptime Monitor", version `0.1.0`, OpenAPI docs at `/docs`.
- **Serving**: uvicorn on port **8000**. In the cluster, Service `api` listens on port 80 (port name `http`). On AWS,
  Ingress `api` (Traefik) serves `/` on port 80, reachable only from the allowed CIDR.
- **Authentication**: none on any endpoint.
- **Rate limiting**: none.
- **Middleware**: `record_request_metrics` records `http_requests_total{method,path,status}` and
  `http_request_duration_seconds{method,path}`, where `path` is the route template, or `unmatched`.

| # | Method | Path | Tag | Request | Success | Errors | Notes |
|---|---|---|---|---|---|---|---|
| 1 | GET | `/health` | platform | none | 200 `{"status":"ok"}` | none | Liveness probe. Deliberately touches no database |
| 2 | GET | `/ready` | platform | none | 200 `{"status":"ready"}` | 503 `database unreachable` | Readiness probe. Runs `SELECT 1` and logs failures with `log.exception` (including the traceback) |
| 3 | GET | `/metrics` | platform | none | 200 Prometheus text | none | Rebuilds the site gauges from the database on every call |
| 4 | POST | `/sites` | sites | `SiteCreate` | 201 `SiteOut` | 409 duplicate URL; 422 validation | The URL is stored as `str(HttpUrl)`, so a bare host gains a trailing `/` |
| 5 | GET | `/sites` | sites | none | 200 `SiteOut[]` ordered by id | none | |
| 6 | GET | `/sites/{site_id}` | sites | path int | 200 `SiteOut` | 404 `site not found` | |
| 7 | DELETE | `/sites/{site_id}` | sites | path int | 204 | 404 | Also deletes the site's checks |
| 8 | GET | `/sites/{site_id}/checks` | checks | `limit` query, 1-500, default 20 | 200 `CheckOut[]`, newest first | 404; 422 bad limit | |
| 9 | GET | `/status` | checks | none | 200 `SiteStatus[]` | none | The latest check for each site, or nulls if it was never checked |
| 10 | POST | `/checks/run` | checks | none | 200 `RunResult` | 500 on database failure (not handled) | Makes synchronous outbound HTTP requests to every stored URL |

That makes 10 application routes: 3 tagged platform, 4 tagged sites and 3 tagged checks. FastAPI also serves its
default `/docs`, `/redoc` and `/openapi.json`.

### Schemas (`app/schemas.py`)

| Schema | Fields |
|---|---|
| `SiteCreate` | `name: str` (1-100 characters), `url: HttpUrl` |
| `SiteOut` | `id: int`, `name: str`, `url: str`, `created_at: datetime` |
| `CheckOut` | `id`, `site_id`, `checked_at`, `is_up: bool`, `status_code: int?`, `response_ms: int?`, `error: str?` |
| `SiteStatus` | `id`, `name`, `url`, `is_up: bool?`, `status_code: int?`, `response_ms: int?`, `last_checked: datetime?` |
| `RunResult` | `checked: int`, `up: int`, `down: int` |

### Data Model (`app/models.py`)

| Table | Column | Type | Constraints |
|---|---|---|---|
| `sites` | `id` | Integer | primary key |
| | `name` | String(100) | |
| | `url` | String(500) | UNIQUE |
| | `created_at` | DateTime (with time zone) | defaults to `utcnow` |
| `checks` | `id` | Integer | primary key |
| | `site_id` | Integer | foreign key to `sites.id` with ON DELETE CASCADE; indexed |
| | `checked_at` | DateTime (with time zone) | defaults to `utcnow`; indexed |
| | `is_up` | Boolean | |
| | `status_code` | Integer | nullable |
| | `response_ms` | Integer | nullable |
| | `error` | Text | nullable; the caller cuts it to 500 characters |

The API and the checker both create the schema with `Base.metadata.create_all` at startup. There are no migrations, and
nothing prunes old `checks` rows. The committed `uptime.db` has exactly this schema.

## 2. Metrics and Alerting Contract

### Application metrics (`app/metrics.py`)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `http_requests_total` | Counter | `method`, `path`, `status` | API requests handled |
| `http_request_duration_seconds` | Histogram (default buckets) | `method`, `path` | API latency |
| `site_up` | Gauge | `site` (the site **name**) | 1 if the latest stored check succeeded, else 0. It is the same however old that check is |
| `site_response_ms` | Gauge | `site` | Response time of the latest check; not set when the value is null |

No metric reports when the last check happened, or how many checks succeeded or failed.

- **Scrape config**: ServiceMonitor `api` selects `app: api`, port `http`, path `/metrics`, every `15s`
  (`helm/uptime-monitor/templates/servicemonitor.yaml`). The resulting `job` label is `api`; the alert rules and the
  dashboard depend on it.
- **Platform metrics** the repo relies on but does not define, from kube-state-metrics in kube-prometheus-stack:
  `kube_pod_container_status_restarts_total`, `kube_pod_container_status_waiting_reason`, and the `ALERTS` series
  (used in `docs/RUNBOOK.md:236-238` and the incident review).

### Alert rules (PrometheusRule `uptime-monitor`, `templates/prometheusrule.yaml`)

| Alert | Expression | For | Severity |
|---|---|---|---|
| `MonitoredSiteDown` | `max by (site) (site_up) == 0` | 2m | warning |
| `ApiPodRestarting` | `increase(kube_pod_container_status_restarts_total{namespace="<release ns>"}[15m]) > 2` (every container in the namespace) | 1m | critical |
| `ApiHighErrorRate` | `sum(rate(http_requests_total{job="api",status=~"5.."}[5m])) / sum(rate(http_requests_total{job="api"}[5m])) > 0.05` | 5m | critical |

The built-in kube-prometheus-stack rules, such as `KubePodNotReady` and `Watchdog`, are also active
(`docs/RUNBOOK.md:94`, incident review line 21). The repo has no Alertmanager route or receiver configuration.

### Grafana dashboard (`monitoring/dashboards/uptime-monitor.json`)

The dashboard has uid `uptime-monitor`, schemaVersion 39, refreshes every 30s, and shows the last 30 minutes by default.
Its panels set no datasource, and no query sets `instant`.

| Panel | Type | Query |
|---|---|---|
| Monitored sites | stat | `max by (site) (site_up)` |
| Site response time | timeseries | `max by (site) (site_response_ms)` |
| API requests per second | timeseries | `sum by (path) (rate(http_requests_total{job="api"}[5m]))` |
| API error rate | timeseries | the 5xx ratio, the same expression as `ApiHighErrorRate` |
| API p95 latency | timeseries | `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{job="api"}[5m])))` |
| Pod restarts (last hour) | timeseries | `sum by (pod) (increase(kube_pod_container_status_restarts_total{namespace="uptime"}[1h]))` |

## 3. Log Contract

- **Format**: one JSON object per line on stdout (`app/logging_setup.py`). Every line has `time`, `level`, `logger` and
  `message`. Optional fields are `site`, `url`, `is_up`, `status_code`, `response_ms`, `error`, `checked`, `down` and
  `exception`.
- **Logger names**: `uptime.api`, `uptime.checks`, `uptime.checker`. Uvicorn's own loggers keep uvicorn's handlers
  and plain-text format.
- **Key messages**: `uptime monitor started`, `site added`, `site deleted`, `checked site`, `check round finished`, and
  `readiness check failed: database unreachable` (with a traceback).
- **Sensitive content**:
  - `url` is logged exactly as stored, so credentials embedded in a URL would be logged.
  - `error` and `exception` carry raw exception text, and a SQLAlchemy connection error can include connection details.
- **Loki**:
  - Alloy adds the labels `namespace`, `pod`, `container` and `app`.
  - The push endpoint is `http://loki.monitoring.svc:3100/loki/api/v1/push`, with `auth_enabled: false`.
  - The documented queries are in `docs/RUNBOOK.md:224-230`.

## 4. Configuration Contract (environment variables and Secrets)

| Variable | Default | Source in Kubernetes |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./uptime.db` | Secret `app-config` through `envFrom`; its value is `postgresql+psycopg://uptime:<password>@db:5432/uptime` |
| `CHECK_TIMEOUT_SECONDS` | `5` | not set by the chart |
| `LOG_LEVEL` | `INFO` | not set by the chart |

| Secret | Keys | Used by | Created by |
|---|---|---|---|
| `app-config` | `DATABASE_URL` (includes the password) | api and checker, through `envFrom` | hand (`docs/RUNBOOK.md:149`) |
| `db-credentials` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | postgres and the backup `pg-dump` step | hand (`docs/RUNBOOK.md:148`) |
| `ecr-pull` | docker-registry config holding a 12-hour ECR token | image pulls on AWS and minikube | `deploy-on-server.sh:14-17` on AWS; by hand on minikube (`docs/RUNBOOK.md:194-200`) |
| `argocd-initial-admin-secret`, `kube-prom-grafana` | UI admin passwords | operator logins | installed by their charts (`docs/RUNBOOK.md:212-213`) |

## 5. Kubernetes and GitOps Surfaces

| Object | Name, namespace and key fields | Defined in |
|---|---|---|
| `argoproj.io/v1alpha1 Application` | `uptime` in `argocd`. Source repo `https://github.com/AmmaarahMaroof/aws-k8s-platform.git`, revision `main`, path `helm/uptime-monitor`, values `values.yaml` and `values-gitops.yaml`. Destination namespace `uptime`. Automated sync with prune and selfHeal | `gitops/uptime-app.yaml` |
| `monitoring.coreos.com/v1 ServiceMonitor` | `api` | `templates/servicemonitor.yaml` |
| `monitoring.coreos.com/v1 PrometheusRule` | `uptime-monitor` | `templates/prometheusrule.yaml` |
| `batch/v1 CronJob` | `checker` (`*/5 * * * *`) and `db-backup` (`0 2 * * *`), both with `concurrencyPolicy: Forbid`, `backoffLimit: 2`, and a history of 3 successful and 3 failed Jobs | `templates/checker.yaml`, `templates/backup-cronjob.yaml` |
| `apps/v1 Deployment` and `StatefulSet` | `api` and `postgres` | `templates/api.yaml`, `templates/postgres.yaml` |
| `v1 Service` | `api` (80, named `http`) and `db` (5432) | `templates/api.yaml`, `templates/postgres.yaml` |
| `networking.k8s.io/v1 Ingress` | `api`, class `traefik` | `templates/ingress.yaml` |

No ServiceAccount, Role, ClusterRole, RoleBinding or NetworkPolicy is defined anywhere in the repo.

The operator opens these UIs by port-forwarding (`docs/RUNBOOK.md:203-214`):
- Argo CD: `svc/argocd-server` on 443, in namespace `argocd`.
- Grafana: `svc/kube-prom-grafana` on 80, in namespace `monitoring`.
- Prometheus: `svc/kube-prom-kube-prometheus-prometheus` on 9090, in namespace `monitoring`.

The kube-prometheus-stack release is named `kube-prom`.

## 6. Cloud and CI APIs Used

| API | Caller | Purpose |
|---|---|---|
| AWS STS `AssumeRoleWithWebIdentity` | `ci.yml` terraform-plan job; `deploy.yml` | Assumes the OIDC roles `github-actions-terraform-plan` (ReadOnlyAccess plus the state lock) and `github-actions-deploy` |
| ECR: login, push, manifest inspect | `deploy.yml` | Publishes images to `099021515478.dkr.ecr.eu-west-2.amazonaws.com/uptime-monitor` |
| ECR `GetAuthorizationToken` (`aws ecr get-login-password`) | `deploy-on-server.sh`, operator | Refreshes the `ecr-pull` Secret |
| EC2 `DescribeInstances` | `deploy.yml` | Finds `uptime-dev-server` in the running state |
| SSM `SendCommand` and `GetCommandInvocation` | `deploy.yml` | Runs `deploy-on-server.sh` on the tagged instance |
| S3 `PutObject`, `GetObject` and `ListBucket` on `postgres/*` | `db-backup` CronJob, through the EC2 role | Backups and restores |
| GitHub archive `https://github.com/<repo>/archive/<sha>.tar.gz` | EC2, through SSM | Fetches the chart and the script at the deployed commit |

## 7. Read Surfaces Available to an Investigator

This table lists what exists today. The intent requires read-only access; nothing in the repo grants that access yet.

| Evidence | Where it comes from | Exists on |
|---|---|---|
| Pod status and waiting reasons | Kubernetes API (`get pods`, `describe pod`); `kube_pod_container_status_waiting_reason` | Kubernetes API on both; the metric on minikube only |
| Kubernetes Events | Kubernetes API only; not collected into Loki | both |
| Container logs | Kubernetes API (`logs`, `logs --previous`); Loki | Loki on minikube only |
| App and site metrics, alerts | Prometheus HTTP API (`/api/v1/query`, `ALERTS`) | minikube |
| What is deployed | Argo CD Application status and history; `helm history uptime` | Argo CD on minikube; Helm on AWS |
| Which change caused it | Git history and PRs for `helm/uptime-monitor/values-gitops.yaml` and the chart | GitHub |
| Known failure modes | `docs/RUNBOOK.md`, `docs/TROUBLESHOOTING.md`, `docs/incidents/` | repo |
