# Units Generation Questions

The operator answered these in chat on 2026-11-03. Their answers are recorded below as given.

## Q1: Unit boundary strategy

How should the 17 Domain Design components be grouped into units?

A. By layer (core, readers, tooling)
B. By capability slice, starting with a walking skeleton
C. One unit per component
D. One unit for everything
X. Other (please specify)

[Answer]: X. Other: exactly 3 units. Unit 1, Safe core (walking skeleton): StartupGuard + ClusterSession, Redactor, EvidencePipeline, OpsMcpServer + stdio transport (including the fail-closed frame and the named production entry point from R-10), ToolCatalog, CallLog, plus ONE simple read-only tool end to end (namespace_overview on fixtures), so the single-exit, redaction and stdout tests run from the start. Unit 2, Investigation: the readers (Kubernetes, Argo CD, Prometheus, Loki, Git) + ReaderBackends, ImagePullDiagnosis, the remaining tools, InvestigationGuide. Unit 3, Fixtures and CI: FixtureRecorder, the seeded fake-secrets set, FixtureLeakScan, and the CI job that runs the tool tests on fixtures.

## Q2: Unit 1 dependency on readers

Unit 1's namespace_overview needs a Kubernetes reader and a fixture backend, but Q1 places both in Unit 2. How should this be resolved?

A. Move a minimal KubernetesReader and ReaderBackends into Unit 1; Unit 2 extends them
B. Stub them in Unit 1 test code only
C. Drop namespace_overview from Unit 1
X. Other (please specify)

[Answer]: A. Move a minimal KubernetesReader (only what namespace_overview needs: namespaces, pods and their status) and ReaderBackends into Unit 1. Unit 2 extends them. The live backend only reads through ClusterSession, so nothing reaches the cluster without passing StartupGuard.

## Q3: Unit 1 test data

FixtureRecorder is in Unit 3. What fixtures do Unit 1's tests use?

A. A small hand-written fixture set with obviously fake values, committed under the test folder; Unit 3 replaces or extends it with recorded fixtures
B. Wait for Unit 3's recorded fixtures
X. Other (please specify)

[Answer]: A. Unit 1's tests use a small hand-written fixture set with obviously fake values, committed under the test folder. Unit 3 replaces or extends it with recorded fixtures later.

## Q4: Ordering and delivery

How are the units built and merged?

A. Strictly in order, each with its own Functional Design, build and PR; each merged before the next starts
B. In parallel where the DAG allows
X. Other (please specify)

[Answer]: X. Other: built in the order Unit 1, Unit 2, Unit 3. Each unit gets its own Functional Design, its own build and its own PR. Unit 1 must be merged before Unit 2 starts.

## Q5: Deployment model

A. One local process (the MCP server) that all units extend; fixture and CI tooling ship in the same repo
B. Independently deployed units
X. Other (please specify)

[Answer]: Not asked separately. Taken from the approved Domain Design (ADR-007): A. One local stdio MCP server package (`ops_mcp/`), run by Claude Code; units are build increments of it, not separate deployments. Recorded as an assumption in unit-of-work.md.

## Q6: Change boundary for this planning work

[Answer]: Don't change anything outside /aidlc and /docs/aidlc.

## Q7: Where U1's secret-bearing fakes live (review-01, Major 1)

The operator answered on 2026-11-03, after review-01. An earlier audit entry at 15:08 recorded a different answer before the operator replied; that entry was premature and is corrected in the audit log.

A. Put them in `tests/ops_mcp/fixtures/seeded/` from U1, in the seeded layout with the fake marker
B. Keep planted secrets in test code only
X. Other (please specify)

[Answer]: A. Fake secrets go in `tests/ops_mcp/fixtures/seeded/` from U1 onwards, in the seeded layout with the fake marker. The hand-written evidence fixtures stay free of secret-shaped values. Tests that need a planted secret load it from `seeded/`. That gives one place for all fake secrets, one marker and one leak-scan exemption (and later one gitleaks allowlist path).

## Q8: Who owns the prompt path (review-01, Major 2)

A. U1 owns the prompt-registration hook and the DNS-1123 validation in the adapter, with a U1 test; U2 supplies only the prompt content
B. Mark the prompt path as a U2 extension of the adapter
X. Other (please specify)

[Answer]: A. Agree with the reviewer. U1 owns the prompt-registration hook and the DNS-1123 validation in the adapter, with a U1 test. U2 supplies only the prompt content. Remove "Complete" from the adapter row, or qualify it.

## Q9: Minor review points, CI file and identity kit

A. Fold in all minor review points
X. Other (please specify)

[Answer]: A, plus: the U1 CI step goes in a NEW workflow file, `.github/workflows/ops-assistant.yml` (pytest with coverage, then `ruff`, on `ops_mcp/` only); the existing `ci.yml` and `deploy.yml` are not edited. The read-only identity kit (ServiceAccount + RBAC manifests, FR1.4) moves into U1, with a manual live check at the end of U1: the operator applies the manifests and runs the server's start-up self-check against minikube. The agent never applies anything.
