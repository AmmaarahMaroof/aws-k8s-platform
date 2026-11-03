# Architecture Decisions: ops assistant MCP server

Intent: `ops-assistant` · Stage: Domain Design · Date: 2026-10-25

These ADRs record the component-boundary choices behind `components.md`. Each one notes its security implications, as the Inception rules require. Requirement IDs refer to `requirements.md`; `[Qn]` refers to `domain-design-questions.md`; `[gate]` marks a decision the operator made at the Domain Design approval gate on 2026-10-25.

---

## ADR-001: Image-pull diagnosis is deterministic server logic

- **Context:** Two requirements need judgement on the evidence. The report must tell a missing tag from expired `ecr-pull` credentials (FR2.5), and "tag never existed" from "deleted by the ECR 5-image lifecycle policy" (FR2.6). CI has no Claude Code session (requirements Q11), so judgement left to the AI can be tested only in the live run.
- **Decision:** A dedicated `ImagePullDiagnosis` component classifies:
  - the pull-error kind: `not_found`, `unauthorized` or `other`;
  - the tag history, by one heuristic [gate]: `likely_deleted_by_lifecycle` if the tag is the full SHA of a first-parent commit on origin/main, otherwise `never_existed`.

  It is a pure function. `ToolCatalog` makes the reader calls and passes the records in, and the diagnosis calls no reader [gate]. It returns the classification, labelled as a heuristic with its reason, plus the evidence references it used. The session reports it and may disagree, giving its reasons [Q1].
- **Consequences:**
  - (+) The classification is unit-tested in CI on the game-day fixture and its variants, with no readers involved.
  - (+) It is repeatable, and every conclusion cites its evidence.
  - (+) It needs only the first-parent SHA list from an existing git shape. No workflow file is read and no builds are counted.
  - (−) It is a heuristic without registry access. A mainline SHA that CI never built (deploy skipped by path filter, or the workflow not running) is still classified `likely_deleted_by_lifecycle`, so the reason is always shown. New incident classes need new code rather than just prompting.
  - (security) It reads only the records it is given and calls nothing, so it adds no access surface.
- **Alternatives rejected:**
  - *Session-only reasoning:* not CI-testable, and less repeatable between runs.
  - *Server hints only, with the session concluding:* splits one judgement across two places. The tests would cover the hints but not the conclusion the operator reads.
  - *Counting CI-built commits after the tag:* needs every commit's full changed-path list and `deploy.yml` as it was at each commit. That means extra git shapes reading files at past commits, for a count that would still be an estimate.
  - *A three-way result with `undetermined`:* the operator chose a binary heuristic with a stated reason over an outcome that defers the judgement.
  - *The diagnosis calling the readers itself:* mixes I/O into the judgement, so the tests would need readers or mocks.

## ADR-002: One evidence reader per source; git through read-only plumbing with fixed argv shapes

- **Context:** There are five sources: the Kubernetes API, Prometheus, Loki, the Argo CD CRDs and local Git. They differ in access rule, failure mode, timeout and fixture format. NFR6 requires each to degrade on its own. Git is the one source reached by starting a process, and git can write or run programs in surprising places: `git status` refreshes `.git/index`, and repo config can run fsmonitor, external diff, textconv, hook and signature programs. Caller-supplied refs can also be parsed as options. A subcommand allow-list plus a deny-list of flags does not close those paths.
- **Decision:**
  - There are five readers: `KubernetesReader`, `PrometheusReader`, `LokiReader`, `ArgoCdReader` and `GitReader` [Q2]. Each uses a backend interface with a live and a fixture implementation (ADR-011).
  - `GitReader` uses only four read-only plumbing subcommands: `rev-parse`, `log`, `show` and `rev-list` [gate]. It has nine fixed argv shapes, G1 to G9, listed in `components.md` > GitReader, and the git fixture transcript holds only those shapes. Refs are validated as hex SHAs or fixed names, `--end-of-options` is used where git supports it, and paths always follow `--`.
  - `status`, `diff`, `cat-file`, `for-each-ref`, `config`, `ls-remote` and `fetch` are dropped, and no file is read at a past commit. The stale-clone warning compares HEAD with origin/main as recorded at the last fetch, and never contacts the remote [gate].
  - The FR6.6 check compares the Argo CD target branch with the local branch only. The repo URL is not compared: this is a single-repo setup, and the operator recorded the comparison as out of scope [gate].
  - The live runner uses a scrubbed environment: `GIT_OPTIONAL_LOCKS=0`, no system or global config, no terminal prompt, no `GIT_EXTERNAL_DIFF`. It also passes `-c core.fsmonitor=false -c core.hooksPath=/dev/null -c diff.external= -c log.showSignature=false -c protocol.ext.allow=never`, plus `--no-ext-diff --no-textconv` on `log` and `show` [gate].
  - Tests: the runner fails on any other subcommand, an argv outside the fixed shapes, an unvalidated or option-like ref, or an unscrubbed environment. A further test shows that `.git/index`, the refs and the reflogs are unchanged after every git-backed tool runs.
