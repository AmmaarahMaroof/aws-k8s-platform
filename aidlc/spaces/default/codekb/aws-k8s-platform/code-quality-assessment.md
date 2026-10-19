# Code Quality Assessment: aws-k8s-platform

## Baseline (measured locally and read-only on 2026-10-16, at `6b33c16`)

| Check | Result |
|---|---|
| `pytest` | **20 passed** in 0.31s, with 1 warning (Starlette TestClient deprecation: "install `httpx2`") |
| `ruff check app tests` (ruff 0.17.0) | All checks passed |
| `helm lint helm/uptime-monitor` (Helm v4.3.0) | 0 charts failed (INFO: an icon is recommended) |
| `helm template` with `values-gitops.yaml` | Renders Service ×2, Deployment, StatefulSet, CronJob, PrometheusRule and ServiceMonitor |
| `helm template` with `values-aws.yaml` | Renders Service ×2, Deployment, StatefulSet, CronJob ×2 and Ingress |
| Coverage | **Not measured.** There is no pytest-cov, no threshold and no CI step |
| Terraform | Not run in this scan. CI runs `fmt -check`, `validate` (×3) and `plan` (dev) |
| Workflow validation | Not run; `actionlint` is not installed |

This is the brownfield test baseline that later stages compare against.

## Test Coverage

- **Tests**: `tests/test_api.py` (16 in-process API tests) and `tests/test_checks.py` (4 unit and job tests). The fixtures are in `tests/conftest.py`.
- **Approach**: in-memory SQLite (`StaticPool`), a fresh schema for every test, and a monkeypatched `check_url` or `httpx.get`, so no network is used.
- **Covered well**:
  - The happy path of every REST endpoint.
  - Validation (422), conflicts (409) and 404s.
  - Ordering and limits.
  - The metric gauges, including the removal of deleted sites.
  - How checks are classified as up, down or error.
  - `checker.main()`.
- **Not covered**:
  - The `/ready` 503 path and the Postgres-specific behaviour (`_normalise_url`, `pool_pre_ping`).
  - The logging formatter, and the middleware's `unmatched` label.
  - Helm rendering with non-default values.
  - The PromQL rules (there is no `promtool test rules`).
  - The shell scripts and the Terraform modules, beyond `validate`.
- **Org posture**: the `classic` scope requires an 80% line-coverage floor, run in CI (`org.md` § Testing Posture). Coverage is not measured today, so whether the floor is met is unknown.

## Code Quality Ratings (3-point scale from the code analysis guide)

