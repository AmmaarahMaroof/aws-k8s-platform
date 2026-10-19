# Architecture: aws-k8s-platform

## Architecture Analysis

### System Overview

There is one Python service image, `uptime-monitor`, run by two Kubernetes workloads:

- the **Uptime API** Deployment (2 replicas);
- the **Checker CronJob**, every 5 minutes.

Both write to a single **PostgreSQL** StatefulSet. The Helm chart `helm/uptime-monitor` packages all three and can also
render an Ingress, a ServiceMonitor, a PrometheusRule and a db-backup CronJob. The chart reaches two clusters by two
different routes:

1. **AWS dev (k3s on EC2), by push.** GitHub Actions builds and pushes a SHA-tagged image to ECR. It then uses SSM to run
   `scripts/deploy-on-server.sh`, which runs `helm upgrade --install --atomic --set image.tag=<sha>`.
2. **Local minikube, by pull.** The Argo CD `Application` `uptime` tracks `main` with `values-gitops.yaml`, which pins
   the tag, and auto-syncs with prune and selfHeal.

Observability (kube-prometheus-stack, Loki, Alloy, Grafana) is installed **only on minikube**, using the values in
`monitoring/`. AWS infrastructure is Terraform: a bootstrap layer (state bucket, backups bucket, GitHub OIDC roles) and
per-environment network, compute and registry. The full component list is in `component-inventory.md`.

### Architectural Style

- **Application**: a small layered monolith.
  - API layer: `app/main.py`.
  - Logic: `app/checks.py`.
  - Persistence: `app/models.py` and `app/database.py`.
  - Cross-cutting: `app/config.py`, `app/logging_setup.py`, `app/metrics.py`.

  One image serves two process roles, a web server and a batch job, chosen by the container command.
- **Platform**: single-node Kubernetes in each environment.
  - Configuration is Twelve-Factor style: every setting comes from an environment variable (`app/config.py`).
  - Secrets are created out-of-band and never stored in Git (`values.yaml:9-11`).
  - Images are addressed by immutable SHA tags (ECR `IMMUTABLE`).
- **Delivery**: hybrid. CI pushes to AWS; GitOps pulls into minikube.

### Component Relationships

```mermaid
flowchart LR
    subgraph gh["GitHub"]
        repo["Repo main branch"]
        ci["CI workflow"]
        dep["Deploy workflow"]
    end
    subgraph aws["AWS eu-west-2"]
        ecr["ECR uptime-monitor"]
        ssm["SSM Run Command"]
        s3b["S3 db backups bucket"]
        s3s["S3 tfstate bucket"]
        subgraph ec2["EC2 k3s namespace uptime"]
            apiA["api Deployment"]
            chkA["checker CronJob"]
            pgA["postgres StatefulSet"]
            bkA["db-backup CronJob"]
            trf["Traefik Ingress"]
        end
    end
    subgraph mk["minikube"]
        argo["Argo CD app uptime"]
        subgraph ns["namespace uptime"]
            apiM["api Deployment"]
            chkM["checker CronJob"]
            pgM["postgres StatefulSet"]
        end
        subgraph mon["namespace monitoring"]
            prom["Prometheus"]
            ksm["kube-state-metrics"]
            am["Alertmanager"]
            graf["Grafana"]
            loki["Loki"]
            alloy["Alloy"]
        end
    end
    repo --> ci
    repo --> dep
    ci -->|"terraform plan"| s3s
    dep -->|"push sha image"| ecr
    dep -->|"send-command"| ssm
    ssm -->|"deploy-on-server.sh"| ec2
    apiA -.->|"pull"| ecr
    chkA -.->|"pull"| ecr
    trf --> apiA
    apiA --> pgA
    chkA --> pgA
    bkA --> pgA
    bkA -->|"pg_dump upload"| s3b
    repo -->|"poll main"| argo
    argo -->|"helm sync"| ns
    apiM -.->|"pull via ecr-pull secret"| ecr
    chkM -.->|"pull via ecr-pull secret"| ecr
    apiM --> pgM
    chkM --> pgM
    prom -->|"scrape /metrics"| apiM
    prom --> ksm
    prom --> am
    alloy -->|"pod logs"| loki
    graf --> prom
    graf --> loki
```