- **Consequences:**
  - (+) Per-source failure handling and tests, and a narrow access rule per reader.
  - (+) Git's read-only guarantee is an allow-list of argv shapes, not a deny-list of flags, and needs no network at all.
  - (+) The NFR1.3 GET-only test and the NFR13 git test each sit on one reader, with the transport re-checking in ReaderBackends.
  - (−) There are more modules, and composite tools must call several readers (handled by ToolCatalog).
  - (−) The freshness warning is only as current as the operator's last `git fetch`. It says so, and suggests fetching.
  - (security) Each reader holds only its own access. GitReader makes no network connection and cannot run a repo-configured program.
- **Alternatives rejected:**
  - *Grouping by access path* (ClusterReader, ObservabilityReader): mixes Prometheus and Loki failure handling and query languages.
  - *Grouping by question* (WorkloadState, Telemetry, DeployHistory): mixes access rules within one component, which weakens the per-source security tests.
  - *The earlier git allow-list* (`log`, `show`, `diff`, `rev-parse`, `ls-remote`, `cat-file`, `for-each-ref`, `status`, with a deny-list of writing flags): `status` writes the index, `diff`, `cat-file` and `show` options can invoke helpers, and `ls-remote` uses whatever transport the clone is configured with.
  - *Keeping `ls-remote` for a live freshness check:* a network call to the remote, with its configured transport, for a warning that the reflog answers well enough.
  - *Adding shapes to read the origin URL or files at past commits* (`show <sha>:<path>`, reading `.git/config`): more surface for features the operator narrowed instead (ADR-001, FR6.6).

## ADR-003: A mandatory EvidencePipeline is the only exit; Redactor is a separate engine

