# Business Rules: U1 Safe core (`u1-safe-core`)

The YAML block is the source of truth. Rule groups: BR1 start-up and identity, BR2 call arguments, BR3 namespace overview and pod health, BR4 redaction, BR5 evidence shaping, BR6 adapter and transport, BR7 call log, BR8 test data.

```yaml
rules:
  # BR1 Start-up and identity
  - id: BR1.1
    statement: The server reads its kubeconfig only from OPS_MCP_KUBECONFIG.
    category: policy
    applies_to: StartupGuard
    trigger: start-up
    logic: IF the variable is unset or empty THEN refuse to start with the fixed message "OPS_MCP_KUBECONFIG is not set; refusing to start".
    violation: process exits non-zero; one fixed stderr line; no session exists
    source: FR1.3
  - id: BR1.2
    statement: The dedicated kubeconfig must not be the default one.
    category: validation
    applies_to: StartupGuard
    trigger: start-up
    logic: IF the path, after resolving symlinks, equals ~/.kube/config or any path listed in the KUBECONFIG variable THEN refuse to start naming the reason. The server never reads KUBECONFIG for loading.
    violation: refuse to start
    source: FR1.3
  - id: BR1.3
    statement: The namespace allow-list must be non-empty and valid.
    category: validation
    applies_to: ServerSettings
    trigger: start-up
    logic: IF the list is empty, OR any entry is not a DNS-1123 label of at most 63 characters, OR an entry repeats THEN refuse to start naming the bad entry.
    violation: refuse to start
    source: "FR1.3, Q9"
  - id: BR1.4
    statement: The identity must hold no write, exec or Secret access anywhere the server can see.
    category: authorization
    applies_to: StartupGuard
    trigger: start-up and every re-check
    logic: Check scopes are the cluster plus every allow-listed namespace plus argocd and monitoring. Method (BR1.15) - in each namespace scope a SelfSubjectRulesReview lists every rule that applies there, including rules bound cluster-wide; in the cluster scope a fixed probe list of SelfSubjectAccessReviews with no namespace asks the same questions. A rules review marked incomplete counts as refuse, because the grant cannot be proven safe. A rule counts as wildcard if its verbs or resources contain "*". IF in any scope the identity can create, update, patch, delete or deletecollection anything, OR use pods/exec, pods/attach or pods/portforward, OR use any verb on secrets, OR holds a wildcard verb or resource, OR holds services/proxy without resourceNames, or with any resourceName other than the Prometheus and Loki services THEN the verdict is refuse, naming each excess permission and its scope.
    violation: "start-up: refuse to start; re-check: BR1.10"
    source: "NFR1, NFR1.2, NFR1.3, Q9, operator decision (argocd and monitoring scopes; services/proxy only by resourceNames)"
  - id: BR1.5
    statement: Core Kubernetes reads must be present in every allow-listed namespace.
    category: authorization
    applies_to: StartupGuard
    trigger: start-up and every re-check
    logic: Core reads are get and list on pods and events (core API group, events v1), deployments and replicasets (apps), and jobs and cronjobs (batch). Presence is asked with one SelfSubjectAccessReview per verb, resource and namespace. IF any is missing in any allow-listed namespace THEN the verdict is refuse, naming the missing read and namespace.
    violation: "start-up: refuse to start; re-check: BR1.10"
    source: "NFR1, Q4, Q9"
  - id: BR1.6
    statement: Missing optional reads degrade only their source.
    category: policy
    applies_to: StartupGuard, ReaderBackends
    trigger: start-up and every re-check
    logic: Optional reads are pods/log in allow-listed namespaces (source kubernetes-logs), applications in argocd (source argocd), and get on services/proxy for the Prometheus and Loki services in monitoring (sources prometheus, loki). Each is asked with a SelfSubjectAccessReview; the proxy reviews name the exact resourceName from the PROXY_RESOURCE_NAMES constant (BR1.15). IF one is missing THEN mark that source degraded with reason missing-permission; IF a re-check finds it present again THEN remove the mark. The degraded list always reflects the latest completed check.
    violation: none; the source's tools return a per-source error
    source: "NFR6, Q4, Q5"
  - id: BR1.7
    statement: Self-review requests are the only write-shaped API calls.
    category: constraint
    applies_to: StartupGuard, ClusterSession
    trigger: any API request
    logic: IF a request is not GET THEN it must be a SelfSubjectAccessReview or SelfSubjectRulesReview issued by StartupGuard; anything else is refused before it is sent.
    violation: request not sent; internal error record
    source: "NFR1.2, FR7.2"
  - id: BR1.8
    statement: Only StartupGuard creates a ClusterSession, and only after a pass.
    category: constraint
    applies_to: StartupGuard, ClusterSession
    trigger: start-up
    logic: IF the start-up verdict is not pass THEN no session object exists and the adapter is never constructed.
    violation: refuse to start
    source: "ADR-008, NFR1.2"
  - id: BR1.9
    statement: Permissions are re-checked before a call when the last check is stale, one re-check at a time.
    category: policy
    applies_to: OpsMcpServer, StartupGuard
    trigger: an incoming tool call or prompt request
    logic: IF the monotonic time since the last completed check is more than 300 seconds THEN run a re-check (BR1.4, BR1.5, BR1.6) before the call's 5-second budget starts. The re-check has its own 4-second limit; past it, it is inconclusive (BR1.14). Only one re-check runs at a time - a call that finds one in flight waits for it and uses its result. Worst case, a call answers within 4 s of re-check plus its 5 s budget.
    violation: n/a
    source: "Q5, NFR5"
  - id: BR1.10
    statement: A failed re-check stops serving for the life of the process.
    category: policy
    applies_to: ServingState
    trigger: re-check verdict refuse
    logic: IF a re-check returns refuse THEN set state to stopped. While stopped, every tool call and prompt request gets the constant fail-closed frame. A call already in flight when the state changes checks the state again just before sending, and sends the fail-closed frame instead of its result. No later check runs. Only a restart (which runs the full start-up check) recovers.
    violation: n/a
    source: "Q5, Q11"
  - id: BR1.11
    statement: The check clock never reaches output.
    category: constraint
    applies_to: StartupGuard, EvidencePipeline
    trigger: always
    logic: IF a value comes from the monotonic clock THEN it is never placed in an EvidenceEnvelope, so replays stay deterministic.
    violation: test failure (static and replay tests)
    source: "Q5, NFR8"
  - id: BR1.12
    statement: Start-up with an unreachable API server fails closed.
    category: policy
    applies_to: StartupGuard
    trigger: start-up
    logic: IF the review requests cannot be completed within 5 seconds THEN refuse to start with "cannot verify permissions".
    violation: refuse to start
    source: "NFR1.2"
  - id: BR1.13
    statement: The identity kit grants namespaced read access only.
    category: authorization
    applies_to: ReadOnlyIdentityKit
    trigger: manifest review and U1-T21
    logic: The kit holds one ServiceAccount, and only Roles and RoleBindings - a Role in each allow-listed namespace with get, list and watch on the core reads plus pods/log, a Role in argocd with get, list and watch on applications, and a Role in monitoring with get on services/proxy ONLY for the Prometheus and Loki services, using resourceNames. IF any manifest is a ClusterRole or ClusterRoleBinding, OR grants a verb outside get, list and watch, OR names secrets, OR grants services/proxy without resourceNames or for any other service THEN the manifest check fails.
    violation: CI test failure
    source: "FR1.4, NFR1, NFR1.3, Q1, operator decision"
  - id: BR1.14
    statement: No reader runs until a re-check succeeds.
    category: policy
    applies_to: StartupGuard, OpsMcpServer
    trigger: re-check whose review requests time out or fail
    logic: IF a re-check cannot complete THEN no reader runs on that call, which returns a could-not-read error record with the cause "could not verify permissions: cluster unreachable". The state stays serving and the 5-minute clock does not reset, so every later call re-checks first, and no reader runs until a re-check succeeds.
    violation: n/a
    source: "NFR5, NFR7, operator decision"
  - id: BR1.15
    statement: The proxy resource names and the cluster probe list are fixed constants.
    category: constraint
    applies_to: StartupGuard, ReadOnlyIdentityKit
    trigger: start-up and every re-check
    logic: PROXY_RESOURCE_NAMES holds exactly two entries, the Prometheus service and the Loki service in monitoring, in the form the API server checks for services/proxy. Its exact strings are pinned in Infrastructure Design and verified there with kubectl auth can-i; the identity kit's resourceNames and this constant must be equal (U1-T21 compares them). The cluster probe list covers create, update, patch, delete and deletecollection on pods, deployments, replicasets, jobs, cronjobs, services, rolebindings and clusterrolebindings; get and list on secrets; create on pods/exec, pods/attach and pods/portforward; and get on services/proxy with no resourceName. Any allowed probe counts as excess.
    violation: refuse
    source: "NFR1, NFR1.2, NFR1.3, operator decision"

  # BR2 Call arguments
  - id: BR2.1
    statement: The namespace argument is required, valid and allow-listed.
    category: validation
    applies_to: ToolCatalog
    trigger: tool call
    logic: IF namespace is missing, OR not a DNS-1123 label of at most 63 characters, OR not on the allow-list THEN return an argument error record naming the argument; read nothing.
    violation: argument error record
    source: "Q1, Q9"
  - id: BR2.2
    statement: since and until are UTC ISO 8601 timestamps.
    category: validation
    applies_to: ToolCatalog
    trigger: tool call
    logic: IF either is missing, unparseable, has no offset, or has an offset other than Z or +00:00 THEN return an argument error record.
    violation: argument error record
    source: "NFR8, Q2, Q10"
  - id: BR2.3
    statement: since is before until.
    category: validation
    applies_to: TimeWindow
    trigger: tool call
    logic: IF since >= until THEN return an argument error record.
    violation: argument error record
    source: Q2
  - id: BR2.4
    statement: The window is at most 6 hours.
    category: validation
    applies_to: TimeWindow
    trigger: tool call
    logic: IF until - since > 6 hours THEN return an argument error record that says the limit.
    violation: argument error record
    source: Q2
  - id: BR2.5
    statement: Unknown arguments are rejected.
    category: validation
    applies_to: ToolCatalog
    trigger: tool call
    logic: IF the call carries an argument the ToolDefinition does not declare THEN return an argument error record naming it after redaction.
    violation: argument error record
    source: "NFR7"
  - id: BR2.6
    statement: Tool code never reads the wall clock.
    category: constraint
    applies_to: ToolCatalog, readers
    trigger: always
    logic: Time comes only from the call's window and the backend's retrieved_at stamp.
    violation: static test failure
    source: NFR8

  # BR3 Namespace overview and pod health
  - id: BR3.1
    statement: A pod is unhealthy on phase, readiness or reason.
    category: calculation
    applies_to: PodSnapshot
    trigger: building the overview
    logic: IF phase is Pending, Failed or Unknown, OR any container is not ready, OR any container has a waiting reason, OR any container has a terminated reason other than Completed THEN unhealthy = true. A pod in phase Succeeded whose containers all terminated with Completed is healthy.
    violation: n/a
    source: "NFR3, Q3"
  - id: BR3.2
    statement: A restart inside the window makes a pod unhealthy.
    category: calculation
    applies_to: ContainerStatus
    trigger: building the overview
    logic: IF any container has restart_count > 0 AND its last_termination_finished_at is >= since AND < until THEN unhealthy = true. Only the last termination is visible, so earlier restarts in the window are not counted.
    violation: n/a
    source: "Q3, NFR8"
  - id: BR3.3
    statement: Overview order is unhealthy first, then most recent, then name.
    category: calculation
    applies_to: namespace_overview
    trigger: building the overview
    logic: Sort by unhealthy (true first), then last_change_at descending (missing last), then pod name ascending, so the order is total and deterministic.
    violation: n/a
    source: "NFR3, NFR8"
  - id: BR3.4
    statement: Retrieval time is stamped by the backend.
    category: constraint
    applies_to: ReaderBackends
    trigger: each read
    logic: The live backend stamps retrieved_at when the API answers. The fixture backend uses the fixture set's recorded_at. Tool code passes it through unchanged. IF no read completed (argument error, unknown tool, inconclusive re-check, timeout, internal error) THEN retrieved_at is the constant "not retrieved". With several sources, retrieved_at is the latest stamp among the completed reads.
    violation: replay test failure
    source: "FR8.1, NFR8"
  - id: BR3.5
    statement: No pods is not the same as could not read.
    category: policy
    applies_to: namespace_overview
    trigger: building the overview
    logic: IF the read succeeds with zero pods THEN return one empty item "no pods in namespace <ns>" with the window; IF the read fails THEN return a could-not-read error record naming the source, the object and the cause.
    violation: n/a
    source: "NFR7"
  - id: BR3.6
    statement: The server never reads Secrets.
    category: authorization
    applies_to: ClusterSession, KubernetesReader
    trigger: any API request
    logic: IF a path is not on the session's GET allow-list, or names secrets THEN refuse it before sending.
    violation: request not sent; internal error record
    source: "FR7.2, NFR1.3"

  # BR4 Redaction
  - id: BR4.1
    statement: Every match of a redaction rule is replaced by its marker.
    category: policy
    applies_to: Redactor
    trigger: every scanned field
    logic: Rules are connection-string (scheme://user:password@host), secret-pair (password, passwd, secret, token, api_key style key=value or key:value), bearer-token, jwt, aws-access-key-id, aws-secret-key, pem-private-key, docker-auth (dockerconfigjson auths and auth values), base64-secret, public-ip. Each match is replaced by [REDACTED:<kind>].
    violation: n/a
    source: "FR7.3"
  - id: BR4.2
    statement: Protected fields are never scanned.
    category: policy
    applies_to: Redactor, EvidenceItem
    trigger: every record
    logic: IF a field is declared protected (image refs and tags, commit SHAs, PR numbers, object kinds, names, namespaces, UIDs, event reasons, metric names, label keys) THEN it is passed through unchanged. Every other field is scanned, including label values.
    violation: n/a
    source: "FR7.6, ADR-010"
  - id: BR4.3
    statement: Multi-line values are scanned as one text.
    category: policy
    applies_to: Redactor
    trigger: every scanned field
    logic: Lines of one field are joined and scanned together so PEM blocks and wrapped base64 are caught.
    violation: n/a
    source: ADR-010
  - id: BR4.4
    statement: The AWS secret-key rule does not fire on bare hex.
    category: calculation
    applies_to: Redactor
    trigger: aws-secret-key candidates
    logic: IF a 40-character candidate has an AWS key name beside it, OR contains a character outside lowercase hex THEN redact it; otherwise leave it, so commit SHAs survive.
    violation: n/a
    source: ADR-010
  - id: BR4.5
    statement: Base64 forms of secrets are caught.
    category: calculation
    applies_to: Redactor
    trigger: base64 runs of 16 or more characters in a scanned field
    logic: Decode the run. IF the decoded text matches any other rule THEN replace the whole run with [REDACTED:base64-secret].
    violation: n/a
    source: "FR7.3"
  - id: BR4.6
    statement: Public IPs are redacted; private ranges are kept.
    category: policy
    applies_to: Redactor
    trigger: IPv4 and IPv6 addresses in scanned fields
    logic: Keep 10/8, 172.16/12, 192.168/16, 127/8, ::1, fc00::/7 and fe80::/10. Every other address, including documentation and carrier-grade ranges, is replaced by [REDACTED:public-ip].
    violation: n/a
    source: "FR7.5, operator decision"
  - id: BR4.7
    statement: Overlapping matches are redacted once.
    category: calculation
    applies_to: Redactor
    trigger: overlapping matches
    logic: The earliest match wins; on equal start the longest wins. Each replaced span counts once, under its winning kind.
    violation: n/a
    source: "FR7.4"
  - id: BR4.8
    statement: Redaction counts carry kind names and numbers only.
    category: policy
    applies_to: RedactionResult, EvidenceEnvelope
    trigger: every response
    logic: Report the total and a count per kind. Never report positions, lengths, prefixes, suffixes or hashes of redacted values.
    violation: test failure
    source: "FR7.4, Q6"
  - id: BR4.9
    statement: New fields default to scanned.
    category: policy
    applies_to: EvidenceItem
    trigger: record type definition
    logic: IF a field has no protected declaration THEN it is scanned.
    violation: n/a
    source: ADR-010
  - id: BR4.10
    statement: One redaction engine for every caller.
    category: constraint
    applies_to: Redactor
    trigger: always
    logic: Tool output, call-log arguments and (in U3) the recorder and leak scan call the same Redactor. The Redactor knows nothing about ordering, truncation or headers.
    violation: n/a
    source: "ADR-003, project rule on a separate Redactor engine"

  # BR5 Evidence shaping
  - id: BR5.1
    statement: The pipeline order is fixed.
    category: constraint
    applies_to: EvidencePipeline
    trigger: every outgoing message
    logic: Redact every item, then order, then truncate, then add the header.
    violation: n/a
    source: "FR7.7"
  - id: BR5.2
    statement: Every response carries the full evidence header.
    category: validation
    applies_to: EvidenceEnvelope
    trigger: every response
    logic: The header holds tool name, source, query or object, window, retrieved_at, the redaction total and per-kind counts, the degraded sources, items_total and items_dropped. Every field has a value on every response - window is "none" when the arguments failed validation (the error record names the bad argument), retrieved_at follows BR3.4, and source is "none" when no source was asked. These constants keep error responses deterministic on replay.
    violation: fail-closed frame
    source: "FR8.1, FR7.4, Q4, Q7"
  - id: BR5.3
    statement: The whole response is at most 10,000 UTF-8 bytes.
    category: constraint
    applies_to: EvidencePipeline
    trigger: every response
    logic: Render the header first and reserve its bytes, plus room for a truncation note. Add whole items in order; filling stops at the first item that does not fit, so a lower-priority item never displaces a higher one. The redaction counts in the header cover the items actually sent (each item carries its own counts from redaction). 10 KB means 10,000 bytes.
    violation: n/a
    source: "NFR3, Q7, operator decision (10,000 bytes)"
  - id: BR5.4
    statement: Dropped items are counted and explained.
    category: policy
    applies_to: EvidencePipeline
    trigger: items do not fit
    logic: IF items are dropped THEN set items_dropped and add a note "N items dropped; narrow the window or the namespace to see them". Items are never cut in half.
    violation: n/a
    source: "NFR3, Q7"
  - id: BR5.5
    statement: A header that cannot fit fails closed.
    category: constraint
    applies_to: EvidencePipeline
    trigger: header larger than the limit
    logic: IF the header and note alone exceed the limit THEN raise, which leads to the fail-closed frame (BR6.4).
    violation: fail-closed frame
    source: "NFR3, ADR-003"
  - id: BR5.6
    statement: Evidence references are stable.
    category: calculation
    applies_to: EvidenceItem
    trigger: every item
    logic: The reference is built only from protected identifiers, for example k8s:pod/<namespace>/<pod>; the same input gives the same reference on every run.
    violation: n/a
    source: "FR8.2"
  - id: BR5.7
    statement: Degraded sources are always stated and never look empty.
    category: policy
    applies_to: EvidenceEnvelope
    trigger: every response
    logic: The header always lists degraded sources with reason ("Prometheus - not readable, missing permission"), or "none". A tool whose source is degraded returns a could-not-read error record, never an empty item.
    violation: n/a
    source: "NFR6, NFR7, Q4"
  - id: BR5.8
    statement: Errors go through the same pipeline.
    category: constraint
    applies_to: EvidencePipeline
    trigger: any error record
    logic: Argument, unknown-tool, timeout and could-not-read records are redacted and enveloped like data.
    violation: n/a
    source: "FR7.1, ADR-003"

  # BR6 Adapter and transport
  - id: BR6.1
    statement: Only the transport writes to stdout.
    category: constraint
    applies_to: OpsMcpServer
    trigger: always
    logic: stdout carries only pipeline-built MCP frames. stderr carries only the start-up messages of BR1, which are fixed templates. The only values they insert are verbs, resources, namespaces and scopes from the permission check, and the position (not the value) of a bad allow-list entry; the kubeconfig contents and path are never printed. No other module writes to either stream.
    violation: static test failure
    source: "FR7.1, ADR-003"
  - id: BR6.2
    statement: Every handler failure becomes a record.
    category: policy
    applies_to: OpsMcpServer
    trigger: any exception in a handler
    logic: A catch-all turns it into an internal error record with a fixed cause, which then passes the pipeline.
    violation: n/a
    source: ADR-003
  - id: BR6.3
    statement: Each call has a 5-second budget; each source has 4 seconds.
    category: constraint
    applies_to: OpsMcpServer, readers
    trigger: tool call
    logic: The budget starts after any re-check. Sources run concurrently, each with a 4-second timeout. A source read that runs past 4 seconds is cancelled and returns a timeout error record naming the source and the query, while the other sources still answer and the pipeline keeps its last second. Reader work runs off the protocol loop on a fixed worker pool created at start-up. Every network read also sets a 4-second I/O timeout, so a blocked read ends by itself and never holds a worker past the call.
    violation: timeout error record
    source: "NFR5, NFR6, Q5, operator decision"
  - id: BR6.4
    statement: Pipeline or Redactor failure sends the constant frame.
    category: policy
    applies_to: OpsMcpServer
    trigger: EvidencePipeline or Redactor raises
    logic: Send the pre-built fail-closed frame (it may carry a tool name from the closed list, nothing else). Log the failure through the Redactor; if that fails too, log nothing.
    violation: n/a
    source: ADR-003
  - id: BR6.5
    statement: Prompt namespace arguments are validated.
    category: validation
    applies_to: PromptRegistration
    trigger: prompt request
    logic: IF the namespace argument is missing, not a DNS-1123 label of at most 63 characters, or not on the allow-list THEN reject it with an argument error before rendering.
    violation: argument error record
    source: "FR1.6, Q9, operator decision (allow-list applies to prompts)"
  - id: BR6.6
    statement: Rendered prompts pass the pipeline.
    category: constraint
    applies_to: PromptRegistration
    trigger: prompt request
    logic: The render function returns records; the adapter sends them through EvidencePipeline like tool output.
    violation: n/a
    source: "FR1.6, ADR-003"
  - id: BR6.7
    statement: Only the production entry point chooses live data.
    category: constraint
    applies_to: OpsMcpServer
    trigger: construction
    logic: The adapter receives backends, the ToolCatalog, the prompt registry and the call-log path through its constructor and has no mode switch. Only the entry point runs StartupGuard and ReaderBackends.live.
    violation: static test failure
    source: "ADR-011"
  - id: BR6.8
    statement: The server runs only while its client runs.
    category: constraint
    applies_to: OpsMcpServer
    trigger: lifecycle
    logic: Started over stdio by Claude Code; exits when stdin closes. Between calls nothing runs except the idle fixed worker pool (BR6.3): no timer, no background task, no child process, and no new thread created per call.
    violation: test failure
    source: "FR1.1, FR1.5"
  - id: BR6.9
    statement: The server makes no AI calls.
    category: constraint
    applies_to: ops_mcp package
    trigger: always
    logic: No AI or LLM client is imported; the only network peer is the API server.
    violation: static test failure
    source: "FR1.2, NFR13"
  - id: BR6.10
    statement: Only read-only tools can be registered.
    category: validation
    applies_to: ToolCatalog
    trigger: registration
    logic: IF a ToolDefinition is not read_only THEN registration fails at start-up.
    violation: refuse to start
    source: "FR10.3"
  - id: BR6.11
    statement: An unknown tool name is an error record.
    category: validation
    applies_to: OpsMcpServer
    trigger: tool call
    logic: IF the name is not registered THEN return an unknown-tool error record; the name is echoed only after redaction.
    violation: error record
    source: "NFR7"

  # BR7 Call log
  - id: BR7.1
    statement: The call log path is fixed.
    category: policy
    applies_to: CallLog
    trigger: construction
    logic: Production uses ~/.local/state/ops-mcp/calls.log. Tests pass a temporary path through the adapter constructor. No environment variable changes it.
    violation: n/a
    source: Q8
  - id: BR7.2
    statement: The call log is private to the user.
    category: authorization
    applies_to: CallLog
    trigger: opening the log
    logic: Create the directory with 0700 and the file with 0600. IF an existing file has wider permissions THEN tighten them to 0600; IF that fails THEN write nothing.
    violation: no log lines written
    source: Q8
  - id: BR7.3
    statement: The call log rotates at 5 MB and keeps 3 old files.
    category: policy
    applies_to: CallLog
    trigger: before a write that would pass 5 MB
    logic: Rename calls.log to calls.log.1 (shifting .1 to .2 and .2 to .3, dropping .3) and start a new 0600 file.
    violation: n/a
    source: Q8
  - id: BR7.4
    statement: One redacted line per call.
    category: policy
    applies_to: CallLog
    trigger: end of every call, including fail-closed calls
    logic: Write one line with call_id, logged_at, tool name, redacted arguments, duration, bytes returned, redaction total and outcome (ok, empty, error, timeout or fail-closed). IF argument redaction fails THEN omit the arguments; IF the write fails THEN drop the line.
    violation: line dropped
    source: "NFR9"
  - id: BR7.5
    statement: Logging never changes a response or writes elsewhere.
    category: constraint
    applies_to: CallLog
    trigger: always
    logic: A log failure is swallowed. The call log never writes to stdout, stderr or the cluster.
    violation: n/a
    source: "NFR9, ADR-003"

  # BR8 Test data
  - id: BR8.1
    statement: Fake secrets live only in the seeded tree.
    category: policy
    applies_to: SeededSampleSet, tests
    trigger: every committed test file
    logic: IF a file outside tests/ops_mcp/fixtures/seeded/ matches any redaction rule THEN the hygiene test fails. Every seeded value carries the fake marker. Tests that need a secret load it from seeded/.
    violation: test failure
    source: "unit plan Q7, NFR10.2"
  - id: BR8.2
    statement: Fixture mode opens no connections.
    category: constraint
    applies_to: ReaderBackends
    trigger: fixture mode
    logic: The fixture backend reads files only; it opens no socket and starts no process.
    violation: test failure
    source: ADR-011
```

