# Requirements: ops assistant (read-only incident investigation MCP server)

Intent: `ops-assistant` · Scope: classic · Depth: Standard · Date: 2026-10-16

Source key: `[desc]` = the initial request and `docs/aidlc/inception/intent.md`; `[Q<n>]` = an answered question in `requirements-analysis-questions.md`; `[incident]` = `docs/incidents/2026-10-13-bad-image-tag.md`; `[codekb:<file>]` = the reverse-engineering knowledge base in `aidlc/spaces/default/codekb/aws-k8s-platform/`. Ideation was skipped at the operator's request, so the intent document stands in for the ideation artifacts.

## 1. Intent Analysis

**Problem.** During the 13 Oct 2026 game day, a merged change set the image tag to one that does not exist. The checker CronJob shares that image, so uptime checks stopped for about 19 minutes, and none of the alerts fired. The operator found the cause by watching screens and querying four tools by hand (kubectl, Prometheus, Loki, Git/Argo CD) [desc] [incident].

**Goal.** Make that investigation fast, evidence-based and safe. A local **MCP server** gives the operator's existing Claude Code session read-only, redacted access to the evidence: pods, events, logs, metrics, workloads and recent deploys. The session reasons over that evidence, explains the likely cause with citations, and prepares a fix on a local branch for the operator to push and open as a PR [desc] [Q3] [Q4] [Q5].

**Request type.** A new component (enhancement) in a brownfield platform repo. It is read-only towards the existing system: it changes nothing in the cluster or in the app [codekb:business-overview.md].

**Shape.**
- A single user (the repo's sole operator).
- Runs locally in the codespace.
- One target cluster (minikube), one namespace of interest (`uptime`), plus the `monitoring` and `argocd` namespaces as evidence sources [Q1] [codekb:architecture.md].

**Success, as the operator defined it** [desc]. On the bad-image-tag scenario, an investigation:
1. names the cause: an image tag that does not exist (ImagePullBackOff), introduced by PR #34;
2. names the hidden impact: the checker CronJob shares the image, so uptime checks stopped;
3. proposes the right fix: revert PR #34;
4. shows its evidence (events, metrics, the Git change), not just a conclusion.

## 2. Functional Requirements

### FR1: MCP server and registration
- **FR1.1** A local MCP server (stdio transport) runs in the codespace and is registered for Claude Code in the project's MCP configuration. Claude Code is its only client [Q3].
- **FR1.2** The server makes no calls to any AI model and needs no AI API key. Its only outputs are tool results returned to the client [Q4].
- **FR1.3** The server connects to the cluster only through its own kubeconfig. The path comes from a dedicated environment variable or setting, never the default `~/.kube/config` and never the operator's admin context. If no dedicated kubeconfig is configured, the server refuses to start and says why [Q3].
- **FR1.4** The repo provides the read-only identity as reviewed manifests applied through Git: a ServiceAccount, Role/ClusterRole and bindings, plus a documented way to generate the dedicated kubeconfig. Like every change, they go through a PR [Q3] [desc] [codekb:code-quality-assessment.md: there are no RBAC objects to reuse].
- **FR1.5** An investigation starts on demand only. The operator asks in Claude Code (for example, "investigate the uptime namespace"). There is no webhook, schedule or background process [Q2].
- **FR1.6** The server provides an investigation entry point (an MCP prompt, or equivalent project instruction) that tells the session to gather evidence with the tools and to report in the format of FR9 [desc].

### FR2: Pod and workload state
- **FR2.1** A tool lists the pods in a namespace with phase, readiness, restart counts, owner (ReplicaSet/Job → Deployment/CronJob), and each container's image reference and waiting/terminated reason and message (for example `ImagePullBackOff`, `ErrImagePull`, with the registry's "not found" message) [desc] [incident].
- **FR2.2** A tool describes one pod: containers and init containers, images, conditions, state history, node, and the pod's recent events. Environment variable **values** are never included; only names and the source kind (literal, ConfigMap, Secret) are shown [desc].
- **FR2.3** A tool lists Deployments, ReplicaSets, CronJobs and Jobs in a namespace with their image references, rollout status (desired/updated/ready/available), last schedule time and last successful run (for CronJobs), and failed/active Job counts [desc] [incident].
- **FR2.4** Given an image reference (or tag), the workload tool reports every workload in the namespace that uses it. This is how the investigation finds that the API Deployment and the checker CronJob share the bad tag [desc: hidden impact] [codekb:code-structure.md: every place the image tag is set].
- **FR2.5** The pod and event tools return the **exact** image-pull error text from the kubelet or registry, unshortened (within NFR3, the message is never truncated). The report can then tell apart:
  - "manifest unknown / not found", where the tag is missing;
  - "unauthorized / no basic auth credentials / denied", where the `ecr-pull` credentials are expired or invalid.

  The report must name which one applies.