- **Context:** Every response must be redacted (FR7.1), and redacted before truncation (FR7.7). It must carry an evidence header and a redaction count (FR8.1, FR7.4) and fit in 10 KB (NFR3). A single missed code path would leak a secret into the AI session, which breaks a non-negotiable rule. Errors are such paths too: timeout, validation and unknown-tool errors, uncaught exceptions, stderr and library logging can all carry data.
- **Decision:**
  - Tool handlers return structured evidence records, never text.
  - Every outgoing message, errors and the rendered investigation prompt included, is a structured record that `OpsMcpServer` passes through `EvidencePipeline` [gate]. Nothing is exempt. The prompt's namespace argument is validated as a DNS-1123 label (at most 63 characters) and rejected otherwise [gate]. The stdio adapter has a catch-all that turns any uncaught exception into an error record and sends it through the same pipeline.
  - Fail closed [gate]: if `EvidencePipeline` or `Redactor` itself raises, the adapter sends a constant, pre-built error frame with no variable text (at most a tool name from ToolCatalog's closed list). It records the failure in CallLog through Redactor, and records nothing if that fails too. A test makes Redactor raise and checks the frame.
  - stdout carries only MCP protocol frames, written by the transport alone. stderr carries only fixed, non-data startup messages. Python logging has no stream handler [gate].
  - The pipeline runs a fixed order: redact (with `Redactor`), then order (unhealthy first, then recent), then truncate to 10 KB, then add the header [Q3].
  - `Redactor` is its own component, because the call log, the fixture recorder and the leak scan use the same engine.
  - A test fails if anything is written outside that path [gate]. It runs every tool and every error path on fixtures, captures file descriptors 1 and 2, and checks that stdout holds only frames built from pipeline output (or, on the Redactor-raises path only, the one constant fail-closed frame, which is defined and written only in the transport module) and that stderr holds nothing after start-up. A static check also fails on any `print` or direct stream write outside the transport module.
- **Consequences:**
  - (+) "Nothing bypasses redaction" is a structural property of one adapter with one catch-all, and is tested end to end.
  - (+) The redaction rules have one implementation for four uses.
  - (−) Handlers cannot hand-format output, and exception detail reaches the client only after redaction. Debugging leans on the call log.
  - (security) This is the main control for "secrets never reach the AI". Combined with the no-Secrets RBAC (NFR1), it gives two independent layers.
- **Alternatives rejected:**
  - *Each reader calls the redactor:* every new reader or tool is another chance to forget.
  - *Redaction in readers and shaping in a formatter:* splits the redact-then-truncate ordering across components, and FR7.7 becomes a convention rather than a structure.
  - *Pipeline for tool results only, with errors formatted in the adapter:* error messages echo arguments, source responses and exception text, so they are the likeliest leak.
  - *Exempting the prompt as static text:* the prompt takes an argument, so caller text could leave the server unredacted.
  - *Retrying the pipeline, or falling back to raw error text, when it fails:* a recursive failure or an unredacted leak at the one moment redaction is known to be broken.

## ADR-004: Fixtures are captured by a guarded FixtureRecorder through the same session, readers and Redactor

- **Context:** CI needs recorded game-day evidence (NFR10). The repo is public, so fixtures must pass the same redaction before they are committed (NFR10.2). The server must stay free of writes. The recorder reads the live cluster, so it needs the same identity guarantee as the server. CI also needs variants, such as a lifecycle-deleted tag, that cannot be produced safely in the real registry.
- **Decision:**
  - `FixtureRecorder` is a hand-run script, not an MCP tool [Q4].
  - It first runs `StartupGuard`, and refuses to run with an identity that is not read-only. It reaches the cluster only through the resulting `ClusterSession` and the live backends from `ReaderBackends` [gate].
  - It redacts everything with `Redactor`, and writes `FixtureSet` files in the per-source formats under `tests/ops_mcp/fixtures/recorded/`.
  - Variants are produced by editing a copy of a recorded set, never by deleting real images [gate]. The lifecycle-deleted variant rewrites the bad tag to the full SHA of an older first-parent commit on origin/main, taken from the recorded transcript.
  - Seeded-secret samples are separate, hand-made, obviously fake, and live under `tests/ops_mcp/fixtures/seeded/` [gate]. Only that tree is exempt from the leak scan, and there the scan requires the fake marker.
- **Consequences:**
  - (+) The fixtures are realistic, and redacted by the very code under test.
  - (+) The lifecycle variant needs no synthetic commits, because the heuristic only checks whether the tag is a first-parent SHA.
  - (+) The recorder cannot run with an admin kubeconfig, so the read-only guarantee holds for recording too.
  - (+) The server has no file-writing tool.
  - (−) Recording needs a live game day, or a minikube reproduction, whenever the fixtures change.
  - (−) Edited variants are synthetic. Their edits are recorded in the set manifest so a reader can tell recorded from derived.
  - (security) The recorder writes only to `tests/`, and the result reaches `main` only through a reviewed PR and the CI leak scan (`FixtureLeakScan`).
- **Alternatives rejected:**
  - *A record mode inside the server:* gives the server a write path, and records whatever an investigation happened to ask for, not a complete scenario.
  - *Hand-written fixtures:* drift from real API shapes, and leaves the leak scan as the only guard.
  - *A recorder with its own client:* the read-only guarantee would depend on the operator passing the right kubeconfig.
  - *Producing the lifecycle variant by pushing and expiring real images:* changes the shared registry for a test, and can expire an image a real deployment still pins.

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

## ADR-006: The investigation entry point is an MCP prompt; the operator kit ships with it

- **Context:** FR1.6 needs an entry point that sets the report format (FR9), the "MCP tools only" rule (FR11.3) and the fix-preparation limits (FR10). Its form was open (OQ3). The operator also needs the session settings template (FR11.1, FR11.2) and the read-only identity manifests and kubeconfig procedure (FR1.4).
- **Decision:** `InvestigationGuide` provides an MCP prompt from the server (for example `/mcp__ops__investigate`), versioned with the tool names it references [Q6]. Its namespace argument is validated, and the rendered prompt goes through `EvidencePipeline` (ADR-003). The same component owns the operator setup guide, the `.claude/settings.local.json` template, and the `ReadOnlyIdentityKit` (RBAC manifests, including the service-proxy grant, and the kubeconfig procedure).
- **Consequences:**
  - (+) The prompt can never cite a tool that does not exist, and server, prompt and identity kit are released together.
  - (+) The operator gets the instructions and the identity with the tools.
  - (−) Changing the wording means changing the server package.
  - (security) The prompt tells the session to stay within the tools, but it is guidance, not enforcement. The guide states that the server identity is the hard guarantee (FR11.4). The RBAC manifests reach the cluster only through a reviewed PR.
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

## ADR-008: A fail-closed StartupGuard is the only creator of the shared ClusterSession

- **Context:** "The agent can only READ the cluster" is non-negotiable. A misconfigured kubeconfig, such as the operator's admin context, would silently give the server write and Secret access (NFR1.2, FR1.3). The check only helps if every cluster request uses the identity it verified: a reader building its own client from another config would void it.
- **Decision:**
  - `StartupGuard` resolves only the dedicated kubeconfig setting. It runs SelfSubjectAccessReview and SelfSubjectRulesReview, the only write-shaped calls the server makes, and refuses on any excess permission, naming it.
  - Only after the check passes does it create a `ClusterSession`, the single holder of the verified API client and the Prometheus and Loki proxy paths [gate].
  - `ClusterSession`'s constructor is private to `StartupGuard`. Readers receive only backends built from that session and never build their own clients [gate].
  - A static test fails if any module other than `StartupGuard` loads a kubeconfig or constructs an API client.
  - Missing read permissions are recorded on the session as degraded sources, which ToolCatalog reads (through ReaderBackends) and reports per source [gate]. The server and FixtureRecorder both start through this guard.
- **Consequences:**
  - (+) A wrong identity is caught before any evidence is read, and no code path can reach the cluster with an unverified identity.
  - (+) The check is testable with an admin identity and a read-only one, and the degraded-sources report has a consumer.
  - (−) Start-up needs API access; if minikube is down, the server does not start (and says so with a fixed message).
  - (security) This is a second layer behind RBAC: even if the manifests were later loosened, the server would refuse to run.
- **Alternatives rejected:**
  - *Trusting the RBAC manifests alone:* a wrong kubeconfig bypasses them.
  - *Checking permissions lazily on each call:* the first call could already be the dangerous one.
  - *A guard that only checks, with readers loading the kubeconfig themselves:* the verified identity and the one in use can differ.

## ADR-009: Prometheus and Loki are reached through the Kubernetes API-server service proxy

- **Context:** The server must query Prometheus and Loki in the `monitoring` namespace read-only (NFR1.3), with only get/list/watch-style access (NFR1). The mechanism was open (OQ1). Creating a port-forward is a write verb (`create` on `pods/portforward`), which the identity must not hold. The codespace cannot reach ClusterIP addresses directly.
- **Decision:** Both are reached through the API server's service proxy, `/api/v1/namespaces/monitoring/services/<service>:<port>/proxy/<path>`, using the same `ClusterSession` [gate]. The identity holds `get` on `services/proxy` in `monitoring`, with `resourceNames` limited to the Prometheus and Loki services. The proxy passes a request through only for the verb the identity holds, so `get` alone allows only HTTP GET. The readers' path allow-lists (`/api/v1/query`, `/api/v1/query_range`, `/api/v1/alerts`; `/loki/api/v1/query_range`, `/loki/api/v1/labels`) still apply. The exact `resourceNames` strings are pinned and tested with `kubectl auth can-i` in Infrastructure Design.
- **Consequences:**
  - (+) One connection, one identity and one self-check cover all evidence sources, and NFR13's network rule shrinks to "the API server only".
  - (+) GET-only is enforced twice: by RBAC on the proxy, and by the readers' allow-lists.
  - (−) Queries go through the API server, adding a hop and some latency within the 5-second budget.
  - (−) Any GET path on those two services is reachable at the RBAC layer, so the readers' path allow-list is the control that keeps queries to the listed endpoints. Prometheus and Loki admin and delete APIs need POST, PUT or DELETE, which RBAC refuses.
  - (security) No port-forward and no operator credentials. The grant is named and limited to two services, and it appears in the NFR1 `can-i` checks.
- **Alternatives rejected:**
  - *An operator-started `kubectl port-forward`:* depends on the operator's admin context running alongside the investigation. The deny rules (FR11.1) block it in the session, and it gives the server a localhost endpoint whose identity it cannot verify.
  - *Exposing the services (NodePort or Ingress) and calling them directly:* changes the monitoring stack, and Loki runs with `auth_enabled: false`, so it would be open to anything that reaches the port.

## ADR-010: The Redactor protects identifiers by field position and scans joined text

- **Context:** Redaction and the identifiers an investigation needs can collide on real data. A 40-character commit SHA looks like an AWS secret key, and an image tag can be a SHA. FR7.6 protects label values while FR7.5 and NFR2 need public IPs and secrets scrubbed from them. PEM blocks and base64 blobs can span several log lines, so scanning line by line misses them.
- **Decision** [gate]:
  - Protection is by field position, not by pattern. Each evidence record declares its protected identifier fields (image references and tags, commit SHAs, PR numbers, object kinds, names, namespaces and UIDs, event reasons, metric names, label keys), and those values are never scanned.
  - Every other field is scanned. Inside label values the secret and public-IP rules win.
  - Multi-line values are joined and scanned as one text.
  - The AWS secret-key rule needs an AWS key name beside the value, or at least one character outside lowercase hex, so a commit SHA in free text is not mistaken for a key.
  - The seeded test set includes a SHA beside an AWS secret key and checks that the SHA survives and the key is redacted.
- **Consequences:**
  - (+) The game-day identifiers (`gameday-does-not-exist`, the PR #34 commit, `(#34)`) survive by construction, and the conflict between FR7.5 and FR7.6 is settled explicitly.
  - (+) Multi-line secrets are caught.
  - (−) Every record type must declare its protected fields. A new field defaults to scanned, which errs toward redacting.
  - (−) A secret placed inside a protected field, such as an image reference with embedded credentials, is not redacted. This is accepted, because those fields come from typed API fields rather than free text.
  - (security) The default is to redact. Protection is explicit, narrow and testable.
- **Alternatives rejected:**
  - *A protected-token pattern rule applied after redaction* (the earlier design): the order and precedence were undefined, and patterns cannot tell a SHA from a key.
  - *Per-line redaction:* misses PEM and base64 blocks that span lines.
  - *Protecting label values entirely:* a public IP or secret in a label would leak (FR7.5).

## ADR-011: Each reader has a live/fixture backend, chosen at one selection point

- **Context:** CI replays recorded evidence with no cluster (NFR10), and NFR2 needs seeded samples to flow through every tool output type. Replay needs a defined format for each source, and a defined way to swap sources, that the server itself cannot trigger.
- **Decision:**
  - `ReaderBackends` defines one backend interface per reader, with a live and a fixture implementation, and is the only place a mode is chosen [gate]: `live(session, repo_path)` or `fixture(set_dir)`.
  - The `OpsMcpServer` adapter receives its backends and `ToolCatalog` through its constructor. Only the production entry point runs `StartupGuard` and calls `live`. The test harness constructs the same adapter with `fixture(set_dir)` backends, so the adapter-level tests (stdout/stderr capture, Redactor-raises frame, catch-all) run without a cluster. The server has no way to enter fixture mode on its own.
  - Each source has one fixture format: API list JSON and log text for Kubernetes, `{path, params, body}` response lists for Prometheus and Loki, an Application list for Argo CD, and an argv-keyed transcript for git [gate].
  - The live HTTP backends also enforce GET-only, and the live git runner re-checks the argv shape.
- **Consequences:**
  - (+) Every reader, and the diagnosis, runs unchanged on fixtures, so the CI tests exercise the real reader and pipeline code.
  - (+) The server cannot be switched to fixtures, and fixture runs cannot open a connection or start a process.
  - (−) The git transcript is keyed by exact argv, so changing an argv shape means re-recording or editing transcripts.
  - (−) Shape G8 carries `--since` and `--until` values, so a replay matches only if a tool passes the same window text it was recorded with. Functional Design will normalise window arguments for git calls, or key the transcript by shape plus normalised arguments.
  - (security) Transport-level checks sit beside the readers' own allow-lists, so a reader bug alone cannot widen access.
- **Alternatives rejected:**
  - *Mocking clients in each test:* tests would not exercise the shared transport checks, and each test would invent its own data shape.
  - *A fixture flag in the server's settings:* a misconfiguration could make an investigation report on stale recorded data as if it were live.
  - *Replaying git from a restored repository bundle:* needs `git clone` (a write) in the test harness, and still runs repo config.
