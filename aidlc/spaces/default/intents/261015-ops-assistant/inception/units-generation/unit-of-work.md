# Units of Work: Ops Assistant MCP Server

The 17 Domain Design components are grouped into exactly three units, as the operator decided [Q1]. All three are build increments of one local stdio MCP server package, `ops_mcp/`, plus its tests and CI. None is deployed separately (Domain Design ADR-007) [assumption].

## Unit Index

| Unit ID | Directory | Name | Kind | Complexity | Deployment model |
|---|---|---|---|---|---|
| U1 | `u1-safe-core` | Safe core (walking skeleton) | service | L | Embedded in the single `ops_mcp/` stdio process |
| U2 | `u2-investigation` | Investigation | service | XL | Embedded in the same process; extends U1 |
| U3 | `u3-fixtures-ci` | Fixtures and CI | library | M | Hand-run recorder, a CI leak scan and a CI job in the same repo; nothing runs in the server process |

Kinds: U1 and U2 are `service` because together they are the deployed executable. U3 is `library` because its recorder and scan are repo tooling with no standalone runtime in the server, yet they carry real business rules (guarded capture, redaction before write, leak patterns). Those rules need Functional Design.

## U1: Safe core (walking skeleton)

**Purpose.** This is the smallest working server that proves the safety properties from the first build. A single read-only tool, `namespace_overview`, runs end to end on fixtures through the guard, the session, a reader, the pipeline and the transport. That makes the single-exit, redaction and stdout tests real from the start [Q1].

**Components owned.**

| Component | Scope in U1 |
|---|---|
| StartupGuard | Complete: dedicated kubeconfig only, permission self-check, fail closed, sole creator of ClusterSession |
| ClusterSession | Complete: verified read-only connection, GET-only, path allow-list |
| Redactor | Complete engine: positional protection, every FR7.3 kind, counts (ADR-010). U1 starts the Redactor's SeededSampleSet with the fakes its own tests plant (see Test data); U3 completes the set across every tool output type [Q7] |
| EvidencePipeline | Complete: redact, then order, then truncate to 10 KB, then add the header |
| OpsMcpServer + stdio transport | Adapter, complete except prompt content: single exit, catch-all, the constant fail-closed frame owned by the transport module, stdout protocol-only, per-call time budget, and the prompt-registration hook with DNS-1123 validation of the prompt's namespace argument. Rendered prompts go through EvidencePipeline like every other message. U2 supplies only the prompt content through the hook [Q8] |
| Production entry point (composition root) | Named module, not a component (review R-10). It is the only code that runs StartupGuard and `ReaderBackends.live`, then constructs the adapter with those backends and the ToolCatalog |
| ToolCatalog | Framework (registration, argument validation, explicit time window, no-data vs could-not-read, degraded-source answers) plus one tool: `namespace_overview` |
| CallLog | Complete: one redacted line per call, outcome, duration, bytes, redaction count |
| ReaderBackends | Minimal [Q2]: backend interface, `live(session, …)` reading only through ClusterSession, `fixture(set_dir)` with no connections, the one selection point, degraded-sources list. Only the Kubernetes backend exists |
| KubernetesReader | Minimal [Q2]: only what `namespace_overview` needs, namely namespaces, pods and their status (phase, readiness, restarts, waiting/terminated reasons, image refs). Never reads Secrets |
| Read-only identity kit (part of InvestigationGuide) | ServiceAccount and RBAC manifests only (FR1.4, NFR1). The rules cover every read the five U2 readers need, with no write verb and no `secrets` access, so that StartupGuard's self-check can pass against a real API server in U1. Manifest location is fixed in U1 Functional Design and confirmed at U1 plan approval [Q9] |
| CI workflow (repo tooling, not a component) | A new file, `.github/workflows/ops-assistant.yml`: pytest with coverage, then `ruff`, on `ops_mcp/` only. The existing `ci.yml` and `deploy.yml` are not edited [Q9] |

**Reduced `namespace_overview`.** In U1 the overview returns namespaces, pods and their status, with unhealthy pods first. U2 extends it to the full Domain Design shape: non-ready workloads, recent Warning events, Argo CD sync/health and the diagnosis line.

**Test data** [Q3] [Q7]. There are two fixture trees, and secrets live in only one of them.