- **FR2.6** When the cause is a missing tag, the investigation distinguishes **"tag never existed"** from **"tag deleted by the ECR lifecycle policy"** (ECR keeps only the 5 newest images). It uses only evidence available without AWS access:
  - **Previously deployed?** Has the same image reference run successfully before? Sources: earlier ReplicaSets with Ready pods, Argo CD sync history, or Git history of the deployed values files.
  - **Built by CI?** Does the tag match the CI tagging scheme (a commit SHA on `main` built by the pipeline), and how many newer images CI has pushed since? More than 5 means the lifecycle policy has likely expired it.

  The report labels the conclusion with this evidence. Where neither signal settles it, the report says "undetermined without registry access". **Pass/fail:**
  - The game-day fixture (`gameday-does-not-exist`, never deployed, not a commit SHA) is classified "never existed".
  - A fixture variant whose tag is an old CI-built SHA, previously Running, with 6 or more newer builds, is classified "likely deleted by lifecycle policy" [operator feedback at the gate] [codekb:code-quality-assessment.md: ECR keeps 5 images].
- **FR2.7** Partial and after-the-fact failures are covered:
  - **Partial failure:** during a rolling update where old pods still serve, the workload tool reports both the old ReplicaSet (Ready) and the new one (failing). The report states the impact as "partial: old version still serving".
  - **After a revert:** once the failing pods are gone, the tools still return what remains, namely ReplicaSet image history, Argo CD sync history and Git history. The report says the live failure evidence is no longer present.

### FR3: Events
- **FR3.1** A tool returns Kubernetes Events for a namespace, filterable by involved object and by time window. Each event carries type, reason, message, count, first/last timestamps and object reference [desc] [incident: image-pull errors are events, not logs].
- **FR3.2** When there are no events in the window, the tool says "no events in <window>". This is distinct from a failed read. The note also reminds the session that Kubernetes keeps events for about one hour by default [corner: empty vs failed].

### FR4: Logs
- **FR4.1** A tool returns container logs from the Kubernetes API for a pod/container, current or previous instance, limited by tail lines and time window [desc].
- **FR4.2** A tool runs a LogQL query against Loki in the cluster for a time window and returns matching lines with timestamps and labels [desc] [codekb:api-documentation.md §7].
- **FR4.3** When a container never started, the log tools say "container has not started; no logs exist" rather than returning an empty success. On the game day the bad pods had no logs at all [incident] [corner: empty vs failed].

### FR5: Metrics and alerts
- **FR5.1** A tool runs a PromQL instant query or range query against Prometheus in the cluster, for an explicit time or window, and returns the series with labels and values [desc].
- **FR5.2** A tool returns current alerts (`ALERTS`), with state (pending/firing), labels and active-since time [desc] [incident: `KubePodNotReady` was only Pending].
- **FR5.3** Query results that exceed the size limit (NFR3) are reduced, for example by aggregating or keeping the most recent points. The response says what was reduced [Q8].

