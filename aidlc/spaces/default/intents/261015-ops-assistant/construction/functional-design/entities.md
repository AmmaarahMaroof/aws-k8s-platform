# Entities: U1 Safe core (`u1-safe-core`)

The YAML block below is the source of truth for U1's entity model. Logical types only; no storage or framework is implied. Entities that U2 and U3 extend (PodSnapshot, SeededSampleSet, ReadOnlyIdentityKit) are defined here in their U1 shape, and their extension points are marked.

```yaml
entities:
  - name: ServerSettings
    owner: production entry point
    description: Start-up inputs read once by the entry point and handed to StartupGuard and the adapter. Nothing else reads configuration.
    attributes:
      - { name: kubeconfig_path, type: path, required: true, constraints: "from the OPS_MCP_KUBECONFIG environment variable set in .mcp.json; must not resolve to the default kubeconfig (BR1.1, BR1.2)" }
      - { name: namespace_allow_list, type: list<dns1123_label>, required: true, min: 1, constraints: "server argument in .mcp.json, default [uptime]; unique entries; each a DNS-1123 label of at most 63 characters (BR1.3)" }
      - { name: call_log_path, type: path, required: true, default: "~/.local/state/ops-mcp/calls.log", constraints: "not configurable by environment; tests inject a temporary path through the adapter constructor (BR7.1)" }
      - { name: recheck_interval_s, type: integer, required: true, default: 300, constraints: "constant, not configurable (BR1.9)" }
      - { name: recheck_timeout_ms, type: integer, required: true, default: 4000, constraints: "constant (BR1.9)" }
      - { name: proxy_resource_names, type: list<string>, required: true, constraints: "constant PROXY_RESOURCE_NAMES, exactly the Prometheus and Loki services; strings pinned in Infrastructure Design (BR1.15)" }
      - { name: tool_budget_ms, type: integer, required: true, default: 5000, constraints: "constant (BR6.3)" }
      - { name: output_limit_bytes, type: integer, required: true, default: 10000, constraints: "constant; UTF-8 bytes of the whole text sent (BR5.3)" }
    relationships:
      - { to: PermissionReport, cardinality: "1..*", direction: "settings drive each check" }

  - name: PermissionReport
    owner: StartupGuard
    description: Result of one self-check, at start-up or at a re-check.
    attributes:
      - { name: check_kind, type: enum, required: true, allowed: [startup, recheck] }
      - { name: checked_scopes, type: list<string>, required: true, constraints: "'cluster' plus every allow-listed namespace plus the optional-source namespaces argocd and monitoring (BR1.4)" }
      - { name: service_account, type: string, required: true }
      - { name: excess_permissions, type: list<PermissionGap>, required: true, constraints: "empty for a pass" }
      - { name: missing_core_reads, type: list<PermissionGap>, required: true, constraints: "empty for a pass" }
      - { name: missing_optional_reads, type: list<PermissionGap>, required: true }
      - { name: verdict, type: enum, required: true, allowed: [pass, refuse, inconclusive] }
      - { name: monotonic_checked_at, type: monotonic_instant, required: true, constraints: "internal only; never serialised into any output (BR1.11)" }
    constraints:
      - "verdict = refuse if excess_permissions or missing_core_reads is non-empty"
      - "verdict = inconclusive only when the review requests themselves could not be completed (BR1.14)"

  - name: PermissionGap
    owner: StartupGuard
    description: One verb/resource pair that is too much or missing, in one scope.
    attributes:
      - { name: scope, type: string, required: true, constraints: "'cluster' or a namespace" }
      - { name: verb, type: string, required: true }
      - { name: resource, type: string, required: true, constraints: "group/resource[/subresource], optional resourceName" }

  - name: ServingState
    owner: OpsMcpServer
    description: The adapter's lifecycle state. One instance per process.
    attributes:
      - { name: state, type: enum, required: true, allowed: [starting, serving, stopped], default: starting }
      - { name: stop_reason, type: string, required: false, constraints: "fixed text naming the excess permission or missing core read; never sent to the client (the client gets the constant frame)" }
      - { name: last_check, type: ref<PermissionReport>, required: true }
    constraints:
      - "stopped is terminal for the process (BR1.10); transitions are in functional-spec.md"

  - name: VerifiedSession
    owner: ClusterSession
    description: The one read-only connection, constructible only by StartupGuard after a pass.
    attributes:
      - { name: session_id, type: string, required: true, unique: true }
      - { name: service_account, type: string, required: true }
      - { name: api_server, type: url, required: true }
      - { name: allowed_paths, type: list<path_pattern>, required: true, constraints: "GET-only; no path under secrets (BR3.6)" }
      - { name: degraded_sources, type: list<DegradedSource>, required: true }

  - name: DegradedSource
    owner: ReaderBackends
    description: A source that cannot be read, with the reason. Shown in every tool output (BR5.7).
    attributes:
      - { name: source, type: enum, required: true, allowed: [kubernetes-logs, argocd, prometheus, loki, git], constraints: "U1 can only mark sources whose permission is checked; git is added by U2" }
      - { name: reason, type: enum, required: true, allowed: [missing-permission, unreachable, timeout, not-installed] }
      - { name: detail, type: string, required: true, constraints: "fixed phrase, e.g. 'not readable, missing permission get services/proxy in monitoring'" }

  - name: BackendSelection
    owner: ReaderBackends
    description: The single selection point for live or fixture data.
    attributes:
      - { name: mode, type: enum, required: true, allowed: [live, fixture] }
      - { name: session_id, type: string, required: false, constraints: "required when mode = live" }
      - { name: fixture_dir, type: path, required: false, constraints: "required when mode = fixture; tests only" }
      - { name: sources, type: list<string>, required: true, constraints: "U1: [kubernetes]" }

  - name: TimeWindow
    owner: ToolCatalog
    description: The explicit window every time-aware call carries (NFR8).
    attributes:
      - { name: since, type: utc_timestamp, required: true, constraints: "ISO 8601 with Z or +00:00 only (BR2.2)" }
      - { name: until, type: utc_timestamp, required: true, constraints: "same format" }
    constraints:
      - "since < until (BR2.3)"
      - "until - since <= 6 hours (BR2.4)"

  - name: ToolCall
    owner: OpsMcpServer
    description: One incoming MCP tools/call request.
    attributes:
      - { name: call_id, type: string, required: true, unique: true, constraints: "generated per call; deterministic counter, not time-based" }
      - { name: tool_name, type: string, required: true }
      - { name: arguments, type: map, required: true }
      - { name: budget_ms, type: integer, required: true, default: 5000 }
    relationships:
      - { to: ToolDefinition, cardinality: "0..1", direction: "resolved by name; unknown name gives an error record" }

  - name: ToolDefinition
    owner: ToolCatalog
    description: A registered tool. U1 registers one; U2 adds more through the same API.
    attributes:
      - { name: tool_name, type: string, required: true, unique: true }
      - { name: description, type: string, required: true }
      - { name: arguments, type: list<ArgumentSpec>, required: true }
      - { name: read_only, type: boolean, required: true, allowed: [true], constraints: "registration refuses false (BR6.10)" }
      - { name: sources_used, type: list<string>, required: true }

  - name: PromptRegistration
    owner: OpsMcpServer
    description: The prompt-registration hook U1 owns. U2 supplies PromptTemplate content through it.
    attributes:
      - { name: prompt_name, type: string, required: true, unique: true }
      - { name: arguments, type: list<ArgumentSpec>, required: true, constraints: "U1 fixes one argument kind: namespace, validated by BR6.5" }
      - { name: render, type: function_ref, required: true, constraints: "returns structured records, never raw text; output passes EvidencePipeline (BR6.6)" }

  - name: PodSnapshot
    owner: KubernetesReader
    description: U1 subset of the pod record. U2 adds owner, env_refs and full describe fields.
    attributes:
      - { name: namespace, type: dns1123_label, required: true, protected: true }
      - { name: pod_name, type: string, required: true, protected: true }
      - { name: phase, type: enum, required: true, allowed: [Pending, Running, Succeeded, Failed, Unknown], protected: true }
      - { name: containers, type: list<ContainerStatus>, required: true }
      - { name: ready, type: boolean, required: true, constraints: "true only when the pod's Ready condition has status True" }
      - { name: unhealthy, type: boolean, required: true, constraints: "derived by BR3.1/BR3.2" }
      - { name: last_change_at, type: utc_timestamp, required: false, constraints: "latest container state or condition transition time from the API record; used for ordering" }
      - { name: evidence_ref, type: string, required: true, constraints: "k8s:pod/<namespace>/<pod_name> (BR5.6)" }
    relationships:
      - { to: ContainerStatus, cardinality: "1..*", direction: "pod has containers" }

  - name: ContainerStatus
    owner: KubernetesReader
    attributes:
      - { name: name, type: string, required: true, protected: true }
      - { name: image, type: image_ref, required: true, protected: true }
      - { name: ready, type: boolean, required: true }
      - { name: restart_count, type: integer, required: true, min: 0 }
      - { name: waiting_reason, type: string, required: false, protected: true }
      - { name: waiting_message, type: string, required: false, constraints: "scanned; exact text kept apart from redactions (FR2.5 in U2)" }
      - { name: terminated_reason, type: string, required: false, protected: true }
      - { name: last_termination_finished_at, type: utc_timestamp, required: false, constraints: "lastState.terminated.finishedAt; drives BR3.2" }

  - name: EvidenceItem
    owner: EvidencePipeline
    description: One structured record a tool returns. Never free text from a handler (ADR-003).
    attributes:
      - { name: kind, type: enum, required: true, allowed: [record, empty, error, note] }
      - { name: evidence_ref, type: string, required: true }
      - { name: unhealthy, type: boolean, required: true, default: false }
      - { name: sort_time, type: utc_timestamp, required: false }
      - { name: fields, type: map, required: true, constraints: "each field declared protected or scanned; undeclared defaults to scanned (BR4.9)" }
      - { name: redaction_counts, type: map<redaction_kind,integer>, required: true, constraints: "this item's own counts; the header sums them over the items sent (BR5.3)" }

  - name: ErrorRecord
    owner: ToolCatalog
    description: An EvidenceItem of kind error.
    attributes:
      - { name: error_kind, type: enum, required: true, allowed: [argument, unknown-tool, timeout, could-not-read, internal] }
      - { name: source, type: string, required: false }
      - { name: query_or_object, type: string, required: false }
      - { name: cause, type: string, required: true, constraints: "fixed phrase plus redacted detail" }

  - name: EvidenceEnvelope
    owner: EvidencePipeline
    description: The one shape every outgoing message has.
    attributes:
      - { name: tool_name, type: string, required: true }
      - { name: source, type: string, required: true }
      - { name: query_or_object, type: string, required: true }
      - { name: window, type: "ref<TimeWindow> or 'none'", required: true, constraints: "'none' when the arguments failed validation (BR5.2)" }
      - { name: retrieved_at, type: "utc_timestamp or 'not retrieved'", required: true, constraints: "stamped by the backend (live: retrieval time; fixture: the fixture set's recorded_at); 'not retrieved' when no read completed; tool code never reads a clock (BR3.4)" }
      - { name: redaction_total, type: integer, required: true, min: 0 }
      - { name: redaction_by_kind, type: map<redaction_kind,integer>, required: true, constraints: "kind names and counts only (BR4.8)" }
      - { name: degraded_sources, type: list<DegradedSource>, required: true, constraints: "always present; 'none' when empty (BR5.7)" }
      - { name: items_total, type: integer, required: true }
      - { name: items_dropped, type: integer, required: true, min: 0 }
      - { name: truncation_note, type: string, required: false, constraints: "present when items_dropped > 0 (BR5.4)" }
      - { name: items, type: list<EvidenceItem>, required: true }
    relationships:
      - { to: RedactionResult, cardinality: "1", direction: "envelope carries one redaction result" }

  - name: RedactionRule
    owner: Redactor
    attributes:
      - { name: kind, type: enum, required: true, unique: true, allowed: [connection-string, secret-pair, bearer-token, jwt, aws-access-key-id, aws-secret-key, pem-private-key, docker-auth, base64-secret, public-ip] }
      - { name: marker, type: string, required: true, constraints: "[REDACTED:<kind>]" }

  - name: RedactionResult
    owner: Redactor
    attributes:
      - { name: total, type: integer, required: true, min: 0 }
      - { name: counts_by_kind, type: map<redaction_kind,integer>, required: true }
    constraints:
      - "total equals the sum of counts_by_kind"

  - name: SeededSampleSet
    owner: Redactor
    description: All fake secrets in the repo, under tests/ops_mcp/fixtures/seeded/<set>/. U1 starts it; U3 completes it.
    attributes:
      - { name: set_name, type: string, required: true, unique: true }
      - { name: fake_marker, type: string, required: true, constraints: "every seeded value contains it; fixture-set.json kind = seeded" }
      - { name: kinds, type: list<redaction_kind>, required: true, constraints: "U1: one sample per RedactionRule kind, plus a commit SHA beside an AWS secret key (ADR-010)" }
      - { name: files, type: list<path>, required: true }

  - name: CallRecord
    owner: CallLog
    attributes:
      - { name: call_id, type: string, required: true }
      - { name: logged_at, type: utc_timestamp, required: true, constraints: "wall clock is allowed here; the call log is not tool output" }
      - { name: tool_name, type: string, required: true, constraints: "from the closed tool list, else 'unknown'" }
      - { name: redacted_arguments, type: map, required: false, constraints: "absent if argument redaction failed" }
      - { name: duration_ms, type: integer, required: true, constraints: "monotonic clock" }
      - { name: bytes_returned, type: integer, required: true }
      - { name: redaction_total, type: integer, required: true }
      - { name: outcome, type: enum, required: true, allowed: [ok, empty, error, timeout, fail-closed] }

  - name: ReadOnlyIdentityKit
    owner: InvestigationGuide (delivered in U1)
    description: Manifests only. Applied by the operator, never by the agent or the server.
    attributes:
      - { name: service_account, type: string, required: true }
      - { name: roles, type: list<NamespacedRole>, required: true, constraints: "Roles only, no ClusterRole (BR1.13)" }
      - { name: kubeconfig_procedure, type: document_ref, required: true }

  - name: NamespacedRole
    owner: InvestigationGuide (delivered in U1)
    attributes:
      - { name: namespace, type: dns1123_label, required: true }
      - { name: rules, type: list<PolicyRule>, required: true, constraints: "verbs subset of [get, list, watch]; never secrets" }
```