## Rules summary

| Group | Rules | What they settle |
|---|---|---|
| Start-up and identity | BR1.1 to BR1.15 | Dedicated kubeconfig, namespace allow-list, too-much-access and missing-read checks in every scope (rules review per namespace, probe list cluster-wide), degraded optional sources, single-flight 5-minute re-check with its own 4 s limit, permanent stop, namespaced-only identity kit, pinned proxy names |
| Call arguments | BR2.1 to BR2.6 | Allow-listed namespace, UTC-only window of at most 6 hours, no wall clock |
| Overview and health | BR3.1 to BR3.6 | Unhealthy definition including restarts in the window, deterministic order, empty versus could-not-read, no Secrets |
| Redaction | BR4.1 to BR4.10 | Rule kinds, protected fields, joined scan, SHA versus key, base64, IP ranges, counts by kind only, one engine |
| Evidence shaping | BR5.1 to BR5.8 | Fixed order, full header, 10,000-byte limit including header, dropped-item count, stable references, degraded never looks empty |
| Adapter and transport | BR6.1 to BR6.11 | stdout only from transport, catch-all, 5 s budget, fail-closed frame, prompt hook validation, no mode switch, no AI, read-only tools only |
| Call log | BR7.1 to BR7.5 | Fixed path, 0600, rotation, one redacted line per call, failure never leaks |
| Test data | BR8.1 to BR8.2 | Seeded-only secrets, fixture mode offline |