Text fallback:
- GitHub `main` triggers CI and Deploy.
  - CI only validates; its Terraform plan reads the S3 state.
  - Deploy pushes `uptime-monitor:<sha>` to ECR and uses SSM to run `deploy-on-server.sh` on EC2.
- On EC2 k3s (namespace `uptime`):
  - The Traefik Ingress routes to the api Service and Deployment.
  - api and checker connect to the `db` Service (the postgres StatefulSet).
  - The db-backup CronJob dumps postgres and uploads the dump to the S3 backups bucket.
  - Images are pulled from ECR using the `ecr-pull` secret.
- On minikube:
  - Argo CD polls `main` and syncs the chart into namespace `uptime`.
  - Prometheus scrapes the api `/metrics` endpoint (through the ServiceMonitor) and kube-state-metrics. It sends alerts to Alertmanager, which uses only the default receiver.
  - Alloy ships every pod's logs to Loki, and Grafana reads both Prometheus and Loki.

### Data Flow

1. **Write path (checks).**
   - The checker CronJob, or `POST /checks/run`, reads every `Site` and calls `httpx.get(url)`. The timeout is `CHECK_TIMEOUT_SECONDS` (default 5s).
   - It inserts one `Check` row per site, commits, and logs one JSON line per site (`app/checks.py:42-55`).
2. **Read path (status).**
   - `/status`, `/sites/{id}/checks` and `/metrics` read the latest check per site from Postgres.
   - `/metrics` clears and rebuilds the `site_up` and `site_response_ms` gauges on every scrape (`app/main.py:73-86`). CronJob results therefore show up and deleted sites disappear.
   - The gauges carry **no timestamp or age**. If the checker stops writing, `site_up` keeps reporting the last stored result.
3. **Metrics path.** ServiceMonitor `api` (port `http`, `/metrics`, every 15s) feeds Prometheus, which evaluates PrometheusRule `uptime-monitor` and sends firing alerts to Alertmanager. kube-state-metrics provides the pod status series.
4. **Log path.** The app writes JSON logs to stdout. Alloy's `loki.source.kubernetes` reads them through the Kubernetes API and sends them to Loki with the labels `namespace`, `pod`, `container` and `app`. **Kubernetes Events are not collected.**
5. **Backup path.** `pg_dump -Fc` writes to an emptyDir, then `aws s3 cp` uploads it to `s3://uptime-monitor-db-backups-099021515478/postgres/uptime-<ts>.dump`. Backups expire after 7 days. The EC2 role can Put and Get, but not Delete.

### Key Design Decisions