- `tests/ops_mcp/fixtures/handwritten/`: a small hand-written evidence set (namespaces, pods, statuses) with obviously fake names and no secret-shaped values. It holds no passwords, connection strings, tokens, keys, PEM blocks or public IPs, so FixtureLeakScan covers it with no exemption.
- `tests/ops_mcp/fixtures/seeded/`: every fake secret in the repo, from U1 onwards, in the seeded layout with the fake marker. This is the one location, the one marker and the one leak-scan exemption (and later the one gitleaks allowlist path). U1 commits one sample of each FR7.3 kind plus a documentation-range public IP (`203.0.113.0/24`, which the Redactor treats as public). Tests that need a planted secret load it from here and insert it into the evidence under test; no test file contains a secret literal.

U3 adds recorded fixtures next to the hand-written set and completes the seeded set.

**Responsibilities delivered.** Read-only cluster connection gate, the redaction engine, evidence shaping and headers, the only exit to stdout, the call log, the tool framework that U2 adds tools to, the prompt-registration hook that U2 adds prompt content to, the read-only identity kit, and the first CI workflow.

**Implementation notes and constraints.**

- The adapter takes its backends and ToolCatalog through its constructor. Tests construct it with `ReaderBackends.fixture(set_dir)`; the server cannot enter fixture mode on its own (ADR-011).
- The live backend reads only through ClusterSession, so nothing reaches the cluster without passing StartupGuard [Q2].
- The interfaces U2 extends are fixed in U1 and must not change shape in U2: the reader backend interface, the ToolCatalog registration API, the prompt-registration hook, the evidence record types and the EvidencePipeline input [Q8].
- Automated U1 checks run on fixtures and a faked permission review only. The first live start-up and self-check against a real API server is the operator's manual check U1-A1 at the end of U1 [Q9].
- The agent never applies manifests or runs anything against a cluster. The operator applies the identity kit and runs U1-A1 [Q9].

### U1 tests

| # | Test | Proves |
|---|---|---|
| U1-T1 | StartupGuard fails closed when the dedicated kubeconfig variable is missing, or points at `~/.kube/config` | FR1.3 |
| U1-T2 | StartupGuard fails closed when the faked permission review shows any write verb or any `secrets` access, and passes on a read-only rule set. No ClusterSession exists after a failure | NFR1.2, ADR-008 |
| U1-T3 | ClusterSession rejects any non-GET method and any path outside its allow-list, including `secrets` | FR7.2, NFR1.3 (GET-only transport) |
| U1-T4 | Redactor replaces each seeded fake (loaded from `seeded/`) of every FR7.3 kind (connection string, `*PASSWORD*=`, bearer/JWT, AWS key, PEM, dockerconfigjson, base64 connection string) with `[REDACTED:<kind>]`, and reports a count equal to the number planted | FR7.3, FR7.4 |
| U1-T5 | Public IPs (the seeded `203.0.113.0/24` sample) are redacted and private ranges are kept; the FR7.6 identifiers (pod, image tag, commit SHA, namespace) survive | FR7.5, FR7.6 |
| U1-T6 | A seeded secret placed across the 10 KB truncation boundary leaves no fragment: redaction runs before truncation | FR7.7 |
| U1-T7 | EvidencePipeline orders unhealthy items first, truncates to ≤ 10 KB with a note naming what was dropped, and never drops the header or the redaction count | NFR3, FR8.1 |
| U1-T8 | Single exit: on fixtures, `namespace_overview` is driven through the happy path, an empty namespace, a timeout, an argument-validation error, an unknown tool and a handler exception. File descriptors 1 and 2 are captured; stdout holds only pipeline-built MCP frames and stderr holds nothing after start-up | FR7.1, ADR-003 |
| U1-T9 | Fail closed: with Redactor forced to raise, the client receives exactly the constant fail-closed frame, and CallLog records the failure or nothing | ADR-003 |
| U1-T10 | Static check: no `print`, `sys.stdout` or `sys.stderr` write exists outside the transport module | ADR-003 |
| U1-T11 | Only the production entry point calls StartupGuard and `ReaderBackends.live`; the adapter has no fixture switch | ADR-011, review R-10 |
| U1-T12 | `fixture(set_dir)` opens no network connection and starts no process (network blocked in the test) | ADR-011 |
| U1-T13 | A fake backend that stalls produces a timeout error record naming the source and query within the 5-second budget, not a hang | NFR5 |
| U1-T14 | A degraded Kubernetes backend yields a per-source error record; "no pods in window" is distinct from "could not read" | NFR6, NFR7 |
| U1-T15 | `namespace_overview` requires an explicit time window, reads no wall clock, and replays identically twice | NFR8 |
| U1-T16 | End to end on the hand-written fixture: `namespace_overview` returns the `ImagePullBackOff` pods first, with the evidence header, the redaction count and ≤ 10 KB | FR2.1 (status subset), FR8, NFR3 |
| U1-T17 | CallLog writes one line per call with redacted arguments, duration, bytes, redaction count and outcome, and writes nothing to stdout, stderr or the cluster | NFR9 |
| U1-T18 | The registered tool list contains no tool that writes to the cluster, Git or GitHub | FR10.3 |
| U1-T19 | CI gate in the new `.github/workflows/ops-assistant.yml`: ≥ 80% line coverage on new code, `ruff` passes on `ops_mcp/`, the existing suite stays green | NFR12 |
| U1-T20 | Prompt hook: a test prompt registered through the hook is rendered through EvidencePipeline (redacted, with header); a namespace argument that is not a DNS-1123 label is rejected before rendering | FR1.6 (mechanism), ADR-003 |
| U1-T21 | Identity kit manifest check: the Role/ClusterRole grants no write verb and no `secrets` access, and is bound only to the dedicated ServiceAccount | NFR1, FR1.4, FR7.2 |
| U1-T22 | Static check: `ops_mcp/` imports no AI or LLM client library and makes no outbound call other than the API server | FR1.2 |
| U1-T23 | The server starts only when the stdio client launches it, starts no thread, timer or child process after the call returns, and exits when stdin closes | FR1.5 |
| U1-T24 | Evidence references are stable: the same fixture and window give the same reference IDs on two runs, and every item in the response carries one | FR8.2 |
| U1-T25 | Leak hygiene: no file under `tests/ops_mcp/fixtures/handwritten/` and no test source file matches an FR7.3 pattern; only `seeded/` does, and every seeded file carries the fake marker | Q7, NFR10.2 (early) |
| U1-A1 | Manual, end of U1: the operator applies the identity kit to minikube and starts the server with the dedicated kubeconfig; StartupGuard's self-check passes, and `namespace_overview` answers live. With a write verb temporarily added to the role, start-up fails closed. The agent applies nothing | NFR1, NFR1.2, FR1.3, FR1.4 |

