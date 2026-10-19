# Domain Design Questions: ops assistant MCP server

These questions decide how the read-only MCP server from `requirements.md` is split into building blocks: which pieces of code exist, what each owns, and how they call each other. Deployment shape and tech stack come later. Write the letter of your choice after each `[Answer]:` tag, or your own words for X.

## Question 1: Where does the image-pull diagnosis logic live?
Context: two requirements need judgement on the evidence. One must tell a missing tag from expired `ecr-pull` credentials (FR2.5). The other must tell "tag never existed" from "deleted by the ECR 5-image lifecycle policy" (FR2.6). CI cannot run your Claude Code session (Q11), so only logic inside the server can be tested in CI.

A. In the server: a deterministic diagnosis component classifies pull errors and tag history, and returns its classification with the evidence it used. The session reports it, and can disagree with stated reasons. The classification is CI-testable on fixtures
B. In the session only: the server returns raw evidence (exact error text, ReplicaSet and Git history), and Claude reasons it out. Only the live run tests it
C. Both: the server returns classification *hints* (for example `pull_error_kind: not_found | unauthorized | other`, `tag_seen_before: true/false`), and the session draws the conclusion
X. Other (please specify)

[Answer]: A

## Question 2: How should the evidence readers be split?
Context: there are five evidence sources. The Kubernetes API covers pods, workloads, events and logs. The others are Prometheus, Loki, the Argo CD Application CRDs (read through the Kubernetes API), and local Git.

A. One reader per source: KubernetesReader, PrometheusReader, LokiReader, ArgoCdReader, GitReader. Each has its own failure handling (NFR6), timeouts and tests
B. Grouped by access path: ClusterReader (Kubernetes API, including Argo CD CRDs), ObservabilityReader (Prometheus and Loki over HTTP), GitReader
C. Grouped by question: WorkloadState (pods, workloads, events), Telemetry (logs, metrics, alerts), DeployHistory (Argo CD and Git)
X. Other (please specify)

[Answer]: A

## Question 3: How is redaction and output shaping enforced?
Context: every tool's output must be redacted before it is returned (FR7.1), before truncation (FR7.7), and carry the evidence header and redaction count (FR8, FR7.4) within 10 KB (NFR3).

A. One mandatory output pipeline: tool handlers return structured evidence, never text. A single EvidencePipeline component redacts, then shapes and truncates, then adds the header, and is the only path to the MCP response. A tool cannot bypass it
B. Each reader calls a shared Redactor and formatter itself before returning
C. Redaction in the readers (closest to the data), and shaping/truncation in a shared response formatter
X. Other (please specify)

[Answer]: A

## Question 4: How are the CI fixtures recorded?
Context: fixtures must pass the same redaction as tool output before they are committed, because the repo is public (NFR10.2).

A. A separate FixtureRecorder component, a script run by hand during a game day. It calls the same readers and the same redaction pipeline, and writes the redacted results to `tests/`. It is not exposed as an MCP tool
B. A "record" mode built into the MCP server, which saves every tool response it returns during an investigation
C. Fixtures are hand-written from the game-day notes; only the CI leak scan (NFR10.2) guards them
X. Other (please specify)

[Answer]: A

## Question 5: How fine-grained should the MCP tool surface be?
Context: the session has to gather evidence within 5 minutes (NFR4), at up to 10 KB per tool (NFR3). Fewer, broader tools mean fewer calls; finer tools give more control.

A. Fine-grained tools, one per requirement: `list_pods`, `describe_pod`, `list_workloads`, `find_image_users`, `get_events`, `get_logs`, `query_loki`, `query_prometheus`, `get_alerts`, `get_argocd_app`, `git_history`
B. A: plus one overview tool (`namespace_overview`: unhealthy pods, workloads, recent Warning events and the Argo CD sync state in one call, within 10 KB) as the recommended first call
C. Only a few broad tools (overview, deploy history, telemetry query) with options
X. Other (please specify)

[Answer]: B

## Question 6: Where does the investigation entry point live?
Context: FR1.6 requires an entry point that tells the session how to investigate and report: the FR9 format, the FR11.3 "MCP tools only" rule, and the NFR11 checklist items. Design question OQ3 left its form open.

A. An MCP prompt served by the server (for example `/mcp__ops__investigate`), versioned with the tools it refers to
B. A project-level Claude Code skill or command in `.claude/` (outside the server)
C. Both: the server serves the prompt, and a short project doc points to it with the FR11 settings template
X. Other (please specify)

[Answer]: A

## Question 7: How does the new code sit next to the existing app?
Context: the repo's Python package `app/` is the Uptime Monitor. Its tests, `ruff` setup and CI already exist (`codekb/code-structure.md`).

A. A separate top-level package (for example `ops_mcp/`) with its own tests under `tests/ops_mcp/`. It never imports `app/`, and shares only the repo's lint, test tooling and CI
B. A subpackage inside `app/` (for example `app/ops/`)
C. A separate directory with its own project file and dependency set (for example `tools/ops-mcp/pyproject.toml`), and its own CI job
X. Other (please specify)

[Answer]: A
