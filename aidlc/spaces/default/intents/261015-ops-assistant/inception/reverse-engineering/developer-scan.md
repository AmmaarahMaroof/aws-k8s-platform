# Developer Code Scan: aws-k8s-platform

Scan date: 2026-10-16 · Commit: `6b33c163311a34a8be9874be8986134d9293d15b` (branch `step4-ai-ops`) · Intent: `ops-assistant`

This handoff replaces the one written by the interrupted attempt on 2026-10-15. Every finding was re-checked against the current files. The project source has not changed since that commit; only AI-DLC files have.

## Developer Code Scan Results

### Scan Coverage
- **Analyzed deeply** (all 68 tracked project files outside the AI-DLC install were opened and read):
  - `./` (root files: `README.md`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `pytest.ini`, `ruff.toml`, `requirements-dev.txt`, and the project part of `.gitignore`)
  - `app/` (all 11 files)
  - `tests/` (all 4 files)
  - `helm/uptime-monitor/` (`Chart.yaml`, 3 values files, 7 templates)
  - `gitops/` (`uptime-app.yaml`)
  - `k8s/` (3 raw manifests)
  - `monitoring/` (3 values files, plus `dashboards/uptime-monitor.json`, which was parsed for its panels and queries)
  - `.github/workflows/` (`ci.yml`, `deploy.yml`)
  - `infra/` (`bootstrap/`, `envs/dev/`, `envs/prod/`, `modules/compute|network|registry/`; from the `.terraform.lock.hcl` files only the provider pins were read)
  - `scripts/` (`deploy-on-server.sh`)
  - `.devcontainer/` (`devcontainer.json`)
  - `docs/` (`APP.md`, `RUNBOOK.md`, `SECURITY.md`, `TROUBLESHOOTING.md`, `incidents/2026-10-13-bad-image-tag.md`)
- **Skimmed only**:
  - `docs/aidlc/` (only the intent statement was read, for context; it is not application code)
  - `uptime.db` (a tracked binary SQLite file; only its schema was listed, through a read-only connection)
- **Left out**:
  - `.pytest_cache/`, `.ruff_cache/`, `app/__pycache__/`, `tests/__pycache__/` (tool caches)
  - `infra/bootstrap/.terraform/`, `infra/envs/dev/.terraform/`, `infra/envs/prod/.terraform/` (provider downloads)
  - `infra/envs/dev/terraform.tfvars` (gitignored; may hold a real CIDR value)
  - `.claude/`, `aidlc/` (the AI-DLC install and workspace)
  - `gameday.log` (untracked game-day output, not project code)

Read-only local checks run during this attempt:
- `pytest`: 20 passed in 0.31s, with 1 Starlette deprecation warning.
- `ruff check app tests` (ruff 0.17.0): "All checks passed!".
- `helm lint helm/uptime-monitor` (local Helm v4.3.0): 0 charts failed; one INFO note that an icon is recommended.
- `helm template` with `values-gitops.yaml` renders Service ×2, Deployment, StatefulSet, CronJob, PrometheusRule and ServiceMonitor. With `values-aws.yaml` it renders Service ×2, Deployment, StatefulSet, CronJob ×2 (checker, db-backup) and Ingress.

No live cluster, AWS account or GitHub API was queried. `actionlint` is not installed.

### Packages Found
- `app`: Python package, Python 3.12. **Uptime Monitor**, a FastAPI HTTP API with SQLAlchemy models, plus a standalone checker entry point (`python -m app.checker`) that the CronJob runs.
- `tests`: Python test package. A pytest suite that uses in-memory SQLite and a monkeypatched HTTP check.
- `helm/uptime-monitor`: Helm chart v0.1.0 (appVersion `dev`). It holds the API Deployment and Service, the checker CronJob, the Postgres StatefulSet and Service, and four optional parts: Ingress, ServiceMonitor, PrometheusRule and a db-backup CronJob.
- `gitops`: an Argo CD `Application` named `uptime`. It pulls the chart from `main` with `values.yaml` and `values-gitops.yaml`, and auto-syncs into namespace `uptime` with prune and selfHeal.
- `k8s`: raw manifests from Phase 5, the predecessor of the chart. They hard-code namespace `uptime` and image `uptime-monitor:dev`.
- `monitoring`: values for third-party Helm charts. kube-prometheus-stack (version not pinned), Loki 7.3.0 (SingleBinary) and Alloy 1.13.1, plus one Grafana dashboard JSON that no manifest provisions.
- `infra`: Terraform with the AWS provider locked at 6.66.0.
  - `bootstrap`: S3 state bucket, S3 backups bucket, GitHub OIDC provider, and the plan and deploy IAM roles.
  - `envs/dev` and `envs/prod`: network and compute modules; dev also uses the registry module.
  - Modules: `network`, `compute` (EC2 running k3s) and `registry` (ECR).
