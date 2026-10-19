# Technology Stack: aws-k8s-platform

Versions come from the manifests and lock files. The "Installed" column is what the codespace had on 2026-10-16
(`pip list`, `helm version`, `terraform version`). The image resolves its own versions inside the declared ranges when
it is built. Who depends on each item is in `dependencies.md`.

## Languages

| Language | Version | Where |
|---|---|---|
| Python | 3.12 | `Dockerfile` (`public.ecr.aws/docker/library/python:3.12-slim-bookworm`), `ci.yml` (`setup-python` 3.12), devcontainer |
| HCL (Terraform) | `>= 1.10` (CI `^1.10`; 1.16.4 installed) | `infra/**` |
| YAML (Helm, Kubernetes, Actions) | n/a | `helm/`, `k8s/`, `gitops/`, `monitoring/`, `.github/` |
| Go templates (Helm) | n/a | `helm/uptime-monitor/templates/` |
| Bash | n/a | `scripts/deploy-on-server.sh`, `infra/modules/compute/user_data.sh` |
| PromQL and LogQL | n/a | `templates/prometheusrule.yaml`, the dashboard JSON, `docs/RUNBOOK.md` |

## Application Runtime Libraries (`app/requirements.txt`)

| Library | Declared | Installed | Purpose |
|---|---|---|---|
| fastapi | `>=0.115,<1` | 0.141.1 | Web framework |
| uvicorn[standard] | `>=0.30,<1` | 0.54.0 | ASGI server |
| sqlalchemy | `>=2.0,<3` | 2.1.1 | ORM (2.0-style `Mapped`) |
| psycopg[binary] | `>=3.2,<4` | 3.3.6 | PostgreSQL driver |
| httpx | `>=0.27,<1` | 0.28.1 | Outbound site checks; TestClient transport |
| prometheus-client | `>=0.20,<1` | 0.26.0 | Metrics |
| pydantic (transitive) | n/a | 2.13.5 | Schemas (`HttpUrl`, `ConfigDict`) |
| starlette (transitive) | n/a | 1.7.0 | Underneath FastAPI |

## Development Tooling (`requirements-dev.txt`)

| Tool | Declared | Installed | Notes |
|---|---|---|---|
| pytest | `>=8,<9` | 8.4.2 | `pytest.ini`: `testpaths=tests`, `pythonpath=.`, `-q` |
| ruff | `>=0.6,<1` | 0.17.0 | `ruff.toml` holds a bugbear immutable-calls exception. CI installs this range, not an exact pin |

## Containers and Images

| Image | Tag | Used by |
|---|---|---|
| `public.ecr.aws/docker/library/python` | `3.12-slim-bookworm` | Dockerfile, both stages |
| `uptime-monitor` (built here) | the git SHA in ECR (immutable); `dev` locally | API and checker |
| `postgres` | `16-bookworm` | StatefulSet, the `wait-for-db` init container, the backup `pg-dump` step, docker-compose |
| `amazon/aws-cli` | `latest` (unpinned) | backup upload |
| `public.ecr.aws/aquasecurity/trivy` | `0.56.2` | CI and Deploy scans |
| `mcr.microsoft.com/devcontainers/python` | `3.12-bookworm` | devcontainer |

## Kubernetes and Platform

| Technology | Version | Where |
|---|---|---|
| k3s | `INSTALL_K3S_CHANNEL=stable` (unpinned) | AWS EC2 (`user_data.sh`) |
| Traefik | bundled with k3s | Ingress class `traefik` on AWS |
| minikube | devcontainer feature | local cluster |
| Helm | 3.x on the server (`get-helm-3` from `main`); v4.3.0 in the codespace; `azure/setup-helm@v4` with no version input in CI | chart deploys |
| Argo CD | not recorded | minikube, namespace `argocd` |
| kube-prometheus-stack | not pinned (release `kube-prom`) | Prometheus Operator, Prometheus, Alertmanager, Grafana, kube-state-metrics |
| Grafana Loki chart | 7.3.0 | SingleBinary log store |
| Grafana Alloy chart | 1.13.1 | log collector |
| Kubernetes APIs used | `apps/v1`, `batch/v1`, `v1`, `networking.k8s.io/v1`, `monitoring.coreos.com/v1`, `argoproj.io/v1alpha1` | chart and `gitops/` |

## Cloud (AWS, eu-west-2, account 099021515478)

| Service | Use |
|---|---|
| EC2 (`t3.small`, Ubuntu 24.04) | single-node k3s server `uptime-dev-server` |
| VPC, internet gateway, security group | a public subnet with single-CIDR inbound access on port 80 |
| ECR | `uptime-monitor` repository: immutable tags, scan on push, keeps 5 images |
| S3 | Terraform state (native S3 lockfile) and DB backups |
| IAM, STS, OIDC | GitHub Actions roles and the EC2 instance role |
| SSM | Session Manager for admin access; Run Command for deploys |

Terraform provider: `hashicorp/aws ~> 6.0`, locked at **6.66.0** in all three `.terraform.lock.hcl` files.

## CI/CD

| Technology | Version or pin |
|---|---|
| GitHub Actions | `actions/checkout@v4`, `actions/setup-python@v5`, `hashicorp/setup-terraform@v3`, `aws-actions/configure-aws-credentials@v4`, `aws-actions/amazon-ecr-login@v2`, `azure/setup-helm@v4` (pinned by major tag, not by SHA) |
| Docker | the runner's default; Deploy builds use `--provenance=false` |
| jq | the runner's default; builds the SSM parameters in `deploy.yml` |

## Data Stores

| Store | Version | Notes |
|---|---|---|
| PostgreSQL | 16 | Kubernetes StatefulSet with a 1Gi PVC |
| SQLite | bundled with Python | the local default, and in-memory for tests |
| Loki filesystem | n/a | minikube; no retention configured |
| Prometheus TSDB | n/a | minikube; 2-day retention |
