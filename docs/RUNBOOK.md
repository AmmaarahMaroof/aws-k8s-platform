# Runbook: Uptime Monitor platform

How to operate, deploy, roll back, restore and fully rebuild the platform.
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

## 8. Known gotchas

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

Full history of issues and fixes: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
