# Unit Story Map: Ops Assistant MCP Server

No `stories.md` was produced (User Stories was not in this plan), so rows are keyed by functional requirement, with NFR rows added. Each row names the one implementing unit. Requirements that more than one unit touches are listed again under Cross-Cutting Rows. A parent row (FR1, FR2, …) names the unit that delivers most of it; its full coverage is the roll-up of its child rows.

## Functional Requirements

| ID | Unit ID | Directory | Delivered by |
|---|---|---|---|
| FR1 | U1 | u1-safe-core | MCP server, transport and registration |
| FR1.1 | U1 | u1-safe-core | OpsMcpServer stdio transport |
| FR1.2 | U1 | u1-safe-core | OpsMcpServer (no AI calls) |
| FR1.3 | U1 | u1-safe-core | StartupGuard (dedicated kubeconfig only) |
| FR1.4 | U1 | u1-safe-core | Read-only identity kit manifests (moved from U2 [Q9]) |
| FR1.5 | U1 | u1-safe-core | OpsMcpServer (on demand, no background process) |
| FR1.6 | U2 | u2-investigation | InvestigationGuide prompt content (U1 provides the prompt hook and DNS-1123 check [Q8]) |
| FR2 | U2 | u2-investigation | KubernetesReader, ToolCatalog |
| FR2.1 | U2 | u2-investigation | `list_pods` (U1 delivers the pod-status subset inside `namespace_overview`) |
| FR2.2 | U2 | u2-investigation | `describe_pod` |
| FR2.3 | U2 | u2-investigation | `list_workloads` |
| FR2.4 | U2 | u2-investigation | `find_image_users` |
| FR2.5 | U2 | u2-investigation | ImagePullDiagnosis, exact pull errors |
| FR2.6 | U2 | u2-investigation | ImagePullDiagnosis tag-history heuristic |
| FR2.7 | U2 | u2-investigation | ImagePullDiagnosis variants |
| FR3 | U2 | u2-investigation | KubernetesReader events |
| FR3.1 | U2 | u2-investigation | `get_events` |
| FR3.2 | U2 | u2-investigation | `get_events` empty-window note |
| FR4 | U2 | u2-investigation | Logs |
| FR4.1 | U2 | u2-investigation | `get_logs` |
| FR4.2 | U2 | u2-investigation | LokiReader, `query_loki` |
| FR4.3 | U2 | u2-investigation | Log tools, not-started note |
| FR5 | U2 | u2-investigation | PrometheusReader |
| FR5.1 | U2 | u2-investigation | `query_prometheus` |
| FR5.2 | U2 | u2-investigation | `get_alerts` |
| FR5.3 | U2 | u2-investigation | PrometheusReader reduction |
| FR6 | U2 | u2-investigation | ArgoCdReader, GitReader |
| FR6.1 | U2 | u2-investigation | `get_argocd_app` |
| FR6.2 | U2 | u2-investigation | `git_history` |
| FR6.3 | U2 | u2-investigation | Revision-to-commit linking |
| FR6.4 | U2 | u2-investigation | GitReader read-only runner |
| FR6.5 | U2 | u2-investigation | CloneStatus |
| FR6.6 | U2 | u2-investigation | Missing-revision and branch check |
| FR7 | U1 | u1-safe-core | Redactor |
| FR7.1 | U1 | u1-safe-core | EvidencePipeline single exit |
| FR7.2 | U1 | u1-safe-core | ClusterSession path allow-list, KubernetesReader never reads Secrets |
| FR7.3 | U1 | u1-safe-core | Redactor rules |
| FR7.4 | U1 | u1-safe-core | Redaction count |
| FR7.5 | U1 | u1-safe-core | Public-IP rule |
| FR7.6 | U1 | u1-safe-core | Positional protection |
| FR7.7 | U1 | u1-safe-core | Redact before truncate |
| FR8 | U1 | u1-safe-core | EvidenceEnvelope |
| FR8.1 | U1 | u1-safe-core | Evidence header |
| FR8.2 | U1 | u1-safe-core | Stable evidence references |
| FR9 | U2 | u2-investigation | InvestigationGuide report format |
| FR9.1 | U2 | u2-investigation | Prompt report sections |
| FR9.2 | U2 | u2-investigation | Hypothesis labelling in the prompt |
| FR9.3 | U2 | u2-investigation | Follow-up proposals in the prompt |
| FR10 | U2 | u2-investigation | InvestigationGuide fix preparation guidance |
| FR10.1 | U2 | u2-investigation | Guide: local branch and commit |
| FR10.2 | U2 | u2-investigation | Guide: no push, no PR |
| FR10.3 | U1 | u1-safe-core | ToolCatalog has no write tool |
| FR11 | U2 | u2-investigation | Settings template, prompt |
| FR11.1 | U2 | u2-investigation | Deny rules in the settings template |
| FR11.2 | U2 | u2-investigation | Manual approval guidance |
| FR11.3 | U2 | u2-investigation | Prompt: tools only, report gaps |
| FR11.4 | U2 | u2-investigation | Operator guide |