## Sources

- `aidlc/spaces/default/intents/261015-ops-assistant/construction/functional-design/functional-design-questions.md` [Q1] to [Q11]
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/requirements-analysis/requirements.md`
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/domain-design/decisions.md` (ADR-003, ADR-008, ADR-010, ADR-011)
- `aidlc/spaces/default/intents/261015-ops-assistant/inception/units-generation/unit-of-work.md`
- `aidlc/spaces/default/memory/project.md` (Redactor kept separate from EvidencePipeline)

## Assumptions & Open Questions

The operator settled the six points below on 2026-11-03, after the first draft. They are decisions, not assumptions.

- Operator decision: the excess-access check also covers the `argocd` and `monitoring` namespaces (BR1.4). The `monitoring` Role grants get on services/proxy only for the Prometheus and Loki services, using resourceNames; services/proxy without resourceNames counts as too much access (BR1.4, BR1.13).
- Operator decision: the prompt's namespace must also be on the allow-list (BR6.5).
- Operator decision: if a re-check cannot complete, no reader runs until a re-check succeeds; that call returns "could not verify permissions: cluster unreachable", and the 5-minute clock does not reset (BR1.14).
- Operator decision: sources run concurrently, each with a 4-second timeout (BR6.3).
- Operator decision: IPv6 handling and the treatment of documentation and carrier-grade IPv4 ranges as public (BR4.6).
- Operator decision: 10 KB means 10,000 bytes (BR5.3).
- [assumption] The base64 rule's 16-character minimum (BR4.5) is a starting value that NFR Requirements may tune against false positives (requirements OQ4).
- [assumption] The re-check has its own 4-second limit and runs one at a time (BR1.9). Because Q5 puts the re-check before the 5-second budget, a call that needs a slow re-check can take up to about 9 seconds. Only calls more than 5 minutes after the last check are affected.
- [assumption] The method of the self-check (BR1.4, BR1.15): a rules review per namespace, an access-review probe list for the cluster scope, and an incomplete rules review counting as refuse.
- [assumption] The exact PROXY_RESOURCE_NAMES strings are pinned in Infrastructure Design, as Domain Design already planned.
