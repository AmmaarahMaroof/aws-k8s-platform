# Business Overview: aws-k8s-platform

## Purpose

`aws-k8s-platform` is an end-to-end DevOps platform project built around a deliberately small application, the
**Uptime Monitor** (`README.md:3`, `docs/APP.md:3-4`). The app "exists to be deployed, monitored and operated", so the
platform is the real deliverable: CI/CD, infrastructure as code, Kubernetes packaging, GitOps, observability, backups
and disaster recovery, security triage, and incident practice. The application is the workload that exercises all of it.

## Business Domain

- **Domain**: website availability monitoring, used as the workload for platform and SRE practice.
- **Owner and operator**: one engineer (GitHub `AmmaarahMaroof`). Every runbook procedure is done by hand and has been
  run at least once (`docs/RUNBOOK.md:4`).
- **Cost posture**: frugal by design.
  - k3s runs on a single EC2 `t3.small` instead of EKS.
  - A public subnet replaces a NAT gateway, and Traefik replaces an ALB.
  - It would cost about $22 a month if left on 24/7, so the server is stopped between sessions (`README.md:74-95`).
- **Users of the app**: the operator, who calls the HTTP API directly. There is no UI beyond FastAPI's `/docs` and the Grafana dashboard.

## Key Functionality

### Uptime Monitor (the application)

| Capability | How it works | Evidence |
|---|---|---|
| Register websites to watch | `POST /sites` with a name and URL; a duplicate URL gets 409 | `app/main.py:98-108` |
| Check sites | HTTP GET on each URL. A status below 400 means up; a timeout or transport error means down | `app/checks.py:19-55` |
| Scheduled checking | A Kubernetes CronJob runs `python -m app.checker` every 5 minutes | `helm/uptime-monitor/templates/checker.yaml`, `values.yaml:22-23` |
| On-demand checking | `POST /checks/run` | `app/main.py:167-171` |
| Status and history | `GET /status` (latest result per site) and `GET /sites/{id}/checks` | `app/main.py:130-164` |
| Metrics for alerting | `site_up` and `site_response_ms` gauges, rebuilt from the database on every scrape | `app/main.py:73-86`, `app/metrics.py` |

Endpoint contracts are in `api-documentation.md`.

### Platform capabilities (the real product)

| Capability | Where |
|---|---|
| Lint, tests, image build with Trivy scan, Terraform validate and plan, and Helm lint on every PR | `.github/workflows/ci.yml` |
| Push-based deploy to AWS k3s on merge to `main` (SHA-tagged image, Helm through SSM) | `.github/workflows/deploy.yml`, `scripts/deploy-on-server.sh` |
| Pull-based GitOps deploy on local minikube (Argo CD auto-sync with self-heal) | `gitops/uptime-app.yaml`, `helm/uptime-monitor/values-gitops.yaml` |
| Metrics, alerts and dashboards (Prometheus Operator, Grafana) | `monitoring/kube-prometheus-stack-values.yaml`, `templates/prometheusrule.yaml`, `templates/servicemonitor.yaml`, `monitoring/dashboards/uptime-monitor.json` |
| Central logs (Alloy to Loki) | `monitoring/alloy-values.yaml`, `monitoring/loki-values.yaml` |
| Backups and DR: nightly `pg_dump` to S3, and a full rebuild tested at about 17 minutes | `templates/backup-cronjob.yaml`, `infra/bootstrap/backups.tf`, `docs/RUNBOOK.md` sections 6-7 |
| Least-privilege CI identities (GitHub OIDC, no stored keys) | `infra/bootstrap/github_oidc.tf`, `docs/SECURITY.md:75-81` |
| Incident practice (game days and written incident reviews) | `docs/incidents/2026-10-13-bad-image-tag.md`, `docs/RUNBOOK.md:242-247` |

## Environments

| Environment | Runtime | How it is deployed | Observability |
|---|---|---|---|
| Local dev | `uvicorn` with SQLite, or `docker compose` with Postgres | by hand | none |
| Local minikube (codespace) | minikube, namespace `uptime` | **Argo CD** pulls `main` | Prometheus, Grafana, Alertmanager (default receiver), Loki and Alloy |
| AWS `dev` | k3s on one EC2 instance in eu-west-2 | GitHub Actions, then SSM, then `helm upgrade --atomic` | **None in the cluster.** The README says monitoring "isn't watching the live server 24/7" (`README.md:93`) |
| AWS `prod` | Terraform defines only network and compute (`infra/envs/prod/main.tf`) | no pipeline targets it | none |

## Key Business Transactions

These are the transactions that `architecture.md` § Interaction Diagrams traces across components:

1. **Uptime check round**: the checker probes every site, stores the results, and Prometheus reads them through `/metrics`.
2. **Release to AWS**: a merge to `main` builds, scans and pushes an image, then deploys it through SSM and Helm.
3. **Release via GitOps**: a merged change to `values-gitops.yaml` or the chart is synced by Argo CD into minikube.
4. **Alert**: Prometheus evaluates rules and passes firing alerts to Alertmanager, which notifies nobody.
5. **Manual incident investigation**: the operator moves between kubectl, Prometheus, Loki, Argo CD and Git.

## Context for the Active Intent (ops assistant)

The reference incident (`docs/incidents/2026-10-13-bad-image-tag.md`) was a planned game day on minikube with Argo CD:

- PR #34 (commit `5f30243`) changed only `values-gitops.yaml`, setting `image.tag` to `gameday-does-not-exist`.
- The rolling update protected the API. The checker CronJob shares the image, so its pods went into `ImagePullBackOff`
  and uptime checks stopped silently.
- None of the three custom alerts fired.
- The fix was a revert, PR #35 (commit `b931682`), 19 minutes after the break. Detection relied on the operator
  watching screens.
- Five follow-up actions are still **open** (incident review lines 40-47).

The intent (`docs/aidlc/inception/intent.md`) builds on this situation. This knowledge base records only the system as it
exists today. The read surfaces an investigator would use are listed in `api-documentation.md`, and the gaps that limit
them are in `code-quality-assessment.md`.

## Glossary

| Term | Meaning |
|---|---|
| Site | A monitored website (`sites` table) |
| Check | One availability probe result for a site (`checks` table) |
| Checker | The CronJob, or the module `app.checker`, that runs one round of checks and exits |
| GitOps values | `helm/uptime-monitor/values-gitops.yaml`, the file Argo CD applies on minikube |
| AWS values | `helm/uptime-monitor/values-aws.yaml`, applied by `deploy-on-server.sh` with the tag passed via `--set` |
| Game day | A planned fault injection, made through Git, followed by a written incident review |
| `ecr-pull` | The docker-registry Secret holding a 12-hour ECR token, used for every image pull |