### FR6: Recent deploys
- **FR6.1** A tool reads the Argo CD Application resources from the cluster: sync status, health status, the current revision, and the sync history (revision, deployed-at time) [Q10] [codekb:architecture.md: GitOps release].
- **FR6.2** A tool reads the local Git history of the repository for the paths that define what is deployed (by default `helm/uptime-monitor/values-gitops.yaml` and `helm/uptime-monitor/`). It returns commits in a window with hash, time, author, subject (which carries the PR number in squash-merge titles, for example `(#34)`), and the diff of the deployed paths, size-limited [Q10] [desc].
- **FR6.3** The deploy tools link the Argo CD revision to the Git commit, so the session can state "the deployed revision `<sha>` is the commit from PR #N that changed `image.tag` from X to Y" [desc].
- **FR6.4** Git access is read-only. The server never runs a command that writes to the repository, its refs or its remote [Q5] [Q10].
- **FR6.5** Every Git tool response states **which commit was checked**: the local `HEAD` hash and branch. It also warns when the local clone is **behind `origin/main`**, with how many commits. The comparison uses the read-only `git ls-remote origin refs/heads/main` (this writes no refs; see NFR13). If the remote is unreachable, the tool compares against the local `origin/main` ref, says so, and gives the time of the last fetch [operator feedback at the gate].
- **FR6.6** If the Argo CD deployed revision is not in local Git history, the tool returns an explicit error: "revision `<sha>` not in local history; the clone may be stale (run `git fetch`)". It never returns an empty result. The tool also reports a mismatch when the Argo CD Application's source repo URL or target branch differs from the local clone's `origin` and branch.

### FR7: Redaction (applies to every tool)
- **FR7.1** Every tool redacts its output **inside the server, before returning it**. No raw output path bypasses redaction [Q4] [desc].
- **FR7.2** The server never reads Kubernetes Secret objects. RBAC also denies it (NFR1) [Q3].
- **FR7.3** Redaction covers at least:
  - credentials embedded in URLs and connection strings (`scheme://user:password@host`), for example the app's `DATABASE_URL`;
  - `password=`, `passwd`, `secret`, `token`, `api_key` style key/value pairs;
  - bearer tokens and JWTs;
  - AWS access key IDs and secret keys;
  - PEM private keys;
  - docker registry auth blobs (the `ecr-pull` dockerconfigjson);
  - the base64 forms of these where they appear in manifests.

  Each redaction is replaced by a marker such as `[REDACTED:<kind>]` [desc] [codekb:code-quality-assessment.md: the DB password can appear in error logs].
