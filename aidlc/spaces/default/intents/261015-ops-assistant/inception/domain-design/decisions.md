# Architecture Decisions: ops assistant MCP server

Intent: `ops-assistant` · Stage: Domain Design · Date: 2026-10-16

These ADRs record the component-boundary choices behind `components.md`. Each one notes its security implications, as the Inception rules require. Requirement IDs refer to `requirements.md`; `[Qn]` refers to `domain-design-questions.md`.

---

## ADR-001: Image-pull diagnosis is deterministic server logic

- **Context:** Two requirements need judgement on the evidence. The report must tell a missing tag from expired `ecr-pull` credentials (FR2.5), and "tag never existed" from "deleted by the ECR 5-image lifecycle policy" (FR2.6). CI has no Claude Code session (requirements Q11), so judgement left to the AI can be tested only in the live run.
- **Decision:** A dedicated `ImagePullDiagnosis` component classifies:
  - the pull-error kind: `not_found`, `unauthorized` or `other`;
  - the tag history: `never_existed`, `likely_deleted_by_lifecycle` or `undetermined`.

  It works from reader records, and returns the classification with the evidence references it used. The session reports it and may disagree, giving its reasons [Q1].
- **Consequences:**
  - (+) The classification is unit-tested in CI on the game-day fixture and its variants.
  - (+) It is repeatable, and every conclusion cites its evidence.
  - (−) The rules are heuristics without registry access, so "undetermined" must be a first-class outcome. New incident classes need new code rather than just prompting.
  - (security) It reads only reader records and calls nothing external, so it adds no access surface.
- **Alternatives rejected:**
  - *Session-only reasoning:* not CI-testable, and less repeatable between runs.
  - *Server hints only, with the session concluding:* splits one judgement across two places. The tests would cover the hints but not the conclusion the operator reads.

## ADR-002: One evidence reader per source

- **Context:** There are five sources: the Kubernetes API, Prometheus, Loki, the Argo CD CRDs and local Git. They differ in access rule (RBAC verbs, GET-only HTTP, a git allow-list), failure mode, timeout and fixture format. NFR6 requires each to degrade on its own.
- **Decision:** There are five readers, `KubernetesReader`, `PrometheusReader`, `LokiReader`, `ArgoCdReader` and `GitReader` [Q2]. Each has a live backend and a fixture backend.
- **Consequences:**
  - (+) Per-source failure handling and tests, and a narrow access rule per reader.
  - (+) The NFR1.3 GET-only test and the NFR13 git allow-list test each sit on exactly one component.
  - (−) There are more modules, and composite tools must call several readers (handled by ToolCatalog).
  - (security) Each reader holds only its own access: the HTTP readers cannot reach the Kubernetes API, and GitReader cannot make HTTP calls beyond its single `ls-remote`.
- **Alternatives rejected:**
  - *Grouping by access path* (ClusterReader, ObservabilityReader): mixes Prometheus and Loki failure handling and query languages.
  - *Grouping by question* (WorkloadState, Telemetry, DeployHistory): mixes access rules within one component, which weakens the per-source security tests.

## ADR-003: A mandatory EvidencePipeline is the only response path; Redactor is a separate engine

- **Context:** Every response must be redacted (FR7.1), and redacted before truncation (FR7.7). It must carry an evidence header and a redaction count (FR8.1, FR7.4) and fit in 10 KB (NFR3). A single missed code path would leak a secret into the AI session, which breaks a non-negotiable rule.
- **Decision:**
  - Tool handlers return structured evidence records, never text.
  - `OpsMcpServer` converts results into MCP responses only through `EvidencePipeline`.
  - The pipeline runs a fixed order: redact (with `Redactor`), then order (unhealthy first, then recent), then truncate to 10 KB, then add the header [Q3].
  - `Redactor` is its own component, because the call log and the fixture recorder use the same engine.
- **Consequences:**
  - (+) "Nothing bypasses redaction" becomes a structural property of one adapter and is testable: every tool, including error and empty results, is checked through the same path.
  - (+) The redaction rules have one implementation for three uses.
  - (−) Handlers cannot hand-format output; formatting choices live in the pipeline.
  - (security) This is the main control for "secrets never reach the AI". Combined with the no-Secrets RBAC (NFR1), it gives two independent layers.
- **Alternatives rejected:**
  - *Each reader calls the redactor:* every new reader or tool is another chance to forget.
  - *Redaction in readers and shaping in a formatter:* splits the redact-then-truncate ordering across components, and FR7.7 becomes a convention rather than a structure.

## ADR-004: Fixtures are captured by a separate FixtureRecorder through the same readers and Redactor

- **Context:** CI needs recorded game-day evidence (NFR10). The repo is public, so fixtures must pass the same redaction before they are committed (NFR10.2). The server must stay free of writes.
- **Decision:** `FixtureRecorder` is a hand-run script, not an MCP tool. It calls the live readers, redacts everything with `Redactor`, derives the scenario variants, and writes `FixtureSet` files under `tests/` [Q4].
- **Consequences:**
  - (+) The fixtures are realistic, and redacted by the very code under test.
  - (+) The server has no file-writing tool.
  - (−) Recording needs a live game day, or a minikube reproduction, whenever the fixtures change.
  - (security) The recorder uses the same read-only identity. It writes only to `tests/`, and the result reaches `main` only through a reviewed PR and the CI leak scan.