| Dimension | Rating | Evidence |
|---|---|---|
| Naming clarity | good | `run_all_checks`, `latest_check`, `_get_site_or_404`; every module has a descriptive docstring |
| Function size | good | Every function is under 30 lines; the largest, `overall_status`, is about 17 |
| Error handling | fair | Transport errors map to "down" and `/ready` returns 503. `POST /checks/run` and other database calls have no handling, so failures become unhandled 500s. `create_all` races on the first start with several replicas (TROUBLESHOOTING #12) |
| Test presence | good | Every application module has tests. The infrastructure and configuration layers have none |
| Duplication | fair | `k8s/*.yaml` duplicates the chart. The "latest check per site" lookup is repeated in `/metrics` and `/status` (N+1 queries). The alert and dashboard PromQL are duplicated |
| Dead code | fair | ruff finds no unused imports. No pipeline uses the legacy `k8s/` manifests, and `uptime.db` is committed |

## Linting and Static Analysis

- **Python**: ruff with the default rules plus a documented bugbear exception.
  - The two `# noqa: F401` comments are both justified: they are imports that register the models (`app/database.py:56`, `tests/conftest.py:14`).
  - There are no TODO, FIXME or HACK markers.
  - No formatter is enforced and there is no type checker.
  - ruff is range-pinned only (`>=0.6,<1`), although TROUBLESHOOTING #23 says it was pinned in `ci.yml`.
- **Helm**: `helm lint` and `helm template` in CI, with **default values only**.
- **Terraform**: `fmt -check -recursive`, `validate`, and `plan` for dev only.
- **Workflows**: no `actionlint`, although TROUBLESHOOTING #31 recommends it.
- **Security**:
  - A Trivy scan that fails on CRITICAL findings, with `--ignore-unfixed`, in both CI and Deploy.
  - ECR scan on push.
  - A triage log in `docs/SECURITY.md`.
  - The image runs as a non-root user (`Dockerfile:18,27`).

## CI/CD Quality

- `main` is protected and changes only through PRs (`docs/SECURITY.md:60`). CI runs on every PR.
- The CI identities are least-privilege OIDC roles with no static keys (`component-inventory.md` § Terraform Bootstrap).
- The deploy is idempotent and safe to repeat:
  - It reuses an existing SHA image (TROUBLESHOOTING #22).
  - It uses `--atomic`, so a failed rollout rolls back.
  - The concurrency group serialises deploys.
- The GitOps path has no deploy-time validation beyond what CI checks for the PR. The Deploy workflow deliberately ignores `values-gitops.yaml`.
- **Defect in `.github/workflows/deploy.yml:128-134`** (D1):
  - A leftover `paths-ignore:` list sits under `jobs.deploy`, after its steps; the parsed job keys are `needs, runs-on, steps, paths-ignore`.
  - `paths-ignore` is a trigger filter, not a valid job key, so GitHub probably rejects the whole workflow. This is the same signature as TROUBLESHOOTING #31.
  - Not confirmed here, because actionlint is not available.
  - The correct `on.push.paths-ignore` block is at lines 6-12. Commit `fb74525`, "Fix deploy indent (#33)", added that block but did not remove the stray one.

## Documentation Quality

Strong overall:
- A README with an architecture diagram and a cost analysis.
- An app guide.
- A runbook in which every procedure has been run for real.
- A security triage log with an IAM review.
- 33 troubleshooting entries, each giving symptom, diagnosis, cause, fix and lesson.
- One incident review with a timeline and actions.

Defects:
- `docs/TROUBLESHOOTING.md:187` and `246-248`: **unresolved git conflict markers** (`<<<<<<< Updated upstream`, `=======`, `>>>>>>> Stashed changes`).
- `docs/TROUBLESHOOTING.md:320-328`: entry #12 is duplicated under a second `## Kubernetes` heading. Entries from #23 onward use `##` instead of `###`.
- `docs/RUNBOOK.md:205` refers to `scripts/ui.sh`, which is not in the repo.
- `docs/APP.md:16` still calls the checker a "future Kubernetes CronJob".
- `README.md:45` labels the Kubernetes subgraph "minikube, local", although the same diagram also shows the AWS k3s deploy.
- TROUBLESHOOTING #22's fix text says the workflow checks with `aws ecr batch-get-image`. The follow-up at line 172 and `deploy.yml:48` show that `docker manifest inspect` is what is used.
- TROUBLESHOOTING #16 says the "Monitored sites" stat panel was switched to an Instant query, but the exported dashboard JSON sets no `instant` flag.

## Technical Debt Register

This register is the single list of debt items; other artifacts refer to them by ID.

| # | Debt | Location | Ops relevance |
|---|---|---|---|
| D1 | The Deploy workflow is probably invalid (a stray `paths-ignore`) | `.github/workflows/deploy.yml:128-134` | AWS deploys may not run at all |
| D2 | No alert for stale checks or for pods stuck waiting; no Alertmanager receiver; Events are not collected; `site_up` carries no age | `templates/prometheusrule.yaml`, `app/main.py:73-86`, `monitoring/*` | The reference incident went undetected (5 open actions) |
| D3 | CI never checks that the image tag exists, and lints Helm only with default values | `.github/workflows/ci.yml:105-113` | A bad tag can reach `main` |
| D4 | ECR keeps only 5 images while GitOps pins a SHA | `infra/modules/registry/main.tf:29-43`, `values-gitops.yaml:3` | The pinned image can disappear |
| D5 | No RBAC, ServiceAccounts, NetworkPolicies or pod `securityContext`; Postgres has no resource limits | `helm/uptime-monitor/templates/*` | There are no least-privilege identities to build on |
| D6 | Secrets are created by hand; `DATABASE_URL` embeds the password; the API logs DB exceptions and raw site URLs | `docs/RUNBOOK.md` section 7, `app/main.py:67-69`, `app/checks.py:50-53` | Any log or describe output must be redacted |
| D7 | The schema is created by `create_all` at startup, with no migrations | `app/database.py:53-58` | A restart on the first start (TROUBLESHOOTING #12) |
| D8 | Unpinned images and tools (`aws-cli:latest`, the k3s channel, the Helm installer, kube-prometheus-stack, Helm in CI, ruff) | `dependencies.md` § Dependency Risks Observed | Environments are not reproducible |
| D9 | No observability on the AWS cluster | `README.md:93` | Investigation with metrics and logs is only possible on minikube |
| D10 | `ApiPodRestarting` covers every pod in the namespace despite its name | `templates/prometheusrule.yaml:21` | The alert name is misleading |
| D11 | The API has no authentication; `POST /checks/run` triggers outbound requests to every stored URL | `app/main.py` | Relies on the single-CIDR ingress |
| D12 | `uptime.db` is committed; the legacy `k8s/` manifests remain; the docs have conflict markers; the dashboard is not provisioned | repo root, `k8s/`, `docs/TROUBLESHOOTING.md`, `monitoring/dashboards/` | Hygiene and drift |
| D13 | `/metrics` and `/status` make N+1 queries; the `checks` table grows with no retention | `app/main.py:79-85,151-163` | Scrape latency grows with history and site count |
| D14 | prod hard-codes `<home-ip>/32` (the operator's home IP, redacted) and ignores its required `http_allowed_cidr` variable; prod has no registry or backups; CI plans only dev | `infra/envs/prod/main.tf:38-51` | prod cannot be deployed as it stands |
