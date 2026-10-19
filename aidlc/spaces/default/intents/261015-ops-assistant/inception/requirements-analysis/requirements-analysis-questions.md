# Requirements Analysis Questions: ops assistant

Your intent (`docs/aidlc/inception/intent.md`) already settles the non-negotiable rules and the success test on the bad-image-tag game day. These questions cover what it leaves open. Write the letter of your choice after each `[Answer]:` tag, or your own words for X.

## Question 1: Which environment must the first version investigate?
Context: the observability tools the assistant would read (Prometheus, Loki, Argo CD) exist only on local minikube. The AWS dev server has the Kubernetes API and Helm history, but no metrics or logs stack.

A. Minikube only (where the game day ran and every data source exists)
B. Minikube first, with AWS dev as a later, separate step
C. Both minikube and AWS dev from the start (on AWS it works with only the Kubernetes API, Helm and Git)
X. Other (please specify)

[Answer]: A

## Question 2: How does an investigation start?
Context: on the game day no alert fired, so an alert-triggered assistant would not have started by itself.

A. On demand only: I run a command (for example `ops-assistant investigate --namespace uptime`)
B. On demand, plus automatically when Alertmanager fires an alert (webhook)
C. On demand, plus a scheduled health sweep (for example every 15 minutes) that investigates anything unhealthy
D. Automatic only (alert webhook and/or schedule)
X. Other (please specify)

[Answer]: A

## Question 3: Where does the assistant run?

A. As a command-line tool on my machine / codespace, using my existing kubeconfig, but through a read-only identity
B. As a workload inside the cluster (a Deployment or Job with its own read-only ServiceAccount)
C. Command-line tool first; packaged for in-cluster later
X. Other (please specify)

[Answer]: X. A, but as an MCP server, not a standalone CLI. The ops MCP server runs locally in my codespace and Claude Code is the client that calls its tools. It talks to the minikube cluster through a dedicated read-only ServiceAccount (get/list/watch only, no access to Secrets) via its own kubeconfig, not my admin kubeconfig. Running in-cluster is out of scope for v1.

## Question 4: Which AI service should it use?
Context: whatever runs the model receives the redacted evidence, so this decides where incident data goes.

A. Claude through the Anthropic API (API key from an environment variable)
B. Claude through Amazon Bedrock in eu-west-2 (data stays inside your AWS account; uses your AWS credentials)
C. Make it configurable between A and B
X. Other (please specify)

[Answer]: X. None inside the server. The MCP server makes no AI calls and needs no API key; it only returns redacted, read-only evidence to its client. The AI is the Claude Code session I’m already using (my Claude plan), so incident data only goes where that session already sends it. Redaction happens inside each tool before anything is returned. A standalone mode calling Bedrock or the Anthropic API is out of scope for v1

## Question 5: How far should it go with the fix?
Context: your rule says every fix goes through a pull request that a human reviews and merges. Since Q3/Q4 make the MCP server a read-only evidence source, the fix is made outside it; this decides by whom and how far. (Reframed after your Q3/Q4 answers.)

A. The Claude Code session opens a draft PR itself (new branch, `gh pr create --draft`) with the evidence in the PR description; the MCP server stays read-only with no Git or GitHub write access; I review and merge
B. The Claude Code session prepares the branch and commit locally; I push and open the PR myself
C. The MCP server only provides evidence; the session describes the fix (diff text in its report) and I make the change
X. Other (please specify)

[Answer]: B

## Question 6: What kinds of incident must the first version handle?
Context: the success test covers one scenario. A wider set needs more tools and more test scenarios.

A. Only the bad-image-tag class (ImagePullBackOff / ErrImagePull, including the shared-image CronJob impact)
B. Common pod failures: image pull errors, CrashLoopBackOff, OOMKilled, Pending (unschedulable), failed readiness, failed CronJob runs
C. B, plus app-level symptoms read from metrics and logs (for example sites reported down, database unreachable)
D. Anything: it investigates open-endedly with whatever the tools show
X. Other (please specify)

[Answer]: A

## Question 7: How should we prove it works?
Context: the success test needs a repeatable check. A live game day is realistic but slow; recorded evidence makes a fast automated test.

A. Recorded fixtures: capture the game day's pods, events, metrics and Git data once, and run the assistant against them in an automated test (CI-friendly)
B. Live: rerun the bad-image-tag game day on minikube and judge the assistant's report by hand
C. Both: recorded fixtures in CI, plus a live game-day run before calling it done
X. Other (please specify)

[Answer]: C

## Question 8: What performance limits should the MCP tools meet?
Context: with the AI running in your Claude Code session (Q4), there is no per-call API bill; what the server controls is how fast each tool answers and how much text it returns (large outputs use up the session's context). (Reframed after your Q3/Q4 answers.)

A. Each tool answers within 5 seconds and returns at most ~10 KB (truncated with a note when larger); a full bad-image-tag investigation finishes within 5 minutes
B. Each tool answers within 10 seconds and returns at most ~25 KB; a full investigation finishes within 10 minutes
C. Only the end-to-end target: a full investigation finishes within 10 minutes; no per-tool limits
X. Other (please specify)

[Answer]: A

## Question 9: Are the detection gaps from the game day in scope?
Context: the scan found why no alert fired. `site_up` keeps reporting the last stored check however old it is, and there is no alert for failed checker runs or ImagePullBackOff. The incident review lists these as open follow-ups.

A. Out of scope: the assistant only investigates; alert fixes are separate work
B. In scope as fixes the assistant should be able to propose (as PRs), but not build them now
C. In scope: fix the alerting gaps as part of this work, so an alert-triggered assistant would actually start
X. Other (please specify)

[Answer]: B

## Question 11 (follow-up): What exactly does the CI fixture test check?
Context: your answers combine recorded fixtures in CI (Q7) with the AI living in your Claude Code session (Q4). CI has no Claude Code session, so a CI test cannot judge the AI's conclusion; it can check that the tools return the right evidence, redacted. (Added because Q4 and Q7 together leave this open.)

A. CI checks the tools only: against the recorded fixtures, each tool returns the evidence needed to name the cause (ImagePullBackOff on the new tag, the checker CronJob on the same image, the values-gitops.yaml change from PR #34), within the size limit, with every secret redacted. The AI's conclusion (cause, hidden impact, revert PR #34) is judged in the live game-day run
B. A, plus a scripted replay I run by hand: Claude Code against the fixtures (no live cluster), with a written checklist for the conclusion
X. Other (please specify)

[Answer]: A

## Question 10 (follow-up): Where does the "recent deploys" evidence come from?
Context: the success test requires naming PR #34 as the cause. The local Git history in your codespace already carries the PR numbers in squash-merge titles (for example `... (#34)`), so it may be enough; the GitHub API adds PR descriptions, authors and review state, but needs a token. (Added after your Q3/Q4 answers made the server a local, read-only evidence source.)

A. Local Git only: the server reads the repo's history (`git log` / `git show` on the deployed files), plus Argo CD's sync history from the cluster; no GitHub token
B. Local Git plus the GitHub API, read-only (a fine-grained token with read-only access to this repo's pull requests and contents)
X. Other (please specify)

[Answer]: A
