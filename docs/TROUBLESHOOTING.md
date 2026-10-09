# Troubleshooting log

Real problems hit while building this project, how they were diagnosed, and how they were fixed.
Format: **Symptom → Diagnosis → Cause → Fix → Lesson.**

---

## Dev environment

### 1. Codespace ignored the devcontainer config
- **Symptom:** `terraform: command not found`; Python was 3.14 instead of the 3.12 in the config.
- **Diagnosis:** The Python version didn't match the config, so the config wasn't being used. Listed the files with `ls -la`.
- **Cause:** The folder was named `devcontainer`, not `.devcontainer` (missing dot).
- **Fix:** `git mv devcontainer .devcontainer`, commit, rebuild the container.
- **Lesson:** When a tool silently ignores config, check the exact path and name first.

### 2. Codespace stuck in recovery mode
- **Symptom:** "This codespace is currently running in recovery mode due to a container error."
- **Diagnosis:** Read the creation log (Cmd+Shift+P → *Codespaces: View Creation Log*) and searched it for `ERROR`.
- **Cause:** The docker-in-docker feature didn't support the base image's new Debian release ("trixie").
- **Fix:** Pinned the image to `mcr.microsoft.com/devcontainers/python:3.12-bookworm`.
- **Lesson:** Pin versions instead of relying on `latest`, so an upstream change can't break the build.

---

## Containers

### 3. Container exited immediately after `docker run -d`
- **Symptom:** `curl` couldn't connect; `docker logs` said "No such container".
- **Diagnosis:** Ran the container in the foreground (without `-d` and `--rm`) to see the output.
- **Cause:** `sqlite3.OperationalError: unable to open database file`. The app ran as non-root `appuser`, but `/app` was owned by root.
- **Fix:** Added `RUN chown appuser:appuser /app` to the Dockerfile (code stays root-owned and read-only).
- **Lesson:** Hardening (non-root) can break things that quietly relied on root. Grant only the write access needed.

### 4. `curl: Connection reset by peer` right after starting the container
- **Symptom:** The health check failed, but the container was running.
- **Cause:** `curl` ran before uvicorn had finished starting (a startup race).
- **Fix:** Waited a few seconds before checking. In Kubernetes this is handled by a readiness probe on `/ready`.
- **Lesson:** "Running" isn't the same as "ready". That's why readiness probes exist.

---

## CI/CD

### 5. Linter flagged `Depends()` in every FastAPI endpoint (ruff B008)
- **Cause:** A false positive: FastAPI is designed to use `Depends()` as a default argument.
- **Fix:** Narrow exception in `ruff.toml` (`extend-immutable-calls = ["fastapi.Depends", "fastapi.Query"]`) with a comment explaining why.
- **Lesson:** Configure false positives narrowly and document them. Don't disable the rule.

### 6. OIDC: "Not authorized to perform sts:AssumeRoleWithWebIdentity"
- **Symptom:** The `terraform-plan` CI job couldn't sign in to AWS.
- **Diagnosis:** Confirmed the IAM role existed (`aws iam get-role`), then added a temporary CI step printing the OIDC token's claims (not the token itself).
- **Cause:** GitHub's `sub` claim included immutable owner and repo IDs: `repo:AmmaarahMaroof@143191112/aws-k8s-platform@1394704938:pull_request`. The trust policy expected the older format without IDs.
- **Fix:** Updated the trust policy to match the exact `sub` values, without loosening it with wildcards.
- **Lesson:** Compare what the system actually sends with what you expect. Fix the mismatch without weakening security.

---

## Terraform

### 7. `terraform init` said "empty directory"
- **Cause:** Ran it from the repo root instead of the folder containing the `.tf` files.
- **Fix:** `cd infra/bootstrap` (or `infra/envs/dev`) first.
- **Lesson:** Terraform works on the current directory. Check `pwd` before running it.