## U2: Investigation

**Purpose.** This unit gives the server everything an investigation needs: all five evidence sources, the deterministic image-pull diagnosis, the remaining tools and the operator kit [Q1].

**Components owned.**

| Component | Scope in U2 |
|---|---|
| KubernetesReader | Extends U1: workloads, events, container logs, full pod describe |
| ArgoCdReader | Complete |
| PrometheusReader | Complete (service proxy, GET-only) |
| LokiReader | Complete (service proxy, GET-only) |
| GitReader | Complete: nine fixed argv shapes G1 to G9, hardened runner, scrubbed environment, window normalisation (review R-09) |
| ReaderBackends | Extends U1: live and fixture backends for the four new readers |
| ImagePullDiagnosis | Complete: pure classification, including the FR2.6 heuristic |
| ToolCatalog | Adds `list_pods`, `describe_pod`, `list_workloads`, `find_image_users`, `get_events`, `get_logs`, `query_loki`, `query_prometheus`, `get_alerts`, `get_argocd_app`, `git_history`, `diagnose_image_pull`; extends `namespace_overview` to its full shape |
| InvestigationGuide | Prompt content registered through U1's prompt hook (U1 owns rendering through the pipeline and the DNS-1123 check [Q8]), operator guide, settings template with the FR11 deny rules. The read-only identity kit moved to U1 [Q9]; U2 may add read-only rules for its readers if Functional Design finds a gap, and U1-T21 must still pass |

**Test data** [Q7]. U2 extends U1's hand-written fixture set with fake Argo CD, Prometheus, Loki and git transcript data and the FR2.5 to FR2.7 variants, still with no secret-shaped values. Any planted secret a U2 test needs, such as a secret-looking env value for `describe_pod`, is added to `seeded/` and loaded from there. U3 later reruns the fixture-set-parameterised tests on recorded fixtures (see U3-T7).

**Implementation notes and constraints.**

- U2 starts only after U1 is merged [Q4].
- It adds readers and tools through U1's interfaces and does not reshape them.
- The prompt content plugs into U1's prompt hook; U2 does not change the adapter [Q8].

### U2 tests

