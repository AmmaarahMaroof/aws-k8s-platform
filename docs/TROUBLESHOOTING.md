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