- **Alternatives rejected:**
  - *A record mode inside the server:* gives the server a write path, and records whatever an investigation happened to ask for, not a complete scenario.
  - *Hand-written fixtures:* drift from real API shapes, and leaves the leak scan as the only guard.

## ADR-005: Fine-grained tools plus one overview tool

- **Context:** An investigation has 5 minutes end to end (NFR4) and 10 KB per tool (NFR3). Fine tools give precise evidence; too many calls cost time and context.
- **Decision:** `ToolCatalog` exposes one tool per question:
  - `list_pods`, `describe_pod`, `list_workloads`, `find_image_users`, `get_events`, `get_logs`;
  - `query_loki`, `query_prometheus`, `get_alerts`;
  - `get_argocd_app`, `git_history`, `diagnose_image_pull`;
  - plus `namespace_overview`, the recommended first call [Q5].

  The overview returns unhealthy pods, non-ready workloads, recent Warning events and the Argo CD sync/health state within 10 KB.
- **Consequences:**
  - (+) The first call usually points straight at the failing workloads; follow-up calls are targeted.
  - (+) Each tool is small and testable.
  - (−) There are 13 tools to describe and keep consistent, and the overview duplicates some reader composition.
  - (security) No tool writes. Every tool, including the overview, passes the EvidencePipeline.
- **Alternatives rejected:**
  - *Fine-grained tools only:* more calls before the session sees the shape of the incident.
  - *A few broad tools:* larger outputs that hit the 10 KB cap and get truncated, and less precise evidence references.

## ADR-006: The investigation entry point is an MCP prompt; the guide and settings template ship with it

- **Context:** FR1.6 needs an entry point that sets the report format (FR9), the "MCP tools only" rule (FR11.3) and the fix-preparation limits (FR10). Its form was open (OQ3).
- **Decision:** `InvestigationGuide` serves an MCP prompt from the server (for example `/mcp__ops__investigate`), versioned with the tool names it references [Q6]. The same component owns the operator setup guide and the `.claude/settings.local.json` template for FR11.1 and FR11.2.
- **Consequences:**
  - (+) The prompt can never cite a tool that does not exist, and server and prompt are released together.
  - (+) The operator gets the instructions with the tools.
  - (−) Changing the wording means changing the server package.
  - (security) The prompt tells the session to stay within the tools, but it is guidance, not enforcement. The guide states that the server identity is the hard guarantee (FR11.4).
- **Alternatives rejected:**
  - *A project skill in `.claude/`:* lives apart from the tools, so it can drift. It also sits in the AI-DLC-managed directory.
  - *Both a prompt and a skill:* two copies of the same instructions.

## ADR-007: A separate top-level package `ops_mcp/` that never imports `app/`

- **Context:** The repo's `app/` package is the Uptime Monitor, the workload being observed. The assistant must not be coupled to it, but should reuse the repo's lint, tests and CI.
- **Decision:** All components live in `ops_mcp/`, with tests in `tests/ops_mcp/`. There are no imports from `app/`. The package uses the existing `pytest`, `ruff` and CI workflow [Q7].
- **Consequences:**
  - (+) There is a clear boundary between the observer and the observed, and the existing app is unchanged.
  - (+) One toolchain.
  - (−) Shared dependencies (for example the Kubernetes client and the MCP SDK) are added to the repo's dev and runtime requirements, which Infrastructure Design will settle.
  - (security) The assistant's dependencies are not shipped in the app image, so the observed workload's attack surface does not grow.
- **Alternatives rejected:**
  - *A subpackage in `app/`:* couples the assistant to the app's release and image.
  - *A separate project directory with its own CI job:* a second toolchain to maintain for one small package.

## ADR-008: Startup is gated by a fail-closed StartupGuard

- **Context:** "The agent can only READ the cluster" is non-negotiable. A misconfigured kubeconfig, such as the operator's admin context, would silently give the server write and Secret access (NFR1.2, FR1.3).
- **Decision:** `StartupGuard` resolves only the dedicated kubeconfig setting. It runs SelfSubjectAccessReview and SelfSubjectRulesReview, the only write-shaped calls the server makes, and refuses to serve on any excess permission, naming it. Missing read permissions are reported as degraded sources, not as fatal.
- **Consequences:**
  - (+) A wrong identity is caught before any evidence is read.
  - (+) The check is testable with an admin identity and a read-only one.
  - (−) Start-up needs API access; if minikube is down, the server does not start (and says why).
  - (security) This is a second layer behind RBAC: even if the manifests were later loosened, the server would refuse to run.
- **Alternatives rejected:**
  - *Trusting the RBAC manifests alone:* a wrong kubeconfig bypasses them.
  - *Checking permissions lazily on each call:* the first call could already be the dangerous one.