| # | Test | Proves |
|---|---|---|
| U2-T1 | Each new reader returns its records from fixtures, with the evidence header and redaction count | FR2 to FR6, FR8 |
| U2-T2 | `find_image_users` reports both the API Deployment and the checker CronJob for the bad tag | FR2.4 |
| U2-T3 | Pod and event tools return the exact image-pull error text, never shortened | FR2.5 |
| U2-T4 | `diagnose_image_pull`: the `gameday-does-not-exist` tag is classified "never existed"; a full first-parent `origin/main` SHA is classified "likely deleted by lifecycle policy"; both carry the heuristic label and reason. The expired `ecr-pull` credentials case is told apart from a missing tag | FR2.5, FR2.6 |
| U2-T5 | The partial-failure and after-revert variants are classified correctly | FR2.7 |
| U2-T6 | `get_events` answers "no events in <window>" on an empty window, distinct from a failed read | FR3.2, NFR7 |
| U2-T7 | Log tools answer "container has not started; no logs exist" for a never-started container | FR4.3 |
| U2-T8 | Prometheus results larger than the limit are reduced and say what was reduced | FR5.3, NFR3 |
| U2-T9 | The Argo CD revision is linked to its git commit and PR; a revision missing from local history returns the explicit "clone may be stale" error; a branch mismatch is reported | FR6.3, FR6.6 |
| U2-T10 | Every git response states HEAD and branch and warns when the clone is behind `origin/main` | FR6.5 |
| U2-T11 | The git runner refuses every other subcommand, any argv outside G1 to G9, an unvalidated or option-like ref, and an unscrubbed environment | NFR13, FR6.4 |
| U2-T12 | `.git/index`, refs and reflogs are unchanged after every git-backed tool runs | FR6.4, NFR13 |
| U2-T13 | With the network blocked, no tool connects anywhere except the (faked) API server | NFR13 |
| U2-T14 | Git replays match whatever window text a tool passes (normalised `--since`/`--until`) | review R-09 |
| U2-T15 | With Prometheus, Loki or Argo CD down, its tools return a per-source error while the others answer | NFR6 |
| U2-T16 | Padded fixture (200 healthy pods, 500 Normal events): the pod, workload and event tools still return the `ImagePullBackOff` pods and both workloads sharing the bad tag within 10 KB | NFR3 |
| U2-T17 | The full `namespace_overview` returns unhealthy pods, non-ready workloads, recent Warning events and Argo CD state in one response ≤ 10 KB | ToolCatalog |
| U2-T18 | The investigation prompt is registered through U1's hook and renders through the pipeline; U1-T20's DNS-1123 rejection holds for it | FR1.6, ADR-003 |
| U2-T19 | Prompt and guide content check: the prompt names the report sections, labels hypotheses and proposes follow-ups; the guide says fixes are a local branch and commit, never a push or a PR; the manual-approval text and the "tools only, report gaps" instruction are present; the operator guide exists and names the deny rules | FR9.1, FR9.2, FR9.3, FR10.1, FR10.2, FR11.2, FR11.3, FR11.4 |
| U2-T20 | The settings template contains the FR11 deny rules and no auto-approve | FR11 |
| U2-T21 | CI gate in `.github/workflows/ops-assistant.yml`: ≥ 80% coverage, `ruff`, existing suite green; all U1 tests still pass | NFR12 |
| U2-T22 | `describe_pod` returns env variable names and their source kind only; a seeded secret-looking env value never appears | FR2.2 |
| U2-T23 | `list_workloads` returns Deployments and CronJobs with ready counts and image refs | FR2.3 |
| U2-T24 | `get_alerts` returns firing alerts from the fake Alertmanager data, and "no alerts firing" is distinct from a failed read | FR5.2, NFR7 |
| U2-T25 | Every U2 tool's items carry stable evidence references that repeat across two runs | FR8.2 |
| U2-T26 | Each U2 tool requires an explicit window where it takes one and replays identically twice on the same fixtures | NFR8 |

## U3: Fixtures and CI

**Purpose.** This unit replaces hand-written evidence with recorded, redacted game-day fixtures, proves zero leakage against realistic seeded secrets on every tool output type, and makes CI run it all with no cluster [Q1].

**Components owned.**

| Component | Scope in U3 |
|---|---|
| FixtureRecorder | Complete: hand-run, guarded by StartupGuard, reads through the U2 readers, writes only Redactor output, makes variants by editing copies |
| FixtureLeakScan | Complete: CI scan of every committed fixture file; `tests/ops_mcp/fixtures/seeded/` is the only exemption [Q7] |
| CI job (repo tooling, not a component) | Extends U1's `.github/workflows/ops-assistant.yml` with the recorded-fixture runs and the leak scan [Q9] |