- `scripts/deploy-on-server.sh`: Bash that runs on EC2 through SSM. It refreshes the `ecr-pull` secret and runs `helm upgrade --install --atomic --set image.tag=<sha>`.
- `.github/workflows`: GitHub Actions.
  - `ci.yml` has five jobs: test, build-and-scan, terraform, terraform-plan and helm.
  - `deploy.yml` has two jobs: build-and-push, then deploy through SSM.

### Build System
- **Type**: pip with requirements files (no `pyproject.toml`), a multi-stage Docker build, Helm charts, Terraform 1.10 or later, and GitHub Actions.
- **Config Files**: `app/requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `ruff.toml`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `helm/uptime-monitor/Chart.yaml`, `infra/**/main.tf`, `infra/**/.terraform.lock.hcl`, `.devcontainer/devcontainer.json`.
- **Build Dependencies**:
  - `requirements-dev.txt` includes `app/requirements.txt` through `-r`.
  - The `Dockerfile` builder stage installs `app/requirements.txt` into `/install`. The runtime stage copies `/install` and `app/` onto the base image `public.ecr.aws/docker/library/python:3.12-slim-bookworm`.
  - `helm/uptime-monitor` deploys one image, `image.repository:image.tag`, which both the API Deployment and the checker CronJob use.
  - `gitops/uptime-app.yaml` reads `helm/uptime-monitor` with `values-gitops.yaml`.
  - `scripts/deploy-on-server.sh` reads `helm/uptime-monitor` with `values-aws.yaml` and `--set image.tag=$SHA`.
  - `infra/envs/{dev,prod}` use `infra/modules/{network,compute}`; dev also uses `modules/registry`.

### APIs Discovered
- REST (FastAPI), `app/main.py`: 10 endpoints, and none of them authenticate.
  - Platform: `/health`, `/ready`, `/metrics`.
  - Sites: POST and GET `/sites`, GET and DELETE `/sites/{id}`.
  - Checks: `/sites/{id}/checks`, `/status`, `/checks/run`.
- Prometheus exposition at `GET /metrics` (`app/metrics.py`): 4 metric families, `http_requests_total`, `http_request_duration_seconds`, `site_up` and `site_response_ms`.
- JSON log lines on stdout (`app/logging_setup.py`) with a fixed set of extra fields.
- Kubernetes CRDs the repo uses: `argoproj.io/v1alpha1 Application`, and `monitoring.coreos.com/v1` `ServiceMonitor` and `PrometheusRule`.
- Loki: Alloy pushes to `http://loki.monitoring.svc:3100/loki/api/v1/push`, and Grafana's Loki datasource is `http://loki.monitoring.svc:3100`.
- AWS APIs used by CI/CD: STS (OIDC), ECR, EC2 DescribeInstances, and SSM SendCommand and GetCommandInvocation.

### Frameworks & Libraries
- Python 3.12: Dockerfile base `public.ecr.aws/docker/library/python:3.12-slim-bookworm`; CI uses `setup-python` with 3.12.
- fastapi `>=0.115,<1` (0.141.1 installed locally): the HTTP API.
- uvicorn[standard] `>=0.30,<1` (0.54.0): the ASGI server.
- sqlalchemy `>=2.0,<3` (2.1.1): the ORM.
- psycopg[binary] `>=3.2,<4` (3.3.6): the Postgres driver.
- httpx `>=0.27,<1` (0.28.1): outbound site checks, and the transport for the test client.
- prometheus-client `>=0.20,<1` (0.26.0): metrics.
- pydantic 2.13.5 (transitive, through fastapi): request and response schemas.
- pytest `>=8,<9` (8.4.2) and ruff `>=0.6,<1` (0.17.0 locally): development only.
- Postgres `postgres:16-bookworm`. The Traefik ingress class comes from k3s.
- Terraform `>= 1.10` (1.16.4 installed locally), with `hashicorp/aws ~> 6.0` locked at 6.66.0.
- Helm: v4.3.0 in the devcontainer. CI uses `azure/setup-helm@v4` without pinning a Helm version. The EC2 server installs Helm 3 through `get-helm-3` from the helm `main` branch.
- Grafana Loki chart 7.3.0 and Grafana Alloy chart 1.13.1. The kube-prometheus-stack chart version is not pinned in the repo.
- Argo CD: the version is not recorded in the repo.
- Trivy `public.ecr.aws/aquasecurity/trivy:0.56.2`. The backup image `amazon/aws-cli:latest` is not pinned.