## Non-Functional Requirements

| ID | Unit ID | Directory | Delivered by |
|---|---|---|---|
| NFR1 | U1 | u1-safe-core | Read-only identity kit manifests, checked live at U1-A1 [Q9] |
| NFR1.2 | U1 | u1-safe-core | StartupGuard self-check |
| NFR1.3 | U2 | u2-investigation | Prometheus and Loki through the service proxy |
| NFR2 | U3 | u3-fixtures-ci | Seeded sample set across every tool output type |
| NFR3 | U1 | u1-safe-core | EvidencePipeline size and ordering |
| NFR4 | U3 | u3-fixtures-ci | Checked only in the live acceptance run after U3 |
| NFR5 | U1 | u1-safe-core | Per-call time budget |
| NFR6 | U2 | u2-investigation | Per-source degradation across five sources |
| NFR7 | U1 | u1-safe-core | No-data vs could-not-read in the ToolCatalog framework |
| NFR8 | U1 | u1-safe-core | Explicit time window in the ToolCatalog framework |
| NFR9 | U1 | u1-safe-core | CallLog |
| NFR10 | U3 | u3-fixtures-ci | Recorded fixtures and CI job |
| NFR10.2 | U3 | u3-fixtures-ci | FixtureLeakScan |
| NFR11 | U3 | u3-fixtures-ci | Live acceptance run after U3 |
| NFR12 | U1 | u1-safe-core | Coverage and lint gate, first set up in U1 in the new `.github/workflows/ops-assistant.yml` [Q9] |
| NFR13 | U2 | u2-investigation | GitReader runner, no outbound calls |

## Cross-Cutting Rows

| ID | Units | How it spans units |
|---|---|---|
| FR1 | U1, U2 | U1 delivers the server, transport, identity kit and prompt hook; U2 delivers the prompt content (FR1.6) |
| FR1.6 | U1, U2 | U1 owns prompt registration and DNS-1123 validation; U2 supplies the prompt content [Q8] |
| FR2.1 | U1, U2 | U1 returns pod status inside `namespace_overview`; U2 adds the full `list_pods` tool |
| FR8.2 | U1, U2 | U1 defines stable evidence references; U2 tools carry them (U2-T25) |
| NFR1 | U1, U2 | U1 ships the identity kit covering all five readers' reads; U2 may add read-only rules only if Functional Design finds a gap |
| NFR1.3 | U1, U2 | U1 provides the GET-only transport (U1-T3); U2 adds the Prometheus and Loki service-proxy path allow-lists |
| FR7.2 | U1, U2 | U1 fixes the Secret-free path allow-list; U2's new readers must stay inside it |
| NFR3 | U1, U2 | U1 enforces the limit; U2-T16 proves it on the padded fixture for its tools |
| NFR6, NFR7 | U1, U2 | U1 defines the error and no-data records; U2 applies them to four more sources |
| NFR12 | U1, U2, U3 | Every unit's PR passes the coverage and lint gate |
| NFR2, NFR10 | U1, U2, U3 | U1 starts `tests/ops_mcp/fixtures/seeded/` as the only home of fake secrets and keeps hand-written evidence secret-free [Q7]; U2 adds to both; U3 completes the seeded set and reruns the fixture-set-parameterised tests on recorded fixtures |

## Implementation Order Within Each Unit

- **U1:** ClusterSession and StartupGuard → Redactor and the first `seeded/` samples → EvidencePipeline → ReaderBackends (fixture, then live) and the minimal KubernetesReader → ToolCatalog framework and `namespace_overview` → OpsMcpServer adapter and transport, including the fail-closed frame and the prompt hook → production entry point → CallLog → identity kit manifests → `.github/workflows/ops-assistant.yml` → operator's manual live check U1-A1.
- **U2:** KubernetesReader extensions → ArgoCdReader → GitReader → PrometheusReader and LokiReader → ImagePullDiagnosis → remaining tools and full `namespace_overview` → InvestigationGuide content (prompt, operator guide, settings template).
- **U3:** FixtureRecorder → recorded game-day set and variants → completed seeded sample set and NFR2 tests → FixtureLeakScan → CI job extensions in `ops-assistant.yml`.

## Coverage Verification

Every FR and NFR in `requirements.md` has exactly one implementing unit above. Each of U1, U2 and U3 has rows.

## Sources

- `aidlc/spaces/default/intents/261015-ops-assistant/inception/requirements-analysis/requirements.md`
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/units-generation/unit-of-work.md`
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/units-generation/units-generation-questions.md` [Q7] to [Q9]

## Assumptions & Open Questions

None.
