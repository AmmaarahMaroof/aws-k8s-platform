# Component Inventory: aws-k8s-platform

This is the authoritative component list. The other artifacts refer to these `###` headings, and the Scope of Analysis
`components:` list in `reverse-engineering-timestamp.md` repeats them word for word. Endpoint and object contracts are in
`api-documentation.md`, versions are in `technology-stack.md`, and debt items are in `code-quality-assessment.md`.

## Application

### Uptime API
- **Type**: service (FastAPI on uvicorn, port 8000).
- **Source**: `app/main.py`, `app/schemas.py`, `app/metrics.py`, `app/logging_setup.py`, `app/database.py`, `app/models.py`, `app/config.py`.
- **Runtime** (`helm/uptime-monitor/templates/api.yaml`):
  - Deployment `api`: 2 replicas, init container `wait-for-db`, readiness probe `/ready`, liveness probe `/health`.
    It requests 50m CPU and 128Mi memory, with a 256Mi memory limit.
  - Service `api`: port `http`, 80 to 8000.
- **Responsibilities**: managing sites, reporting status and history, on-demand checks, Prometheus metrics and health probes.
- **Depends on**: PostgreSQL Database (`DATABASE_URL` from Secret `app-config`) and the monitored websites (outbound HTTP).
- **Interfaces**: `api-documentation.md` sections 1-3.

### Checker CronJob
- **Type**: batch job. It uses the same image with the command `python -m app.checker`.
- **Source**: `app/checker.py`, `app/checks.py`.
- **Runtime** (`templates/checker.yaml`): CronJob `checker`, schedule `*/5 * * * *`.
  - `concurrencyPolicy: Forbid`, `backoffLimit: 2`, `restartPolicy: OnFailure`, and a history of 3 successful and 3 failed Jobs.
  - It requests 50m CPU and 64Mi memory, with a 128Mi memory limit.
  - The pods have no `app` label.
- **Responsibilities**: each run does one round of checks, writing one `checks` row and one JSON log line per site. It exits 0 unless it crashes.
- **Depends on**: PostgreSQL Database, Secret `app-config`, and **the same image tag as the Uptime API**.
- **Ops note**: it has no health signal of its own. If it stops running, no metric or alert in the repo notices (incident review, 2026-10-13).

### PostgreSQL Database
- **Type**: datastore.
- **Runtime** (`templates/postgres.yaml`):
  - StatefulSet `postgres`: 1 replica, `postgres:16-bookworm`, a 1Gi RWO PVC `data`, and `PGDATA` in a subdirectory.
    Readiness probe `pg_isready -U uptime`. No resource requests or limits.
  - Service `db` on port 5432.