### Test Coverage
- **Test Directories**: `tests/`, containing `conftest.py`, `test_api.py` (16 tests) and `test_checks.py` (4 tests), for 20 tests in total.
- **Test Frameworks**: pytest with FastAPI `TestClient`. `monkeypatch` replaces `app.checks.check_url` and `httpx.get`.
- **Coverage Config**: absent. There is no pytest-cov, no threshold and no coverage step in CI.
- Helm templates, PrometheusRule expressions, Terraform and shell scripts have no tests. They are only checked by `helm lint`/`template` and `terraform fmt`/`validate`/`plan`.

### Code Quality Indicators
- **Linting**:
  - ruff runs with its default rule set plus a bugbear `extend-immutable-calls` exception (`ruff.toml`); CI runs `ruff check app tests`.
  - ruff is only range-pinned (`>=0.6,<1` in `requirements-dev.txt`), although TROUBLESHOOTING #23 says it was pinned in `ci.yml`.
  - CI also runs `helm lint`, `helm template` and `terraform fmt -check -recursive`.
  - No formatter is enforced.
- **CI/CD**:
  - `.github/workflows/ci.yml` runs on pull requests and on pushes to main.
  - `.github/workflows/deploy.yml` runs on pushes to main outside its ignored paths, and on `workflow_dispatch`.
  - Argo CD auto-sync drives the minikube environment (`gitops/uptime-app.yaml`).
- **Documentation**: strong for an operations project.
  - The README has a Mermaid architecture diagram and cost tables.
  - `docs/APP.md` describes the app.
  - `docs/RUNBOOK.md` covers deploy, rollback, alerts, backup and restore, DR, local GitOps and agent safety.
  - `docs/SECURITY.md` covers CVE triage and the IAM review.
  - `docs/TROUBLESHOOTING.md` has 33 entries, and there is one incident review.
  - Python modules have module docstrings and explanatory comments.

### Technical Debt Signals
- `.github/workflows/deploy.yml:128-134`: a leftover `paths-ignore:` block sits under `jobs.deploy`. It was left behind when #33 (`fb74525`) added the correct block under `on.push`. `paths-ignore` is not a valid job key, so GitHub probably rejects the workflow (the TROUBLESHOOTING #31 signature). Not confirmed, because actionlint is not installed.
- `docs/TROUBLESHOOTING.md`:
  - Lines 187, 246 and 248 hold unresolved merge-conflict markers (`<<<<<<< Updated upstream`, `=======`, `>>>>>>> Stashed changes`).
  - Entry #12 is duplicated at lines 320-328.
- `docs/RUNBOOK.md:205` references `scripts/ui.sh`, which does not exist.
- `app/database.py:53-58`: `init_db()` runs `create_all` on every replica at startup, and there are no migrations. TROUBLESHOOTING #12 documents the resulting race.
- Unpinned versions:
  - `helm/uptime-monitor/values.yaml:52` uses `awsCliImage: amazon/aws-cli:latest`.
  - kube-prometheus-stack, the Helm version in CI and the k3s/Helm install scripts in `infra/modules/compute/user_data.sh` are all unpinned.