### 8. "Error acquiring the state lock" (S3 412 PreconditionFailed)
- **Diagnosis:** Read the lock info: *Who* was my own codespace, *Created* over an hour earlier, operation `apply`. Confirmed no Terraform process was running (only `terraform-ls`, the editor's language server).
- **Cause:** An earlier `apply` was interrupted and left a stale lock file in S3.
- **Fix:** `terraform force-unlock <LOCK_ID>`, then re-ran `plan` and `apply`.
- **Lesson:** Locking prevents concurrent changes. Only force-unlock after confirming nothing else is running.

---

## AWS

### 9. Enabling IAM Identity Center would have switched off the Free plan
- **Symptom:** The setup page warned that creating an AWS Organization upgrades the account to pay-as-you-go and removes the free-tier credits.
- **Fix:** Cancelled. Used an IAM user with MFA instead, and `aws login` for short-lived CLI credentials.
- **Lesson:** Read warnings before clicking, and check the cost impact of account-level changes.

### 10. ECR showed untagged images and an empty scan status
- **Cause:** Docker's default build attestations (provenance/SBOM) made the push a multi-item bundle (a manifest list).
- **Fix:** Built with `--provenance=false --sbom=false` for a single, scannable image. Deleting the bundle needed two passes, because the child images were still referenced until the bundle was removed.
- **Lesson:** Understand what your build tool actually pushes.

### 11. ECR found 4 critical CVEs that the CI Trivy scan didn't block
- **Cause:** CI uses `--ignore-unfixed`; ECR reports everything. All four were in base-image OS packages.
- **Fix:** Triaged them. OpenSSL had a patch, so it was upgraded in the Dockerfile (criticals 4 → 3, 12 findings removed in total). The Perl CVEs had no fix, and Perl isn't used by the app, so they're documented as accepted risk in `docs/SECURITY.md`.
- **Lesson:** Scanners differ. Triage findings, fix what's fixable, document the rest, and verify with a rescan.

---

## Kubernetes

### 12. One API replica restarted once on first deploy
- **Symptom:** `kubectl get pods` showed `RESTARTS 1` on one of the two API pods, a few seconds after creation. Everything worked afterwards.
- **Diagnosis:** `kubectl -n uptime logs <pod> --previous` (logs of the crashed container, not the current one).
- **Cause:** `UniqueViolation ... sites_id_seq already exists`. Both replicas ran "create tables if missing" at startup against an empty database at the same moment; one won, the other crashed. On restart the tables existed, so it started fine (a race condition).
- **Fix (current):** Documented. It only affects the very first start on an empty database, and Kubernetes self-heals it.
- **Fix (proper, planned):** Run schema migrations once, as a separate Kubernetes Job or init step (e.g. Alembic), before the API rolls out, instead of every replica doing it at startup.
- **Lesson:** A restart count above 0 is a clue, even when everything looks healthy. `--previous` is the first command for any restart. Startup code that is safe with one instance may not be safe with several.

### 13. API pods crashed once on every fresh Helm install
- **Symptom:** After `helm install`, both API pods went `Error` → restarted once at ~5s. Postgres only became Ready at ~7s.
- **Diagnosis:** Compared timings in `kubectl get pods -w`; `kubectl logs <pod> --previous` showed a database connection error.
- **Cause:** Helm creates everything at once. The API started before Postgres accepted connections, failed to create its tables, and exited. Kubernetes has no `depends_on` like Docker Compose.
- **Fix:** Added an init container (`wait-for-db`) that loops on `pg_isready -h db` before the API container starts. Fresh installs now show `Init:0/1` → `1/1 Running` with 0 restarts.
- **Lesson:** Kubernetes doesn't order startup between workloads. Use init containers for hard dependencies, and keep the app tolerant of dependencies being briefly unavailable.

### 14. Pods stuck in CreateContainerConfigError after rebuilding minikube
- **Symptom:** The checker pod showed `CreateContainerConfigError`.
- **Diagnosis:** `kubectl describe pod` → Events showed the Secret it references could not be found.
- **Cause:** After `minikube delete`, everything in Git was redeployable, but the Secrets (created by hand, deliberately outside Git) were gone.
- **Fix:** Recreated the Secrets; the pods recovered without a reinstall.
- **Lesson:** Anything created by hand is the first thing missing after a rebuild. Secret creation belongs in the rebuild runbook.

### 15. Kubernetes API refused connections after installing the monitoring stack
- **Symptom:** `kubectl` watch dropped, then `connection to the server ... was refused`; three monitoring targets showed `connection refused`.
- **Diagnosis:** `minikube status` and `free -h`: 6.6 of 7.8 GB used, 1.2 GB available, no swap.
- **Cause:** kube-prometheus-stack plus the app needed more than a 2 CPU / 4 GB cluster could provide; components were starved and restarted.
- **Fix:** Moved to a 4-core / 16 GB machine and gave minikube 4 CPUs / 8 GB. All targets came up.
- **Lesson:** Observability has its own resource cost. Capacity planning includes the tools that watch the system (the same reason the stack isn't on the 2 GB EC2 instance).

### 16. Status panel kept showing a deleted site as DOWN
- **Symptom:** After deleting a site, the Grafana Stat panel still showed it as DOWN, although the API and Prometheus no longer had it.
- **Cause:** The panel used a **range** query and showed the last value within the 30-minute window.
- **Fix:** Changed the query type to **Instant** (the current value only).
- **Lesson:** Range queries suit graphs over time; instant queries suit "what is the state right now" panels.

### 17. "is not a valid CIDR block: http_allowed_cidr"
- **Cause:** Wrote `cidr_blocks = ["http_allowed_cidr"]`. The quotes made Terraform use the literal text instead of the variable's value.
- **Fix:** `cidr_blocks = [var.http_allowed_cidr]`, i.e. reference variables with `var.` and no quotes.
- **Lesson:** Quotes mean "this exact text"; `var.name` means "look up this value".

### 18. Deploy failed with InvalidInstanceId right after starting the server
- **Symptom:** Deploy job failed in "Deploy via SSM" with `InvalidInstanceId: Instances not in a valid state` (AWS CLI exit code 254).
- **Diagnosis:** `aws ssm describe-instance-information` didn't show the instance as Online.
- **Cause:** EC2 "running" only means the machine has booted. The SSM agent needs to register with AWS before it can receive commands. (In this case it never did, because of #19.)
- **Fix:** Fixed #19, waited for the agent to show Online, then re-ran the failed job.
- **Lesson:** "Running" isn't "ready" (the readiness-probe lesson again, at server level). Possible improvement: the workflow waits for SSM `PingStatus = Online` before deploying.

### 19. SSM went offline after locking down the security group
- **Symptom:** Deploys failed and `describe-instance-information` returned nothing, even with the server running.
- **Diagnosis:** With no SSH or SSM access, read the boot log via `aws ec2 get-console-output`: the SSM agent got `dial tcp ...:443: i/o timeout` calling the SSM endpoint. `describe-security-groups` then showed ingress empty and egress set to my home IP.
- **Cause:** When restricting port 80 (phase 8a), the CIDRs were swapped: my IP went on the egress rule and ingress lost its CIDR. The server couldn't reach AWS APIs, ECR or GitHub, and nobody could reach the app.
- **Fix:** Ingress port 80 → allowed CIDR only; egress → `0.0.0.0/0`. SSM reconnected by itself.
- **Lesson:** Ingress and egress are separate decisions. A security test must check that the control allows the right thing as well as blocks the wrong thing; a rule that blocks everything also passes a "blocked" test.

### 20. Backup upload failed with AccessDenied
- **Symptom:** `pg_dump` succeeded; the upload failed: `assumed-role/uptime-dev-ec2-role ... is not authorized to perform: s3:PutObject ... because no identity-based policy allows the s3:PutObject action`.
- **Diagnosis:** The error showed credentials were working (correct assumed role) but no policy allowed the action. `aws iam list-role-policies` showed `db-backups` wasn't attached.
- **Cause:** The policy is created conditionally (`count = var.backup_bucket_name == null ? 0 : 1`) and the dev environment wasn't passing the bucket name, so Terraform created zero copies.
- **Fix:** Passed `backup_bucket_name` to the compute module and applied. The next backup uploaded.
- **Lesson:** Read AWS AccessDenied errors in full: they name who, what, where and why. Conditional resources fail silently when their input is missing.

### 21. Failed Job pod disappeared before its logs could be read
- **Symptom:** `kubectl logs job/... -c upload` printed nothing; the pod showed `RESTARTS 2` then `Terminating`.
- **Cause:** The container failed, restarted up to the Job's `backoffLimit`, then the Job gave up and deleted the pod, along with its logs.
- **Fix:** Re-ran the Job and streamed its logs live with `kubectl logs -f`.
- **Lesson:** Watch Job logs live, or check `kubectl get events`. In production, ship logs to a central store (e.g. Loki or CloudWatch) so they outlive the pod.

### 22. DR test: "Run workflow" couldn't redeploy because the image tag already existed
- **Symptom:** During the disaster-recovery test, the manual Deploy run failed at Push: `tag ... already exists ... cannot be overwritten because the tag is immutable`.
- **Cause:** The workflow always rebuilt and pushed the image for the current commit. That commit's image was already in ECR, and immutable tags (correctly) refuse overwrites, so the job failed before deploying.
- **Workaround:** Ran the same deploy script by hand on the new server via SSM, using the existing image.
- **Fix:** The workflow now checks ECR first (`aws ecr batch-get-image`) and skips build, scan and push if the commit's image already exists, so "Run workflow" works as a pure redeploy.
- **Lesson:** This is exactly what DR tests are for. The pipeline worked for normal releases, but not for "redeploy the current version onto new infrastructure", the main thing you need in a recovery.

**Follow-up (fix verification):** two more failed runs before the fix worked:
1. "Re-run jobs" on the old failed run replays the original commit *and its original workflow file*, so it can't pick up a fix merged later. Use **Run workflow** for a new run on the latest `main`.
2. The fix commit had been made on local `main`, so it never reached GitHub (`git push` was rejected by the branch ruleset). `git show origin/main:<file>` shows what's really on main. Moved the commit to a branch and merged it via PR.
3. The existence check was switched from `aws ecr batch-get-image` to `docker manifest inspect`.

## 23. CI lint failed on code nobody changed

**Symptom:** the PR changed only `deploy.yml`, but the `test` job failed at Lint: `UP017 Use datetime.UTC alias` in `app/models.py`.

**Cause:** ruff wasn't pinned in CI, so every run installed the latest version. A new release enforced UP017 (`timezone.utc` → `datetime.UTC`) on existing code.

**Fix:** `ruff check app tests --fix`, then pinned ruff's version in `ci.yml`.

**Lesson:** pin tool versions in CI. Builds should only fail when *our* code changes.

**Verified:** Run workflow on 9 Oct 2026 deployed successfully without rebuilding.
---

## Handy fixes

| Symptom | Fix |
|---|---|
| Output stuck at `(END)` or `:` | Press `q`. For AWS CLI, disable the pager: `aws configure set cli_pager ""` |
| Terminal shows `>` and waits | A multi-line paste was incomplete. Press Ctrl+C and paste the whole block |
| `fatal: a branch named ... already exists` | `git checkout <branch>` instead of `git checkout -b` |
| Git LFS hook warnings in a container without LFS | Remove the unused hooks: `rm -f .git/hooks/pre-push .git/hooks/post-*` |
| Files created by a command don't exist | Check with `ls -la` / `cat` before moving on |


## Kubernetes

### 12. One API replica restarted once on first deploy
- **Symptom:** `kubectl get pods` showed `RESTARTS 1` on one of the two API pods, a few seconds after creation. Everything worked afterwards.
- **Diagnosis:** `kubectl -n uptime logs <pod> --previous` (logs of the crashed container, not the current one).
- **Cause:** `UniqueViolation ... sites_id_seq already exists`. Both replicas ran "create tables if missing" at startup against an empty database at the same moment; one won, the other crashed. On restart the tables existed, so it started fine (a race condition).
- **Fix (current):** Documented. It only affects the very first start on an empty database, and Kubernetes self-heals it.
- **Fix (proper, planned):** Run schema migrations once, as a separate Kubernetes Job or init step (e.g. Alembic), before the API rolls out, instead of every replica doing it at startup.
- **Lesson:** A restart count above 0 is a clue, even when everything looks healthy. `--previous` is the first command for any restart. Startup code that is safe with one instance may not be safe with several.