## Summary

- **Configuration and identity:** ServerSettings, PermissionReport and PermissionGap, ServingState, VerifiedSession and DegradedSource describe how the server proves it is read-only, and what it does when that proof changes.
- **Calls:** ToolCall, ToolDefinition, PromptRegistration and TimeWindow describe what a client can ask for and how it is validated.
- **Evidence:** PodSnapshot and ContainerStatus are U1's only reader records. EvidenceItem, ErrorRecord and EvidenceEnvelope are the one output shape. RedactionRule, RedactionResult and SeededSampleSet belong to the Redactor.
- **Operations:** CallRecord is the server's own log. ReadOnlyIdentityKit and NamespacedRole are the manifests the operator applies.

## Sources

- `aidlc/spaces/default/intents/261015-ops-assistant/construction/functional-design/functional-design-questions.md` [Q1] to [Q11]
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/domain-design/components.md` (Entity Ownership, Fixture Formats, Constraints for Functional Design)
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/units-generation/unit-of-work.md` (U1 scope)
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/requirements-analysis/requirements.md`

## Assumptions & Open Questions

- [assumption] The kubeconfig path comes from an environment variable named `OPS_MCP_KUBECONFIG`, set in the `.mcp.json` server entry. FR1.3 allows "a dedicated environment variable or setting"; the name is a design choice.
- Operator decision: 10 KB means 10,000 bytes.
- [assumption] The ServiceAccount's namespace and how its token is issued stay open for Infrastructure Design (requirements OQ2).