- `infra/modules/registry/main.tf:29-43`: the ECR lifecycle keeps only 5 images (`tagStatus: any`). The SHA pinned in `values-gitops.yaml` can expire after five newer pushes and cause ImagePullBackOff with no Git change.
- `infra/envs/prod/main.tf`:
  - It declares a required `http_allowed_cidr` variable (lines 38-41) but never uses it, and hard-codes `<home-ip>/32` (the operator's home IP, redacted) at line 51.
  - Prod has no registry module and no backup bucket access.
  - CI plans only dev.
- AWS account ID `099021515478` is hard-coded in the Helm values, the deploy script, the workflows, Terraform and the runbook.
- `helm/uptime-monitor/templates/prometheusrule.yaml:20-26`: the `ApiPodRestarting` alert covers every container in the namespace, not only the API.
- No alert detects stale checks. `site_up` is rebuilt from the latest stored check whatever its age (`app/main.py:73-86`), so `MonitoredSiteDown` cannot fire when the checker stops.
- No Alertmanager receiver is configured anywhere in the repo (the incident review says the same at line 38).
- Kubernetes security gaps:
  - No ServiceAccount, Role, RoleBinding or NetworkPolicy exists in any manifest; every pod uses the namespace `default` ServiceAccount.
  - Pods have no `securityContext`.
  - The Postgres StatefulSet has no resource requests or limits.
- The raw `k8s/*.yaml` files and the Helm chart define the same deployment twice and can drift. The raw ones have no Service port name, init container or pull secrets.
- `monitoring/dashboards/uptime-monitor.json`:
  - No manifest provisions it.
  - Its panels set no datasource.
  - The "Monitored sites" stat panel has no `instant` flag, although TROUBLESHOOTING #16 says the fix was switching it to Instant.
- `uptime.db`, a SQLite runtime artifact, is committed even though `.dockerignore` excludes `*.db`.
- The API has no authentication. `POST /checks/run` makes outbound requests to every stored URL, an SSRF-style surface that the single-CIDR ingress only partly limits.
- `app/checks.py:50-53` logs the full site `url`, and `error` holds raw exception text. A URL with embedded credentials would reach the logs.
- pytest prints the Starlette TestClient deprecation warning ("install `httpx2`").
- There is no coverage measurement, although the org default for `classic` scope sets an 80% line-coverage floor.

## Handoff Summary
- **Intent-relevant finding**: the deployed image tag lives in exactly two places.
  - GitOps (minikube): `helm/uptime-monitor/values-gitops.yaml:3` (`tag: "d01d633f…"`), which Argo CD auto-syncs from `main` with selfHeal and prune (`gitops/uptime-app.yaml:10-22`).
  - AWS k3s: `--set image.tag=$SHA` in `scripts/deploy-on-server.sh:22`; `values-aws.yaml:4` holds an empty tag.

  The API Deployment and the checker CronJob share that one tag (`templates/api.yaml:41`, `templates/checker.yaml:23`). That is why a bad tag silently stopped monitoring in the reference incident (`docs/incidents/2026-10-13-bad-image-tag.md:9,26`; commit `5f30243`, PR #34, changed only that line, and revert `b931682` is PR #35). The investigation signals that exist are:
  - App metrics: `site_up`, `site_response_ms`, `http_requests_total` and `http_request_duration_seconds`. There is no freshness metric.
  - kube-state-metrics from kube-prometheus-stack: `kube_pod_container_status_waiting_reason` and `kube_pod_container_status_restarts_total`.
  - Three custom alerts plus the built-in `KubePodNotReady` and `Watchdog`.
  - JSON pod logs in Loki, labelled `namespace`, `pod`, `container` and `app`.
  - Kubernetes Events, which are **not** collected into Loki.
  - Argo CD sync history.
  - Git history and PRs.
- **Risks / follow-up**:
  1. No RBAC objects exist yet. A read-only identity for the assistant must be created from scratch; there is nothing to reuse.
  2. Secrets are created out-of-band: `db-credentials`, `app-config` (whose `DATABASE_URL` embeds the password), `ecr-pull`, and the Argo CD and Grafana admin secrets. Pods receive them through `envFrom`, so `kubectl get -o yaml` on Secrets, or on pods' env, can expose credentials. A `DATABASE_URL` password can also appear in SQLAlchemy errors the app logs (`/ready` calls `log.exception`), and site URLs are logged verbatim.
  3. All the newer observability (Argo CD, Prometheus, Loki) exists only on local minikube. The AWS k3s server has none of it, and its deploys are pushed by CI, not pulled by GitOps.
  4. `deploy.yml` is probably invalid (see above).
  5. The 5-image ECR lifecycle can silently invalidate a pinned GitOps tag.
  6. The agent safety posture is in `docs/RUNBOOK.md:249-257` and TROUBLESHOOTING #33. Auto-edits are limited to `aidlc/**` and `docs/aidlc/**`, and the agent must never be approved to run kubectl, helm, aws, terraform or git push.