- **FR7.4** Each tool response reports how many values were redacted, so the session and the operator can tell redaction happened [desc: evidence].
- **FR7.5** Real public IP addresses in tool outputs are replaced by `[REDACTED:public-ip]`. Private ranges (10.x, 172.16–31.x, 192.168.x, 127.x) are kept as evidence [operator feedback at the gate: public IP is a required redaction test sample] [memory:project.md ## Forbidden].
- **FR7.6** Redaction never removes the identifiers an investigation needs as evidence:
  - image references and tags;
  - commit hashes and PR numbers;
  - Kubernetes object names, namespaces and labels;
  - event reasons;
  - metric names and label values.

  **Pass/fail:** on the game-day fixtures, `gameday-does-not-exist`, the PR #34 commit hash and `(#34)` all survive redaction unchanged.
- **FR7.7** Redaction runs **before** truncation and size reduction (FR5.3, NFR3), so a truncated output can never cut a secret in half and leave a fragment unredacted.

### FR8: Evidence references
- **FR8.1** Every tool response carries an evidence header: the tool name, the source (Kubernetes API / Prometheus / Loki / Argo CD / Git), the exact query or object reference, the time window, and the time it was retrieved [desc: every conclusion backed by evidence].
- **FR8.2** Evidence items carry stable references, such as an event's object/reason/last timestamp, a metric's series labels and timestamp, or a commit hash. The report can then cite them exactly [desc].

### FR9: Investigation report (produced by the Claude Code session, guided by FR1.6)
- **FR9.1** The report states:
  - **Likely cause**, with a confidence level;
  - **Impact**: visible impact, plus hidden impact on any other workload sharing the failing component;
  - **Timeline** of the key events;
  - **Evidence**: every claim cites at least one FR8 evidence reference;
  - **Proposed fix**;
  - **Recommended follow-ups**.
  [desc]
- **FR9.2** A claim without supporting evidence is labelled as a hypothesis, never stated as a finding [desc].
- **FR9.3** Recommended follow-ups may include detection improvements, such as an alert on stale uptime checks, an alert on pods stuck waiting, or a CI image-tag check. These are written as proposals the operator can turn into PRs. This work does not build them [Q9].

### FR10: Fix preparation
- **FR10.1** When the fix is a code or config change (for the reference incident, a revert of PR #34's commit), the Claude Code session prepares a local branch and commit. The commit message references the investigation and the evidence [Q5].
- **FR10.2** The session does not push and does not open the PR. The operator reviews the local commit, pushes it and opens the PR, which a human reviews and merges [Q5] [desc].
- **FR10.3** The MCP server has no tool that writes to Git, GitHub or the cluster. Fix preparation uses the session's own Git access, and the operator approves each command by hand (FR11.2) [Q5] [Q3].

### FR11: Investigation session constraints (the Claude Code side)
- **FR11.1** During an investigation, the Claude Code session reaches the cluster **only through the MCP server**.
  - The repo documents, and provides a copyable template for, deny rules in the operator's `.claude/settings.local.json` that block direct cluster and cloud tools: `Bash(kubectl *)`, `Bash(helm *)`, `Bash(aws *)` and `Bash(minikube *)`. They stay in place for the whole investigation.
  - **Pass/fail:** with the template applied, a session request to run `kubectl get pods` (or `helm`, `aws`, `minikube`) is refused by Claude Code, while the MCP tools still answer [operator feedback at the gate].
- **FR11.2** During an investigation, **every command the session runs needs the operator's manual approval**. No Bash command is auto-approved, and auto/bypass permission modes are not used. This covers the Git commands of fix preparation (FR10). **Pass/fail:** the documented investigation setup sets no `allow` rule for Bash, and the investigation guide tells the operator to use the default (ask) permission mode [operator feedback at the gate].
- **FR11.3** The investigation entry point (FR1.6) tells the session to gather cluster evidence only through the MCP tools. If a tool fails, the session reports the gap rather than trying another route.
- **FR11.4** The deny rules and manual approval constrain the session but do not make it a security boundary. The hard guarantee remains the server's read-only identity (NFR1) and its redaction (FR7). The investigation guide states this plainly.

## 3. Non-Functional Requirements

### Security
- **NFR1: Read-only cluster identity.**
  - The server's identity is a dedicated ServiceAccount whose RBAC grants only `get`, `list` and `watch`. It covers only the resources the tools need: pods, `pods/log`, events, deployments, replicasets, jobs, cronjobs, and Argo CD `applications`.
  - On top of that, it holds exactly the read access for Prometheus and Loki that design picks under NFR1.3. Design must add that entry to this list by name (for example `get` on `services/proxy` with `resourceNames` limited to the two services).
  - It grants nothing on `secrets`, and no `create`/`update`/`patch`/`delete`, `pods/exec`, `pods/attach` or `pods/portforward`.
  - **Pass/fail:**
    - `kubectl auth can-i --list --as=system:serviceaccount:<ns>:<sa>` shows only the listed verbs and resources.
    - `can-i get secrets`, `can-i list secrets`, `can-i delete pods`, `can-i create pods/exec` and `can-i patch deployments` all return `no`.
  - [Q3] [desc] [operator feedback at the gate]
- **NFR1.2: Self-check at startup.** On startup the server checks its own permissions with SelfSubjectAccessReview / SelfSubjectRulesReview. These review requests are the **only** write-shaped API calls the server ever makes. Kubernetes allows them to every authenticated identity by default, so they need no RBAC grant. The server **refuses to serve** if its identity can read Secrets or perform any create, update, patch, delete or exec action. **Pass/fail:** started with an admin kubeconfig, the server exits with a clear error naming the excess permission [Q3] [desc].
- **NFR1.3: Metrics and logs access is read-only.** However Prometheus and Loki are reached (the mechanism is design question OQ1), the access is read-only:
  - The server only calls their query endpoints with HTTP `GET`: Prometheus `/api/v1/query`, `/api/v1/query_range` and `/api/v1/alerts`; Loki `/loki/api/v1/query_range` and `/loki/api/v1/labels`.
  - It never calls an admin, write or delete endpoint.
  - It never uses the operator's admin credentials from inside the server.

  **Pass/fail:**
  - A unit test asserts that the HTTP client only issues `GET` requests to those paths, and fails on any other method or path.
  - Whatever mechanism design chooses keeps NFR1's `can-i` checks passing [operator feedback at the gate].
- **NFR2: Zero secret leakage, tested against realistic samples.**
  - **Required samples.** The redaction test suite seeds these realistic samples, at minimum:
    1. a Postgres connection string with a password (`postgresql://uptime:<pw>@db:5432/uptime`), in a log line and in an exception traceback;
    2. a Secret-style env var (`DB_PASSWORD=<value>`, and the same in a pod-spec-like YAML block);
    3. a bearer token (`Authorization: Bearer <jwt>`);
    4. a public IP address.
  - **Further samples.** The other FR7.3 kinds are also seeded: `password=` / `api_key=` pairs, AWS keys, a PEM block, a dockerconfigjson auth string, and the base64 form of a connection string.
  - **Every tool output type is covered:** pod and workload descriptions, events, Kubernetes logs, Loki results, Prometheus labels, Argo CD Application, and Git diff.
  - **Pass/fail (in CI):**
    - No tool output contains any seeded value or its base64 form.
    - Each appears as `[REDACTED:<kind>]`.
    - The FR7.4 count matches the number seeded.
    - The FR7.6 identifiers survive.
  - [desc] [Q11] [operator feedback at the gate]- **NFR13: No outbound calls.**
  - The server opens network connections only to the Kubernetes API server, and to Prometheus and Loki by the read-only path of NFR1.3.
  - Its only other connection is the single read-only `git ls-remote` call of FR6.5 to the repo's `origin`, which writes no refs.
  - It starts no processes except `git` with a fixed allow-list of read-only subcommands: `log`, `show`, `diff`, `rev-parse`, `ls-remote`, `cat-file`, `for-each-ref` and `status`.
  - **Pass/fail:** a unit test fails if the Git runner is asked for any subcommand outside the allow-list (for example `fetch`, `push`, `commit`, `checkout`, `reset` or `config`), or for a flag that writes (for example `--output`). A test with network access blocked shows that the tools make no other outbound connection [Q4] [operator feedback at the gate].

### Performance
- **NFR3: Per-tool limits.**
  - Each tool returns within **5 seconds** and at most **10 KB** of text.
  - When the result is larger, it is truncated or aggregated, with a note naming what was dropped and how to narrow the query.
  - Truncation keeps the most useful items first: unhealthy items first (failing pods, Warning events, non-ready workloads), then the most recent. The FR8 evidence header and the FR7.4 redaction count are never dropped.
  - **Pass/fail:** on the game-day fixtures padded with 200 healthy pods and 500 Normal events, the pod, workload and event tools still return the `ImagePullBackOff` pods and both workloads sharing the bad tag within 10 KB [Q8].
- **NFR4: End-to-end time.** A full bad-image-tag investigation, from the operator's request to a report that meets FR9, finishes within **5 minutes** on the live game-day run [Q8].
- **NFR5: Timeout behaviour.** A data source that does not answer within the tool's budget yields a clear timeout error naming the source and the query, within the 5-second limit, not a hang [Q8] [corner: unreachable source].

### Reliability and error handling
- **NFR6: Degrade per source.**
  - If one evidence source is down or unreachable (for example Prometheus not running, Loki not installed, Argo CD absent), its tools return an error naming that source and why. The other tools keep working.
  - The report lists which sources it could not read [construction rules: error handling] [corner: briefly unreachable store].
- **NFR7: No silent failure.** Every tool distinguishes "no data" (empty, with the window queried) from "could not read" (error with cause) [incident: silent failure] [corner: empty vs failed].
- **NFR8: Explicit time.** Tools take an explicit time window and an optional "as of" time. They never assume the wall clock, so recorded fixtures replay deterministically [Q7] [Q11].

### Observability (of the server itself)
- **NFR9: Call log.**
  - The server writes a local log line for every tool call: tool, arguments with values redacted, duration, bytes returned, number of redactions, and outcome (ok, empty, error or timeout).
  - It writes nothing to the cluster.
  - This gives the operator a health and error-rate record for the server [operation rules: health and error metric].

### Testing and quality
- **NFR10: CI fixture tests.**
  - **Fixtures.** Recorded fixtures of the game day go under `tests/`:
    - pods, events and workloads;
    - the Argo CD Application;
    - Prometheus series and Loki results;
    - the Git commits for PR #34 and #35;
    - the FR2.5 to FR2.7 variants: auth failure, a tag deleted by the lifecycle policy, partial failure, and after revert.
  - **What CI runs.** CI runs every tool against these fixtures with no cluster. It asserts that:
    - the evidence needed for all four success criteria is returned;
    - each response carries the FR8 evidence header and the FR7.4 redaction count;
    - output is within NFR3's size limit;
    - output is fully redacted (NFR2).
  - The fixtures expect **PR #34** as the introducing change [Q7] [Q11] [operator feedback at the gate].
- **NFR10.2: Fixtures are redacted before they are committed.** The repo is public, so recorded fixtures pass through the **same** redaction code as tool output before they are written to `tests/`. A CI check scans every committed fixture file and fails the build if it contains:
  - a connection string with a password;
  - a `*PASSWORD*=` / `*SECRET*=` / `*TOKEN*=` value that is not `[REDACTED:…]`;
  - a bearer token or JWT;
  - a PEM block;
  - an AWS key;
  - a public IP address.

  Only the NFR2 test file's deliberately seeded fake samples are exempt, and they are clearly fake [operator feedback at the gate].
- **NFR11: Live acceptance run.**
  - Before the work is called done, the operator reruns the bad-image-tag game day on minikube. Claude Code runs with the FR11 deny rules applied, using only this server's tools.
  - The run makes a new PR, so the report must name **whichever PR or commit introduced the bad tag in that run**, not PR #34. Only the recorded fixtures expect PR #34.
  - The operator judges the report with this checklist; every line must pass:
    1. **Cause:** names a non-existent image tag (ImagePullBackOff / ErrImagePull), classified per FR2.5–FR2.6, and the PR or commit of this run that introduced it.
    2. **Hidden impact:** names the checker CronJob as sharing the image, with uptime checks stopped since the break.
    3. **Fix:** proposes reverting that run's change, and prepares it as a local branch and commit per FR10.
    4. **Evidence:** every claim in the cause, impact and fix sections cites at least one FR8 evidence reference (event, metric series, workload or commit).
    5. **Confidence:** the cause carries a confidence of `high`, `medium` or `low`, with a one-line reason. Any unsupported claim is labelled as a hypothesis.
    6. **Constraints:** the session ran no `kubectl`, `helm`, `aws` or `minikube` command, and the server log (NFR9) shows only read calls.
    7. **Time:** the report arrives within NFR4's 5 minutes.
  - [Q7] [Q11] [desc] [operator feedback at the gate]- **NFR12: Coverage and lint.** New code has at least **80% line coverage** in CI (the classic-scope floor). It passes the repo's existing `ruff` configuration, and the existing test suite stays green [org.md ## Testing Posture] [codekb:code-quality-assessment.md: coverage is not measured today, so measurement must be added].

## 4. Constraints

- **C1** The cluster must be read only. No apply, delete, scale or exec, through the server or through its identity. During an investigation, the Claude Code session reaches the cluster only through the server (FR11) [desc] [operator feedback at the gate].
- **C2** Every fix goes through Git as a PR that a human reviews and merges. The assistant never pushes or merges [desc] [Q5].
- **C3** Secrets, passwords and connection strings never leave the server unredacted [desc].
- **C4** Every conclusion shows its evidence [desc].
- **C5** The only AI is the operator's Claude Code session on their existing Claude plan. There is no separate model API or key [Q4].
- **C6** v1 targets local minikube only. The AWS dev server has no metrics or logs stack [Q1] [codekb:business-overview.md: Environments].
- **C7** The repo's GitOps safety settings stay in force. Agent auto-edits are restricted to AI-DLC docs, and changes to deploy configuration go through PRs (commit `71982bf`, `git log`).
- **C8** Changes to the repo go through trunk-based short-lived branches and squash-merge to `main` [org.md ## Way of Working].

## 5. Assumptions

- **A1** The server is written in Python, the repo's existing language, with its existing `pytest` and `ruff` tooling, and uses the official MCP Python SDK. *Reason:* one language and one toolchain in the repo; design may revisit this [codekb:technology-stack.md].
- **A2** *(Confirmed by the operator at the gate. It is now a requirement in NFR10 and NFR11.)* The live acceptance run names whichever PR or commit introduced the bad tag in that run. Only the recorded fixtures expect PR #34.
- **A3** How Prometheus and Loki are reached is open (OQ1). Whichever path design picks must stay read-only (NFR1.3). *Reason:* the operator's rule allows only get/list/watch. Port-forward creation is a write verb, so it cannot be granted to the server's identity [Q3] [operator feedback at the gate].
- **A4** Kubernetes Events are kept for about one hour, so the live run happens within an hour of the break. The fixtures capture events at recording time [incident] [codekb:api-documentation.md §7: events are not collected into Loki].
- **A5** *(Replaced by FR11.2.)* Every session command, including the Git commands of fix preparation, is approved by hand.
- **A6** Argo CD is installed in the `argocd` namespace and its Application CRDs are readable through the Kubernetes API. The server does not use the Argo CD API server or its credentials [Q10] [codekb:component-inventory.md].

## 6. Out of Scope (v1)

- The AWS dev and prod environments [Q1].
- Running the server inside the cluster [Q3].
- Alert-triggered or scheduled investigations [Q2].
- Any AI call from the server, including a standalone mode using Amazon Bedrock or the Anthropic API [Q4].
- Pushing branches or opening PRs automatically [Q5].
- The GitHub API (PR descriptions, reviews) [Q10].
- Incident classes other than bad image tags (ImagePullBackOff/ErrImagePull, including shared-image impact): CrashLoopBackOff, OOMKilled, Pending, app-level symptoms. The tools are general, but only this class is specified and tested [Q6].
- Building the detection fixes from the incident review (the stale-check alert, the stuck-pod alert, the CI image-tag check, collecting events into Loki, an Alertmanager receiver). They are only proposed as follow-ups (FR9.3) [Q9].
- Checking image tag existence in ECR, which would need AWS credentials. The registry's "not found" pull message is the evidence [Q10] [incident].

## 7. Open Questions (for later stages)

- **OQ1 (design):** how the server reaches Prometheus and Loki (NFR1.3, A3). The options are the API-server service proxy with `resourceNames`, or an operator-started port-forward. Each has its own security and RBAC trade-offs. Whichever is chosen must be read-only (NFR1.3) and must be added to NFR1's RBAC list by name.
- **OQ2 (design):** where the ServiceAccount lives (`uptime` or a dedicated `ops-assistant` namespace), and how the kubeconfig token is issued and rotated (a short-lived `kubectl create token` versus a long-lived token Secret).
- **OQ3 (design):** the form of the investigation entry point (FR1.6): an MCP prompt served by the server, or a project-level Claude Code instruction/skill.
- **OQ4 (design):** the redaction approach and its false-positive policy, for example whether to redact all long high-entropy strings or only known patterns.

## Sources

- Initial description: `aidlc/spaces/default/intents/261015-ops-assistant/project-description.json` and `docs/aidlc/inception/intent.md` [desc]
- Answers: `requirements-analysis-questions.md` Q1 to Q11 [Q1]–[Q11]
- Operator feedback at the first approval gate (2026-10-16, Request Changes, recorded in the audit log) [operator feedback at the gate]- Reference incident: `docs/incidents/2026-10-13-bad-image-tag.md` [incident]
- Code knowledge base: `aidlc/spaces/default/codekb/aws-k8s-platform/`: `business-overview.md`, `architecture.md`, `code-structure.md`, `api-documentation.md`, `component-inventory.md`, `technology-stack.md`, `code-quality-assessment.md`
- Rules: `aidlc/spaces/default/memory/org.md` (Way of Working, Testing Posture), `project.md` (Forbidden), `phases/inception.md`, `phases/construction.md`, `phases/operation.md`
- Edge-condition sweep: `.claude/knowledge/aidlc-product-agent/corner-checklist.md`

## Assumptions & Open Questions

See §5 (Assumptions A1 to A6) and §7 (Open Questions OQ1 to OQ4). None blocks Domain Design.
