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

<<<<<<< Updated upstream
## 24. CI broke repeatedly on a docs-only PR: rate limits, then my own fixes

**Symptom:** the Phase 9 PR (README/docs only) failed `build-and-scan` several times in a row, for different reasons.

**What happened, in order:**
1. **Docker Hub rate limit:** `429 Too Many Requests` pulling `python:3.12-slim-bookworm`. Docker Hub limits anonymous pulls per IP, and GitHub's shared runners hit it.
   **Fix:** pulled the base image from the AWS mirror instead: `public.ecr.aws/docker/library/python:3.12-slim-bookworm`.
2. **Same limit, different image:** the Trivy scanner (`aquasec/trivy:latest`) also came from Docker Hub.
   **Fix:** `public.ecr.aws/aquasecurity/trivy:0.56.2`, pinned instead of `:latest` (same lesson as #23).
3. **Lost arguments while editing:** Trivy printed its help text and `image: command not found`. A line-ending `\` had been dropped, so bash ran the next line as a separate command. In `deploy.yml` the `image --exit-code 1 --severity CRITICAL` arguments had been deleted entirely, which would have silently turned the security gate off.
   **Fix:** restored the `\` line continuations and the arguments.
4. **A typo:** `unknown flag: --ignore-unfixed--no-progress` (a missing space).
5. **Real findings:** once the scan ran properly, it found 2 CRITICALs in base-image OS packages, `libsqlite3-0` (CVE-2025-7458, no fix yet) and `zlib1g` (CVE-2023-45853, Debian: will_not_fix). Neither has a patch available; the app doesn't use SQLite.
   **Fix:** `--ignore-unfixed` in both workflows (fail on fixable criticals only), with the accepted CVEs and reasons documented in SECURITY.md.

**Lessons:**
- CI depends on external services (registries, vulnerability databases). Know which ones, and have a fallback.
- Pin tool versions; `:latest` can change under you.
- When editing a security gate, check it still *fails* when it should. A scan with no `--exit-code` passes everything.
- Don't switch a gate off to get green; decide what it should block, and document the exceptions.

## 25. Argo CD UI "refused to connect" on localhost:8080

**Symptom:** `kubectl port-forward` was running and logging connections, but the browser showed `ERR_CONNECTION_REFUSED` at `localhost:8080`.

**Cause:** the port-forward runs in the codespace; `localhost` in the browser meant my Mac, where nothing listens. Argo CD also only serves HTTPS.

**Fix:** opened the port from the codespace **Ports** tab and changed its protocol to **HTTPS**.

**Lesson:** "localhost" is whichever machine you're on. Always check which machine a port is actually forwarded to.

## 26. CI scan failed: `toomanyrequests` pulling Trivy from ECR Public

**Symptom:** `docker: toomanyrequests: Rate exceeded` in the Trivy scan step, on a PR that only changed YAML.

**Cause:** ECR Public also rate-limits anonymous pulls, and GitHub's shared runners can hit the limit. It's looser than Docker Hub (#24), but not unlimited.

**Fix:** re-ran the failed job.

**Next step if it recurs:** install Trivy with the pinned `aquasecurity/setup-trivy` action instead of pulling a container image.

## 27. `no route to host` on 192.168.49.2:8443 after the codespace slept

**Symptom:** every `kubectl` command failed with `dial tcp 192.168.49.2:8443: connect: no route to host`.

**Cause:** minikube stops when the codespace stops. The ECR pull token in the `ecr-pull` secret had also expired (tokens last 12 hours).

**Fix:** `minikube start`, then recreated the `ecr-pull` secret. Argo CD and the app came back by themselves.

**Lesson:** a local cluster doesn't survive the machine sleeping; anything with a short-lived credential needs refreshing.

## 28. `aws login` redirected to 127.0.0.1 and failed

**Symptom:** after signing in, the browser went to `127.0.0.1:44085/oauth/callback?...` and showed "refused to connect".

**Cause:** plain `aws login` expects the browser and CLI on the same machine. The CLI was in the codespace, the browser on my Mac (same root cause as #25).

**Fix:** `aws login --remote`, which shows a code to paste back into the terminal instead of redirecting.
=======

## 29. Grafana: `lookup loki.monitoring.svc: no such host`

**Symptom:** the Loki data source was added to Grafana, but every query failed with `dial tcp: lookup loki.monitoring.svc on 10.96.0.10:53: no such host`.

**Cause:** Loki and Alloy had never actually been installed. Grafana was pointing at a Service that didn't exist. (`helm list -n monitoring` showed only `kube-prom`.)

**Fix:** dry-ran both charts with `helm template` to validate the values, then installed Loki (chart 7.3.0) and Alloy (chart 1.13.1).

**Lesson:** check the thing exists (`helm list`, `kubectl get svc`) before debugging how you connect to it. A DNS "no such host" inside a cluster usually means the Service name or namespace is wrong, or the Service isn't there at all.

## 30. Every log line appeared twice in Grafana

**Symptom:** each log line showed up twice in Loki, with identical timestamps.

**Narrowing it down:**
1. `kubectl -n uptime logs deploy/api` showed each line **once**, so the app was fine and the duplication was in the pipeline.
2. `kubectl -n monitoring get pods | grep alloy` showed **2 Alloy pods**.

**Cause:** `loki.source.kubernetes` reads logs through the Kubernetes API, so *each* Alloy pod collected from *every* pod in the cluster, and Loki received everything twice.

**Fix:** run Alloy as a single-replica Deployment (`controller.type: deployment`, `replicas: 1`). New lines now appear once; lines received before the fix stay duplicated.

**Lesson:** compare the source with the pipeline to find where duplication starts. Know whether a collector works per node or cluster-wide before scaling it.

## 31. Deploy workflow failed instantly; GitHub showed the file path instead of its name
 
**Symptom:** the Deploy run failed in 0 seconds with no logs, and the Actions list named it `.github/workflows/deploy.yml` instead of "Deploy".
 
**Cause:** `paths-ignore:` was indented at the same level as `push:`, so GitHub read it as an event, which is invalid. It was still valid YAML, so a YAML parse check passed.
 
**Fix:** indented `paths-ignore` under `push:` (same level as `branches:`).
 
**Lesson:** valid YAML isn't the same as a valid workflow. Use `actionlint` to check workflow rules. If a run shows the file path instead of the workflow name, the workflow file itself is broken.
 
 ## 32. Browser logins from the codespace fail with "localhost refused to connect"

**Symptom:** after signing in to Claude Code (`claude`), the browser went to `localhost:34101/callback?code=...` and showed `ERR_CONNECTION_REFUSED`. The same thing happened earlier with `aws login` (#28).

**Cause:** these tools start a small callback server *inside the codespace* and redirect the browser to `localhost` to hand over the login code. My browser runs on my Mac, so `localhost` pointed at the Mac, where nothing was listening.

**Fix:** either use the tool's remote/paste-code option (`aws login --remote`), or copy the full callback URL from the browser and send it to the codespace myself:
`curl "http://localhost:<port>/callback?code=..."` in a second codespace terminal. The code is single-use and short-lived, so do it straight away.

**Lesson:** third time this pattern has come up (#25, #28, #32). With a remote dev environment, always ask *which machine* "localhost" refers to. Also: never share screenshots of `callback?code=` URLs.

## 33. AI-DLC installer let the agent edit any file without asking

**Symptom:** installing AI-DLC 2.11.0 for Claude Code created `.claude/settings.json` with the permission `Edit(/**)`: the agent could create or change *any* file in the repo without asking, including `gitops/`, `helm/`, `infra/` and `.github/workflows/`. The installer also added hooks that run on every tool call, and a Stop hook that keeps the agent working through a workflow on its own.

**Why it matters:** this repo deploys through GitOps. An unreviewed edit to `gitops/` or `helm/` would reach the cluster as soon as it was pushed and merged, and an edit to `.github/workflows/` could change the pipeline itself.

**What happened:** I reviewed the dry-run and the full `settings.json` before applying anything. The agent then tried to narrow the permission, but AI-DLC's own `PreToolUse` hook blocked it: the agent isn't allowed to edit its own enforcement files. It also correctly refused to bypass the guard with `sed`.

**Fix:** I made the change myself, replacing `Edit(/**)` with `Edit(/aidlc/**)` and `Edit(/docs/aidlc/**)`. The agent can now update AI-DLC's own docs freely, but every edit to code, infrastructure, GitOps config or workflows asks me first. Checked with `aidlc doctor`. Claude Code's auto mode is also off, so every command needs my approval.

**Follow-up:** `aidlc update` or `aidlc config` may restore `Edit(/**)`. After either, check with `grep -n '"Edit(' .claude/settings.json`.

**Lesson:** review the permissions any AI tooling installs before using it, keep humans in control of the agent's guardrails, and match the agent's freedom to the blast radius of the repo. In a GitOps repo, an unreviewed edit is effectively an unreviewed deploy.
<<<<<<< HEAD

## 34. IP was hardcoded by the agent

My home IP was hardcoded in infra/envs/prod/main.tf and committed to the public repo. Dev correctly used a variable from gitignored tfvars, but prod had the literal value. Found by: the AI-DLC agent during its reverse-engineering scan. Fix: prod now uses var.http_allowed_cidr; I accepted that the old value stays in Git history (low risk, prod never applied). Lesson: a pre-commit secret/IP scan (e.g. gitleaks) would have caught it, so add one to CI.
=======

## 35. Custom Grafana dashboard missing after rebuilding on a new machine

**Symptom:** after rebuilding the local platform on a new laptop, Grafana showed all the built-in Kubernetes dashboards but not **Uptime Monitor**.

**Cause:** the dashboard JSON was in the repo (`monitoring/dashboards/uptime-monitor.json`), but I had originally imported it by hand through the Grafana UI. A fresh Grafana had no way of knowing about it, so the setup wasn't fully reproducible.

**Fix:** loaded it as a ConfigMap with the label `grafana_dashboard=1`. kube-prometheus-stack's Grafana sidecar watches for that label and provisions the dashboard automatically. Added it to the runbook's fresh-setup steps.

**Lesson:** anything set up by clicking in a UI is lost on rebuild. If it isn't in Git or a documented command, it doesn't really exist. Rebuilding on a new machine is a cheap way to find these gaps.

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