**Seeded data (not a component).** The NFR2 SeededSampleSet is an entity of the Redactor (Domain Design). U1 started it in `tests/ops_mcp/fixtures/seeded/` [Q7]; U3 completes it as data and tests across every tool output type [Q1].

**Implementation notes and constraints.**

- U3 adds recorded fixtures next to U1's and U2's hand-written fixtures [Q3]. The hand-written set has no secret-shaped values, so it stays in the repo and passes the leak scan with no exemption [Q7].
- Fixture-set-parameterised tests (the game-day assertions: U1-T16, U2-T2 to U2-T5, U2-T9, U2-T17) run on both sets. Engineered-data tests stay on hand-written or seeded data, because recorded fixtures do not contain their inputs: U1-T4 to U1-T7, U2-T8, U2-T16 and every test that plants a seeded secret.
- The seeded samples are the only exemption from the leak scan, they carry the fake marker, and they are clearly fake (NFR10.2). When gitleaks is added, `seeded/` is its one allowlist path [Q7].
- NFR11, the live acceptance run, is the operator's final check after U3. It is not a CI test.

### U3 tests

| # | Test | Proves |
|---|---|---|
| U3-T1 | The recorder refuses to run unless StartupGuard passes, and writes nothing that has not passed through Redactor | NFR10.2, ADR-004 |
| U3-T2 | Recorded fixtures cover pods, events, workloads, the Argo CD Application, Prometheus series, Loki results and the PR #34 and #35 commits | NFR10 |
| U3-T3 | Variants (auth failure, lifecycle-deleted tag, partial failure, after revert) are produced by editing copies; the lifecycle variant uses an older first-parent SHA from the recorded transcript | NFR10, ADR-004 |
| U3-T4 | Seeded NFR2 samples in every tool output type (pod/workload descriptions, events, Kubernetes logs, Loki, Prometheus labels, Argo CD, git diff): no seeded value or its base64 form appears; each shows as `[REDACTED:<kind>]`; counts match; FR7.6 identifiers survive | NFR2 |
| U3-T5 | FixtureLeakScan fails the build for each NFR10.2 pattern planted in a fixture file outside `seeded/`, and passes on the hand-written set, the recorded set and the exempt `seeded/` tree | NFR10.2 |
| U3-T6 | CI runs every tool against the recorded fixtures with no cluster and asserts the evidence for all four success criteria, the header, the count, ≤ 10 KB and full redaction, with PR #34 as the introducing change | NFR10 |
| U3-T7 | The fixture-set-parameterised U1 and U2 tests (U1-T16, U2-T2 to U2-T5, U2-T9, U2-T17) pass on the recorded fixture set; the engineered-data tests stay green on their own data | NFR10 |
| U3-T8 | CI gate in `.github/workflows/ops-assistant.yml`: ≥ 80% coverage, `ruff`, existing suite green | NFR12 |
| U3-A1 | Manual, after U3: the operator's live game-day run on minikube with the FR11 deny rules, judged against the seven-line checklist, within 5 minutes | NFR11, NFR4 |

## Sources

- `aidlc/spaces/default/intents/261015-ops-assistant/inception/domain-design/components.md` (component catalogue, Constraints for Functional Design)
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/domain-design/decisions.md` (ADR-003, ADR-004, ADR-007, ADR-008, ADR-010, ADR-011)
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/domain-design/reviews/review-04.md` (R-10 composition root)
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/requirements-analysis/requirements.md`
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/units-generation/units-generation-questions.md` [Q1] to [Q9]
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/units-generation/reviews/review-01.md`

## Assumptions & Open Questions

- [assumption] The deployment model is one local `ops_mcp/` process (ADR-007); this was not asked separately.
- [Q9] U1's automated checks are fixture-only. The live start-up and self-check are first tried at the operator's manual check U1-A1, using the identity kit that is now in U1.
- [assumption] In U1, `namespace_overview` returns namespaces, pods and pod status only; U2 extends it to the full Domain Design shape.
- [Q6] This planning work changes nothing outside `aidlc/` and `docs/aidlc/`. Code Generation for U1 will need to write `ops_mcp/`, `tests/ops_mcp/` (including `fixtures/seeded/`), the new `.github/workflows/ops-assistant.yml` and the identity kit manifests [Q9]; that list is confirmed with the operator at U1's plan approval.