| Decision | Evidence | Implication |
|---|---|---|
| One image for the API and the checker | `templates/api.yaml:41`, `templates/checker.yaml:23` | A bad tag breaks both. The checker has no old pod to fall back on, so monitoring went silent in the game day |
| Immutable SHA tags in ECR | `infra/modules/registry/main.tf:16` | Each tag maps to one exact build. Redeploys reuse existing images (`deploy.yml:43-54`) |
| ECR keeps only 5 images | `infra/modules/registry/main.tf:29-43` | Older SHAs, including one pinned in the GitOps values, can expire |
| Secrets kept outside Git | `values.yaml:9-11`, `RUNBOOK.md:144-152` | A manual step after every rebuild. `DATABASE_URL` embeds the DB password |
| Liveness without the DB, readiness with it | `app/main.py:58-70`, `templates/api.yaml:48-59` | A DB outage takes pods out of service without causing restart loops |
| `wait-for-db` init container on the API only | `templates/api.yaml:35-38` | Fixes the fresh-install crash (TROUBLESHOOTING #13). The checker has no such wait |
| `helm upgrade --atomic --timeout 5m` | `scripts/deploy-on-server.sh:20-23` | On AWS, Helm rolls back automatically if new pods are not Ready within 5 minutes |
| Argo CD auto-sync with prune and selfHeal | `gitops/uptime-app.yaml:19-22` | On minikube, Git is the only lever: manual kubectl changes are reverted |
| SSM only: no SSH, IMDSv2 required, encrypted root volume | `infra/modules/compute/main.tf:68-104` | All admin access goes through IAM |
| Single-CIDR ingress on port 80 | `infra/modules/network/main.tf:43-49` | The API has no authentication, so the network rule is the only access control |
| Schema created by `create_all` at startup | `app/database.py:53-58` | No migrations, and a first-start race between replicas (TROUBLESHOOTING #12) |
| Investigation tooling lives only on minikube | `README.md:93`, `monitoring/*` | Evidence for AWS incidents is limited to kubectl and Helm history on the server |

The alternatives the project weighed (EKS, NAT gateway, ALB, monitoring on a larger instance) and why they were rejected
are recorded in `README.md:87-95`.

### Improvement Opportunities

These are observations, not proposed work. The full register is in `code-quality-assessment.md` § Technical Debt Register.

- Alerting does not cover the failure seen in the reference incident: there is no freshness signal for checks, no
  "pod stuck waiting" alert, no Alertmanager receiver, and Events are not collected (D2).
- The CI path does not validate what GitOps deploys: it never checks that the image tag exists and lints Helm only with
  default values (D3).
- There is no observability on the AWS cluster (D9).
- No least-privilege Kubernetes identities exist (D5).
- The raw `k8s/` manifests duplicate the chart and can drift from it (D12).

## Interaction Diagrams

### 1. Release via GitOps (minikube): the path of the reference incident

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant GH as GitHub main
    participant CI as CI workflow
    participant Argo as Argo CD
    participant K8s as minikube ns uptime
    participant ECR as ECR
    Dev->>GH: PR edits values-gitops.yaml image.tag
    GH->>CI: run test, build-and-scan, terraform, helm lint
    CI-->>GH: pass, tag existence not checked
    Dev->>GH: merge PR
    Note over GH: Deploy workflow ignores values-gitops.yaml
    Argo->>GH: poll main, about 3 min or Refresh
    Argo->>K8s: render chart and apply with prune and selfHeal
    K8s->>ECR: pull repository:tag with ecr-pull secret
    alt tag exists
        ECR-->>K8s: image
        K8s-->>Argo: new api pods Ready, Synced and Healthy
    else tag missing or expired
        ECR-->>K8s: not found
        K8s-->>Argo: ErrImagePull then ImagePullBackOff, Degraded
        Note over K8s: old api ReplicaSet keeps serving, every checker Job pod fails
    end
    Dev->>GH: git revert PR
    Argo->>K8s: sync back to previous tag
```

Text fallback:
1. A PR changes `values-gitops.yaml`.
2. CI validates the code, the image and the chart, but not whether the tag exists, and the PR is merged.
3. The Deploy workflow does not run, because the file is in its `paths-ignore` list.
4. Argo CD polls `main` and applies the rendered chart, and the kubelet pulls the image from ECR.
5. If the pull fails, new API pods go into ImagePullBackOff while the old ReplicaSet keeps serving. Every checker Job pod fails, so no new `checks` rows are written.
6. Recovery is a `git revert` PR, which Argo CD syncs back.

### 2. Release to AWS (push)

```mermaid
sequenceDiagram
    participant GH as GitHub main
    participant DW as Deploy workflow
    participant STS as AWS STS OIDC
    participant ECR as ECR
    participant EC2 as EC2 uptime-dev-server
    participant SSM as SSM
    participant K3s as k3s ns uptime
    GH->>DW: push to main, path not ignored
    DW->>STS: assume github-actions-deploy
    DW->>ECR: manifest inspect repo:sha
    alt image missing
        DW->>DW: docker build and Trivy CRITICAL gate
        DW->>ECR: push repo:sha
    end
    DW->>EC2: describe-instances with tag Name=uptime-dev-server, running
    alt server stopped
        DW-->>GH: warning, deploy skipped
    else running
        DW->>SSM: send-command AWS-RunShellScript
        SSM->>EC2: fetch repo tarball at sha, run deploy-on-server.sh sha
        EC2->>K3s: refresh ecr-pull secret
        EC2->>K3s: helm upgrade --install --atomic --set image.tag=sha
        K3s-->>EC2: Ready, or automatic rollback after 5 min
        DW->>SSM: poll get-command-invocation for up to 6 min
    end
```

Text fallback:
1. Deploy assumes the OIDC deploy role.
2. It builds, scans and pushes the image only when `repo:sha` is not already in ECR.
3. It finds the running server by its tag. If the server is stopped, it warns and skips the deploy.
4. Otherwise it sends an SSM shell command that downloads the commit tarball and runs `deploy-on-server.sh <sha>`.
5. The script refreshes the ECR pull secret and runs `helm upgrade --atomic`.
6. The workflow polls SSM until the command succeeds or fails.

This path is only valid if GitHub accepts `deploy.yml`, which is doubtful (`code-quality-assessment.md` D1).

### 3. Uptime check and alert path

```mermaid
sequenceDiagram
    participant Cron as checker CronJob
    participant Site as Monitored website
    participant DB as Postgres
    participant API as api pods
    participant Prom as Prometheus
    participant AM as Alertmanager
    Cron->>DB: select sites
    Cron->>Site: HTTP GET with 5s timeout
    Site-->>Cron: status code or transport error
    Cron->>DB: insert checks rows and commit
    Prom->>API: scrape /metrics every 15s
    API->>DB: latest check per site
    API-->>Prom: site_up, site_response_ms, http_requests_total
    Prom->>Prom: evaluate MonitoredSiteDown, ApiPodRestarting, ApiHighErrorRate
    Prom->>AM: firing alerts
    AM-->>AM: default receiver, nobody is notified
```

Text fallback:
1. The checker writes check rows.
2. Prometheus scrapes the API, which derives `site_up` from the **latest** row.
3. Prometheus evaluates the alert rules and sends firing alerts to Alertmanager, which has no receiver configured.

If the checker stops writing rows, `site_up` keeps its last value, so `MonitoredSiteDown` cannot fire (incident review line 35).

### 4. Incident investigation as practised today (manual)

```mermaid
flowchart TD
    A["Symptom seen on screen or alert in Prometheus UI"] --> B["kubectl get pods"]
    B --> C["kubectl describe pod, read Events"]
    C --> D["kubectl logs and logs --previous"]
    D --> E["Loki query in Grafana by namespace and app"]
    C --> F["PromQL kube_pod_container_status_waiting_reason and ALERTS"]
    B --> G["Argo CD app history shows the live commit"]
    G --> H["git log and PR diff"]
    E --> I["Likely cause"]
    F --> I
    H --> I
    I --> J["Fix through Git: revert PR, Argo CD syncs"]
```

Text fallback:
- The triage order documented in `docs/RUNBOOK.md:96` and section 8 is: get pods, describe pod (Events), logs, logs --previous, then get endpoints.
- Loki queries, PromQL (`kube_pod_container_status_waiting_reason`, `ALERTS`) and the Argo CD history fill in the rest, and Git history identifies the change.
- The fix goes through a revert PR.

All of this is done by hand across four tools (`docs/aidlc/inception/intent.md:4-5`). A pod that never started has no
logs, so Events are the only direct evidence for a failed image pull (`docs/RUNBOOK.md:232`).
