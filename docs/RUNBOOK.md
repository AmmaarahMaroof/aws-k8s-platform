# Runbook: Uptime Monitor platform

How to operate, deploy, roll back, restore and fully rebuild the platform, plus the local GitOps, logging and AI-agent setup.
Every procedure here has been run for real at least once.

**Environment:** `dev` (k3s on a single EC2 instance, eu-west-2)
**Last disaster-recovery test:** 9 October 2026 (see [Disaster recovery](#7-disaster-recovery-full-rebuild))

---

## 1. Quick reference

| I want to... | Command / action |
|---|---|
| Log in to AWS (CLI) | `aws login --remote` |
| Find the server | `aws ec2 describe-instances --filters "Name=tag:Name,Values=uptime-dev-server" --query "Reservations[].Instances[].[InstanceId,State.Name,PublicIpAddress]" --output table` |
| Start / stop the server | `aws ec2 start-instances --instance-ids <id>` / `aws ec2 stop-instances --instance-ids <id>` |
| Check SSM is ready | `aws ssm describe-instance-information --query "InstanceInformationList[].[InstanceId,PingStatus]" --output table` (wait for `Online`) |
| Get a shell on the server | `aws ssm start-session --target <id>` then `sudo -i` and `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml` |
| Check the app (on the server) | `curl -s localhost/status` and `kubectl -n uptime get pods` |
| Check the app (from my laptop) | `http://<public IP>/status` (only my allowed IP can reach port 80) |

**Always stop the server at the end of a session.** It is the main running cost.

---

## 2. Access

- **No SSH.** Port 22 is closed and the instance has no key pair. All admin access is through **SSM Session Manager**, controlled by IAM.
- **App access** (port 80) is restricted to a single allowed CIDR.
- **The SSM agent needs 1–3 minutes after boot** to show `Online`. Commands sent before that fail with `InvalidInstanceId`.

### My home IP changed and I'm locked out

1. Find the new IP: open `https://checkip.amazonaws.com` on the laptop.
2. Update `infra/envs/dev/terraform.tfvars`: `http_allowed_cidr = "<new IP>/32"`
3. `cd infra/envs/dev && terraform apply` (expect `1 to change`, in place)
4. Update the GitHub secret **`HTTP_ALLOWED_CIDR`** to `<new IP>/32` (no quotes), so CI's plan matches.

---

## 3. Deploying

### Normal release
Merge a PR to `main`. The **Deploy** workflow:
1. builds the image, scans it with Trivy, and pushes it to ECR tagged with the commit SHA
2. finds the running server by its `Name` tag and runs `scripts/deploy-on-server.sh <sha>` through SSM
3. the script refreshes the ECR pull secret and runs `helm upgrade --install --atomic`

**The server must be running and SSM `Online`**, otherwise the deploy fails at "Find the running server" (by design).
Docs, infra and monitoring-only changes don't trigger a deploy (`paths-ignore`).

### Redeploy the current version (e.g. onto a rebuilt server)
GitHub → **Actions → Deploy → Run workflow** on `main`.
The workflow skips the build if that commit's image is already in ECR, then deploys it. *(Added after DR finding #22; verified 9 October 2026.)*

Use **Run workflow**, not **Re-run jobs** on an old run: a re-run replays the original commit *and its original workflow file*, so it never picks up fixes merged since.

### Manual deploy (if the pipeline is unavailable)
On the server, as root:
```bash
SHA=<full commit SHA on main>
rm -rf /tmp/deploy && mkdir -p /tmp/deploy
curl -sfL https://github.com/AmmaarahMaroof/aws-k8s-platform/archive/$SHA.tar.gz | tar xz -C /tmp/deploy --strip-components=1
bash /tmp/deploy/scripts/deploy-on-server.sh $SHA
```
These are the same commands the pipeline sends through SSM. The image for `$SHA` must already exist in ECR.

---

## 4. Rolling back

**Automatic:** `helm upgrade --atomic` rolls back by itself if the new pods don't pass their readiness probes within 5 minutes.

**Manual (bad release that passed its probes):** on the server, as root:
```bash
helm -n uptime history uptime
helm -n uptime rollback uptime <previous revision>
kubectl -n uptime get pods
```
Then revert the bad commit on `main` with a PR, so Git matches what's running.

---

## 5. Responding to alerts

Alerts are defined in `helm/uptime-monitor/templates/prometheusrule.yaml`.

| Alert | Meaning | First checks |
|---|---|---|
| **MonitoredSiteDown** (warning, `for: 2m`) | A site the app monitors is failing its checks | Is the site really down? Open it in a browser. If it's up, check the checker: `kubectl -n uptime get cronjob,jobs` and the latest job's logs |
| **ApiPodRestarting** (critical) | An API pod restarted more than twice in 15 min | `kubectl -n uptime get pods`, then `kubectl -n uptime logs <pod> --previous` (logs of the crashed container), then `describe pod` → Events (look for `OOMKilled`, probe failures) |
| **ApiHighErrorRate** (critical) | More than 5% of API requests return 5xx | `kubectl -n uptime logs deploy/api`; check the database: `kubectl -n uptime get pods postgres-0` and `curl -s localhost/ready` |
| **Watchdog** | Always firing, by design (dead man's switch) | Nothing to do. If it **stops**, the alerting pipeline itself is broken |

**Triage order for any unhealthy pod:** `get pods` → `describe pod` (Events) → `logs` → `logs --previous` → `get endpoints`.

---

## 6. Backups and restore

### How backups work
- **CronJob** `db-backup`, daily at **02:00 UTC** (only runs while the server is on)
- Step 1: `pg_dump -Fc` (init container) → step 2: upload to `s3://uptime-monitor-db-backups-099021515478/postgres/uptime-<timestamp>.dump`
- Bucket: encrypted, versioned, private; **backups expire after 7 days**
- The bucket lives in **bootstrap**, outside the environment, so destroying the environment can't destroy its backups
- The server can **upload and read** backups but **cannot delete** them

### Take a backup now
On the server, as root:
```bash
kubectl -n uptime create job backup-manual-$(date +%s) --from=cronjob/db-backup
kubectl -n uptime get jobs | grep backup
```
Check it arrived (from the laptop): `aws s3 ls s3://uptime-monitor-db-backups-099021515478/postgres/ | sort | tail -3`

If the upload fails, read the container's logs **live** (`kubectl logs -f job/<name> -c upload`), because failed Job pods are cleaned up after `backoffLimit`.

### Restore the latest backup
On the server, as root:
```bash
LATEST=$(aws s3 ls s3://uptime-monitor-db-backups-099021515478/postgres/ | sort | tail -1 | awk '{print $4}')
aws s3 cp "s3://uptime-monitor-db-backups-099021515478/postgres/$LATEST" /tmp/restore.dump
kubectl -n uptime scale deployment api --replicas=0
kubectl -n uptime cp /tmp/restore.dump postgres-0:/tmp/restore.dump
kubectl -n uptime exec postgres-0 -- pg_restore -U uptime -d uptime --clean --if-exists /tmp/restore.dump
kubectl -n uptime scale deployment api --replicas=2
kubectl -n uptime rollout status deployment api
curl -s localhost/status
```
- The API is scaled to 0 first so nothing writes during the restore.
- `--clean --if-exists` drops the empty tables the app created at startup, then recreates them with the backup's data.

---

## 7. Disaster recovery (full rebuild)

**Scenario:** the environment's network and server are lost.
**Survives by design:** Git, S3 backups, ECR images, Terraform state, GitHub OIDC roles.

### Procedure
1. **Rebuild infrastructure:** `cd infra/envs/dev && terraform apply`. Note the new `instance_id` (`terraform output instance_id`).
2. **Wait for bootstrap:** user_data installs k3s, Helm and the AWS CLI. Wait for SSM `Online`.
3. **Recreate Secrets** (the one manual step). On the server, as root:
   ```bash
   kubectl create namespace uptime
   PW=$(openssl rand -hex 16)
   kubectl -n uptime create secret generic db-credentials --from-literal=POSTGRES_USER=uptime --from-literal=POSTGRES_PASSWORD="$PW" --from-literal=POSTGRES_DB=uptime
   kubectl -n uptime create secret generic app-config --from-literal=DATABASE_URL="postgresql+psycopg://uptime:${PW}@db:5432/uptime"
   unset PW
   ```
   A new random password is fine: the backup holds the data, not the old password.
4. **Deploy:** Actions → Deploy → **Run workflow** on `main` (or the manual deploy in section 3).
5. **Restore the data:** section 6.
6. **Verify:** `curl -s localhost/status` on the server, and `/status` from the laptop's browser.
7. **Stop the server.**

### Test results: 9 October 2026

| Step | Time (UTC) | Elapsed |
|---|---|---|
| Rebuild started (`terraform apply`) | 13:31:37 | 0:00 |
| Infrastructure applied | 13:34:48 | 3:11 |
| SSM online (server bootstrapped: k3s, Helm, AWS CLI) | 13:36:30 – 13:39:20 | ~5–8 min |
| Secrets created, app deployed (manually, see finding #22) | not recorded separately | |
| Data restored and verified | 13:48:55 | **17:18** |
| **Total recovery time** | | **≈ 17 minutes** |

**Result:** all sites (Google, DR-test-BBC, DR-test-GitHub) were restored from the S3 backup and visible in `/status` on the rebuilt server.

### Findings
- **#22 Pipeline couldn't redeploy an existing version.** "Run workflow" rebuilt the image for the current commit, and immutable ECR tags rejected the push. **Workaround:** manual deploy via SSM. **Fix:** the workflow now skips the build when the image already exists. **Status:** fixed and verified with a successful Run workflow deploy on 9 October 2026.
- **Instance ID changes on rebuild.** Commands must use the new ID; the deploy pipeline is unaffected because it finds the server by tag.

### Next improvements
1. **Automate Secret creation** during bootstrap (e.g. AWS Secrets Manager with External Secrets), removing the last manual step.
2. **Move ECR to a shared layer** (like the backup bucket), so the dev environment's state doesn't own a registry that prod also uses.
3. **Make the workflow wait for SSM `Online`** before deploying, so a deploy straight after starting the server doesn't fail.
4. **Script the restore** (section 6) so it's one command.

---

## 8. Local platform (minikube): GitOps, logging, AI agent

The **AWS server** (sections 1–7) runs the app deployed by the Deploy pipeline.
The **local minikube cluster** in the 4-core codespace runs the newer pieces: **Argo CD**, **Prometheus/Grafana**, **Loki + Alloy**, and the **AI-DLC agent** work.

### Fresh machine setup (Windows laptop + WSL2)

Rebuilt the whole local platform on a new laptop on 21 October 2026, after the codespace ran out of storage: **about 45 minutes** from an empty machine to the app, GitOps, metrics, logs and dashboards running. This is the order that works.

**Machine:** Windows 11, i7 (6 cores), 16 GB RAM, Ubuntu on WSL2, Docker Desktop (WSL 2 backend, Ubuntu integration on).

1. **Give WSL enough memory.** `C:\Users\<you>\.wslconfig`:
```ini
   [wsl2]
   memory=12GB
   processors=6
```
   Then `wsl --shutdown` and reopen Ubuntu. Check with `free -h`.
2. **Tools:** git, kubectl, minikube, Helm, Terraform, AWS CLI v2, Python 3. Check with
   `docker --version && kubectl version --client && minikube version && helm version && terraform -version && aws --version`
3. **Clone into the Linux home folder, not `/mnt/c`** (much faster, no line-ending problems), and open VS Code connected to WSL (`code .`, bottom-left shows **WSL: Ubuntu**).
4. **Start the cluster:** `minikube start --cpus=4 --memory=8192`
5. **Monitoring first.** The chart's `ServiceMonitor` and `PrometheusRule` need kube-prometheus-stack's CRDs, so install it before the app:
```bash
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm repo add grafana https://grafana.github.io/helm-charts
   helm repo update
   kubectl create namespace monitoring
   helm upgrade --install kube-prom prometheus-community/kube-prometheus-stack --version v0.94.1 -n monitoring -f monitoring/kube-prometheus-stack-values.yaml
   helm upgrade --install loki  grafana/loki  --version 7.3.0  -n monitoring -f monitoring/loki-values.yaml
   helm upgrade --install alloy grafana/alloy --version 1.13.1 -n monitoring -f monitoring/alloy-values.yaml
```
6. **Argo CD:**
```bash
   kubectl create namespace argocd
   kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```
7. **AWS login** (needed to pull the image from ECR): `aws configure` / `aws login --remote`, then `aws sts get-caller-identity`.
8. **Namespace and Secrets** (the manual step, kept out of Git on purpose):
```bash
   kubectl create namespace uptime
   PW=$(openssl rand -hex 16)
   kubectl -n uptime create secret generic db-credentials --from-literal=POSTGRES_USER=uptime --from-literal=POSTGRES_PASSWORD="$PW" --from-literal=POSTGRES_DB=uptime
   kubectl -n uptime create secret generic app-config --from-literal=DATABASE_URL="postgresql+psycopg://uptime:${PW}@db:5432/uptime"
   unset PW
   kubectl -n uptime create secret docker-registry ecr-pull \
     --docker-server=099021515478.dkr.ecr.eu-west-2.amazonaws.com \
     --docker-username=AWS --docker-password="$(aws ecr get-login-password --region eu-west-2)"
```
9. **Hand the app to Argo CD:** `kubectl apply -f gitops/uptime-app.yaml`
10. **Load the Grafana dashboard from the repo** (troubleshooting #35):
```bash
    kubectl -n monitoring create configmap uptime-dashboard --from-file=monitoring/dashboards/uptime-monitor.json
    kubectl -n monitoring label configmap uptime-dashboard grafana_dashboard=1
```
11. **Verify:** `kubectl get pods -A` (all Running), `kubectl -n argocd get applications` (`uptime`: Synced / Healthy), and **Uptime Monitor** in Grafana.

**On a laptop, `localhost` works.** Port-forwards from WSL open in the Windows browser at `http://localhost:3000` (Grafana) and `https://localhost:8080` (Argo CD). The codespace Ports-tab rule doesn't apply here.

**Gaps found by this rebuild:** the custom dashboard had been imported by hand (#35), and the kube-prometheus-stack version wasn't pinned, so the runbook couldn't reproduce the exact install.

**Next improvements:** script steps 5–10 into one `scripts/bootstrap-local.sh`, and manage Argo CD and the dashboard through Git as well.


### Start a session
```bash
minikube status                       # if stopped: minikube start --cpus=4 --memory=8g
kubectl -n argocd get applications    # uptime: Synced / Healthy
kubectl -n uptime get pods            # api ×2 + postgres Running
```
If pods show `ImagePullBackOff`, the ECR token has expired (12-hour lifetime). Refresh it:
```bash
kubectl -n uptime delete secret ecr-pull
kubectl -n uptime create secret docker-registry ecr-pull \
  --docker-server=099021515478.dkr.ecr.eu-west-2.amazonaws.com \
  --docker-username=AWS --docker-password="$(aws ecr get-login-password --region eu-west-2)"
```
(Run `aws login --remote` first if AWS credentials have expired.)

### Open the UIs
```bash
bash scripts/ui.sh     # or the three port-forwards below
kubectl -n argocd     port-forward svc/argocd-server                         8080:443 --address 0.0.0.0 > /dev/null 2>&1 &
kubectl -n monitoring port-forward svc/kube-prom-grafana                     3000:80  --address 0.0.0.0 > /dev/null 2>&1 &
kubectl -n monitoring port-forward svc/kube-prom-kube-prometheus-prometheus 9090:9090 --address 0.0.0.0 > /dev/null 2>&1 &
```
| Port | UI | Protocol (Ports tab) | Login |
|---|---|---|---|
| 8080 | Argo CD | **HTTPS** | `admin` / `kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" \| base64 -d` |
| 3000 | Grafana | HTTP | `admin` / `kubectl -n monitoring get secret kube-prom-grafana -o jsonpath="{.data.admin-password}" \| base64 -d` |
| 9090 | Prometheus | HTTP | none |

Always open them from the codespace **Ports** tab (globe icon), never `localhost` in a Mac browser. Stop them all with `pkill -f port-forward`.

### Deploy and roll back (GitOps)
- **Deploy:** change `helm/uptime-monitor/values-gitops.yaml` (or the chart) in a PR and merge it. Argo CD syncs `main` within ~3 minutes (click **Refresh** to speed it up).
- **Roll back:** `git revert` the bad commit in a PR and merge it. Argo syncs back. Don't use `kubectl` to fix things by hand: Argo's **self-heal** reverts manual changes to whatever Git says.
- **Check:** Argo UI → app **uptime** → Synced + Healthy, and **History and Rollback** shows which commit is live.

### Logs (Loki)
Grafana → **Explore** → data source **Loki** → Code mode, **one query per box**:
| Query | Shows |
|---|---|
| `{namespace="uptime", app="api"}` | all API logs |
| `{namespace="uptime", app="api"} != "/health" != "/ready"` | real traffic without probe noise |
| `{namespace="uptime"} \|~ "(?i)error\|warn"` | errors and warnings |
| `{namespace="uptime", pod=~"api-<hash>.*"}` | one specific ReplicaSet's pods |

A pod that never started (e.g. `ImagePullBackOff`) has **no logs**. Use `kubectl -n uptime describe pod <pod>` → **Events** instead.

### Checking alerts
Prometheus (port 9090) → **Alerts**: Inactive / **Pending** (waiting out its `for:` period) / **Firing**.
Useful queries in **Graph**:
- `kube_pod_container_status_waiting_reason{namespace="uptime"}`: pods stuck waiting, and why
- `ALERTS{namespace="uptime"}`: alert history, including when each went pending/firing

Known gap (game day 1): alerts aren't routed to any contact point yet, and a stuck rollout takes 30+ minutes to fire.

### Running a game day
Procedure used for [game day 1](incidents/2026-10-13-bad-image-tag.md):
1. Impact logger: `kubectl -n uptime port-forward svc/api 8000:80 &` then `while true; do echo "$(date +%T) $(curl -s -o /dev/null -w '%{http_code}' localhost:8000/health)"; sleep 5; done | tee gameday.log`
2. `kubectl -n uptime get pods -w` in a second terminal; Argo + Grafana open; timestamped notes.
3. Break it **through Git** (PR + merge), investigate for 15–20 minutes, fix it **through Git** (`git revert`), and note every time.
4. Write the review in `docs/incidents/`: timeline, impact (including hidden impact), root cause, what went well/didn't, actions.

### Working with the AI agent (Claude Code + AI-DLC)
- Start it in the repo with `claude`. **Auto mode stays off**: approve each command yourself.
- **Never approve** `kubectl apply/delete/scale/exec`, `aws`, `helm`, `terraform` or `git push` from the agent. Do those yourself.
- The agent may edit only `aidlc/**` and `docs/aidlc/**` without asking (see troubleshooting #33). **After any `aidlc update` or `aidlc config`**, check this wasn't reset:
  ```bash
  grep -n '"Edit(' .claude/settings.json      # must NOT show "Edit(/**)"
  aidlc doctor
  ```
- If you log in from the codespace and the browser lands on `localhost:<port>/callback?...` with "refused to connect", copy that URL and run `curl "<url>"` in a codespace terminal (troubleshooting #32).

---

## 9. Known gotchas

| Symptom | Cause / fix |
|---|---|
| `kubectl` on the server: `permission denied` on `k3s.yaml` | Not root. Run `sudo -i` and `export KUBECONFIG=/etc/rancher/k3s/k3s.yaml` (needed in every new SSM session) |
| Deploy fails: `InvalidInstanceId` | SSM agent not `Online` yet. Wait, then re-run the failed job |
| SSM never comes online | Check the security group still allows **all egress**: the agent must reach AWS on 443. Read the boot log with `aws ec2 get-console-output --instance-id <id> --latest` |
| Backup upload `AccessDenied` | The `db-backups` policy isn't attached: `aws iam list-role-policies --role-name uptime-dev-ec2-role` |
| Laptop can't reach `/status` | Home IP changed (section 2) |
| Deploy fails with `tag ... already exists` (immutable) | You used **Re-run jobs** on an old run, or the fix isn't on `main`. Use **Run workflow**; check with `git show origin/main:.github/workflows/deploy.yml` |
| `git push` rejected: "Changes must be made through a pull request" | You committed on local `main`. `git checkout -b <branch>`, push that, open a PR, then `git checkout main && git reset --hard origin/main` |
| CI lint fails on code nobody changed | An unpinned tool released new rules. Run the tool locally with `--fix`, and pin its version in `ci.yml` |
| CI `429` / `toomanyrequests` pulling images | Registry rate limit on shared runners. Re-run the job; images are pulled from ECR Public mirrors (troubleshooting #24, #26) |
| A workflow run fails instantly and is named by its file path, not its name | The workflow file is invalid (often indentation). Check with `actionlint` (troubleshooting #31) |
| Deploy run shows a yellow "Server is stopped" warning | Expected: the AWS server is off, so the deploy was skipped. Start it and use **Run workflow** |
| `kubectl`: `no route to host` on 192.168.49.2:8443 | minikube stopped with the codespace. `minikube start --cpus=4 --memory=8g` (troubleshooting #27) |
| A UI won't open / "refused to connect" on localhost | Open it via the codespace **Ports** tab; Argo needs protocol HTTPS (troubleshooting #25) |
| Grafana Loki: `no such host` | Loki isn't installed or the Service name is wrong: `helm list -n monitoring`, `kubectl get svc -n monitoring` (troubleshooting #29) |
| Every log line appears twice | More than one Alloy pod. Alloy must run as a single-replica Deployment (troubleshooting #30) |
| Branch is missing recent work | It was created from an out-of-date local `main`. Always `git checkout main && git pull` before `git checkout -b` |
| Custom Grafana dashboard missing after a rebuild | It was imported by hand. Load it as a labelled ConfigMap (troubleshooting #35) |

Full history of issues and fixes: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)