- **Credentials**: Secret `db-credentials` (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`).
- **Local alternative**: the `db` service in `docker-compose.yml` (password `localdevpassword`, local use only).

### Database Backup CronJob
- **Type**: batch job. It is optional (`backup.enabled`), on in `values-aws.yaml` and off in `values-gitops.yaml`.
- **Runtime** (`templates/backup-cronjob.yaml`): CronJob `db-backup`, schedule `0 2 * * *`.
  1. Init container `pg-dump` (`postgres:16-bookworm`) writes the dump to an emptyDir.
  2. Container `upload` (`amazon/aws-cli:latest`) copies it to `s3://<bucket>/postgres/uptime-<UTC ts>.dump`.
- **Depends on**: PostgreSQL Database, Secret `db-credentials`, and the EC2 instance role. There are no AWS credentials in the cluster.

## Packaging and Delivery

### Helm Chart uptime-monitor
- **Type**: packaging (`helm/uptime-monitor`, chart 0.1.0, appVersion `dev`).
- **Contains**: the four components above, plus an optional Ingress (on in `values-aws.yaml`) and the Prometheus Monitoring Rules.
- **Values layers**:
  - `values.yaml`: defaults.
  - `values-aws.yaml`: AWS k3s.
  - `values-gitops.yaml`: minikube, with the image tag pinned.
- **Image tag locations**: `code-structure.md` § "Where the image tag is set".

### Argo CD Application uptime
- **Type**: GitOps configuration (`gitops/uptime-app.yaml`).
- **Behaviour**: watches `main` at path `helm/uptime-monitor`, applies `values.yaml` and `values-gitops.yaml`, and deploys to namespace `uptime`.
  Sync is automated with `prune: true` and `selfHeal: true`, in project `default`.
- **Scope**: local minikube only. Argo CD itself is installed out-of-band; the repo has no manifests for it.

### Raw Kubernetes Manifests
- **Type**: legacy packaging (`k8s/api.yaml`, `k8s/checker-cronjob.yaml`, `k8s/postgres.yaml`).
- **Notes**: the Phase 5 predecessor of the chart, using image `uptime-monitor:dev` and namespace `uptime`.
  It has no init container, no named Service port and no pull secrets, and no pipeline references it.

### CI Workflow
- **Type**: pipeline (`.github/workflows/ci.yml`). It runs on pushes to `main` and on every pull request.
- **Jobs**:
  - `test`: `pip install -r requirements-dev.txt`, then ruff, then pytest.
  - `build-and-scan` (needs `test`): docker build, then a Trivy 0.56.2 scan that fails on CRITICAL findings, using `--ignore-unfixed`.
  - `terraform`: `fmt -check -recursive`, then `init -backend=false` and `validate` for bootstrap, dev and prod.
  - `terraform-plan` (needs `terraform`): assumes the OIDC plan role and plans dev only.
  - `helm`: `helm lint` and `helm template`, both with **default values only**.
- **Does not check**: whether the image tag in the values files exists in ECR, rendering with `values-gitops.yaml` or `values-aws.yaml`, or workflow validity (there is no actionlint).

### Deploy Workflow
- **Type**: pipeline (`.github/workflows/deploy.yml`).
- **Triggers**: pushes to `main`, except changes to `docs/**`, `infra/**`, `monitoring/**`, `README.md`, `gitops/**` and
  `helm/uptime-monitor/values-gitops.yaml`; and `workflow_dispatch`. Concurrency group `deploy`, with no cancellation.
- **Jobs**:
  - `build-and-push`: skips the build when `repo:sha` already exists, otherwise builds, runs the Trivy gate and pushes.
  - `deploy`: finds the running instance, or warns and skips. Then it runs `AWS-RunShellScript` through SSM and polls for up to 6 minutes.
- **Defect**: a stray `paths-ignore` key under `jobs.deploy` (lines 128-134); see `code-quality-assessment.md` D1.

### Server Deploy Script
- **Type**: script (`scripts/deploy-on-server.sh`). It runs as root on EC2, through SSM.
- **Steps**:
  1. Re-create the `ecr-pull` Secret from `aws ecr get-login-password`.
  2. Run `helm upgrade --install uptime … -n uptime -f values-aws.yaml --set image.tag=$SHA --atomic --timeout 5m`.
  3. Run `kubectl get pods`.

## Observability (minikube only)

### Prometheus Monitoring Rules
- **Type**: chart templates (`templates/servicemonitor.yaml`, `templates/prometheusrule.yaml`), rendered when `monitoring.enabled`
  is true, as it is in `values-gitops.yaml`.
- **Content**: ServiceMonitor `api` (every 15s) and the alerts `MonitoredSiteDown`, `ApiPodRestarting` and `ApiHighErrorRate`
  (`api-documentation.md` section 2).

### kube-prometheus-stack Configuration
- **Type**: third-party chart values (`monitoring/kube-prometheus-stack-values.yaml`). The release is `kube-prom` in namespace
  `monitoring`; the repo does not pin the chart version.
- **Settings**:
  - Picks up ServiceMonitors and rules from any release.
  - 2-day retention; Prometheus requests 100m CPU and 400Mi memory.
  - Scrapes of unreachable control-plane components are disabled.
  - Loki is added as an extra Grafana datasource.
  - **Alertmanager keeps the chart defaults, with no receiver.**

### Loki Log Store
- **Type**: third-party chart values (`monitoring/loki-values.yaml`, grafana/loki 7.3.0).
- **Settings**:
  - SingleBinary mode with 1 replica, filesystem storage and tsdb schema v13.
  - `auth_enabled: false`.
  - The gateway, caches and canary are disabled.
  - Service `loki.monitoring.svc:3100`. No retention is configured.

### Alloy Log Collector
- **Type**: third-party chart values (`monitoring/alloy-values.yaml`, grafana/alloy 1.13.1).
- **Settings**: runs as a single-replica Deployment, because a second replica or a DaemonSet would duplicate every line (TROUBLESHOOTING #30).
  - Pipeline: `discovery.kubernetes` (pods), then relabelling (`namespace`, `pod`, `container`, `app`), then `loki.source.kubernetes`, then `loki.write`.
  - **There is no `loki.source.kubernetes_events`**, so Events are not collected.

### Grafana Dashboard
- **Type**: dashboard JSON (`monitoring/dashboards/uptime-monitor.json`, uid `uptime-monitor`, schemaVersion 39, 6 panels).
- **Provisioning**: none in the repo. The panels are listed in `api-documentation.md` section 2.

## Infrastructure (Terraform, AWS eu-west-2, account 099021515478)

### Terraform Bootstrap
- **Path**: `infra/bootstrap/` (state key `bootstrap/terraform.tfstate`).
- **Resources**:
  - S3 bucket `uptime-monitor-tfstate-099021515478`: versioned, AES256-encrypted, public access blocked, `prevent_destroy`.
  - S3 bucket `uptime-monitor-db-backups-099021515478`: the same settings, plus 7-day expiry.
  - The GitHub OIDC provider.
  - IAM role `github-actions-terraform-plan`: ReadOnlyAccess, plus PutObject and DeleteObject on `*.tflock`. Its trust allows PRs and `main`.
  - IAM role `github-actions-deploy`: its trust allows `main` only. It can:
    - push to the `uptime-monitor` ECR repository only;
    - call `ssm:SendCommand` only on instances tagged `Name=uptime-dev-server`, with the `AWS-RunShellScript` document;
    - call `GetCommandInvocation` and `ec2:DescribeInstances`.

### Network Module
- **Path**: `infra/modules/network/`.
- **Resources**: VPC, internet gateway, one public subnet (`map_public_ip_on_launch`), a route table, and security group
  `<name>-app-sg` (tcp/80 inbound from `http_allowed_cidr` only; all outbound).

### Compute Module
- **Path**: `infra/modules/compute/`.
- **Resources**:
  - EC2 instance: `t3.small` by default, Ubuntu 24.04 from the SSM parameter, IMDSv2 required, 20 GB encrypted gp3 root volume,
    `ignore_changes = [ami]`, tag `Name=<name>-server`.
  - IAM role `<name>-ec2-role` with AmazonSSMManagedInstanceCore and AmazonEC2ContainerRegistryReadOnly. An optional
    `db-backups` policy allows Put and Get on `postgres/*`, and List with that prefix.
  - `user_data.sh` installs k3s (stable channel), Helm (the `get-helm-3` script from `main`) and the AWS CLI (snap).

### Registry Module
- **Path**: `infra/modules/registry/`.
- **Resources**: an ECR repository with `IMMUTABLE` tags, scan on push and AES256 encryption. Its lifecycle policy
  **keeps only the newest 5 images, whatever their tag status**.

### Terraform Environments
- **dev** (`infra/envs/dev/`):
  - Name `uptime-dev`, VPC 10.0.0.0/16.
  - Uses network, **registry `uptime-monitor`**, and compute with backup bucket access.
  - `http_allowed_cidr` comes from a gitignored tfvars file or `TF_VAR_` (the CI secret `HTTP_ALLOWED_CIDR`).
- **prod** (`infra/envs/prod/`):
  - Name `uptime-prod`, VPC 10.1.0.0/16, network and compute only.
  - It declares a required `http_allowed_cidr` variable but passes a hard-coded CIDR instead.
  - It has no registry and no backup access, and no pipeline deploys to it.

## Supporting

### Test Suite
- **Path**: `tests/`. 20 pytest tests with in-memory SQLite and faked HTTP; details in `code-quality-assessment.md`.

### Dev Container
- **Path**: `.devcontainer/devcontainer.json`.
- Image `mcr.microsoft.com/devcontainers/python:3.12-bookworm`, with the docker-in-docker, terraform, aws-cli and
  kubectl-helm-minikube features.
- The local minikube cluster (4 CPUs, 8 GB) runs inside it, together with `docker-compose.yml` for local Postgres.

### Operational Documentation
- **Paths**:
  - `README.md`.
  - `docs/APP.md`.
  - `docs/RUNBOOK.md`: quick reference, access, deploy, rollback, the alert response table, backup and restore, DR, local GitOps, Loki queries, the game-day procedure, and the AI agent safety rules.
  - `docs/SECURITY.md`: CVE triage, controls and the IAM review.
  - `docs/TROUBLESHOOTING.md`: 33 entries, each giving symptom, diagnosis, cause, fix and lesson.
  - `docs/incidents/2026-10-13-bad-image-tag.md`: an incident review with 5 open actions.
- **Role for ops tooling**: the only written record of known failure modes, the triage order and past incidents.
