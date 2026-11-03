# Functional Design Questions: U1 Safe core (`u1-safe-core`)

These questions cover only what the requirements, the Domain Design and the unit plan leave open for U1. Settled points (for example GET-only access, redact before truncate, the fail-closed frame, and fake secrets only in `tests/ops_mcp/fixtures/seeded/`) are carried forward and not asked again.

## Q1: Namespace scope of `namespace_overview`

U1's only tool is the namespace overview. The requirements give it a namespace but do not say whether it can also summarise every namespace at once. The answer decides its arguments and how much the 10 KB limit has to hold.

A. A namespace is required; the tool covers exactly one namespace
B. The namespace is optional; with none given, it summarises every namespace the identity can read, with unhealthy namespaces first
X. Other (please specify)

[Answer]: A. One namespace. The namespace is required and the tool covers exactly that namespace (so the read-only identity only needs a namespaced Role, not cluster-wide access).

## Q2: How the time window is given

The requirement for explicit time (NFR8) says tools never read the wall clock, so recorded fixtures replay the same way. The tool still needs a window in some form.

A. Absolute only: required `since` and `until` as UTC ISO 8601 timestamps
B. A required `as_of` UTC timestamp plus a duration such as `30m` or `2h`; the window is `as_of` minus the duration up to `as_of`
C. Accept either form and normalise both to absolute `since`/`until` before any reader runs
X. Other (please specify)

[Answer]: A. Absolute only: required since and until as UTC ISO 8601 timestamps. Reject the call if since >= until, if either has no UTC offset, or if the window is longer than 6 hours.

## Q3: What counts as an "unhealthy" pod

Truncation keeps unhealthy items first (NFR3), and the overview lists unhealthy pods first. The exact test decides what survives when the 10 KB limit bites.

A. A pod is unhealthy if its phase is Pending, Failed or Unknown, or any container is not ready, or any container has a waiting or terminated reason other than `Completed`
B. As A, plus any container that restarted inside the window
X. Other (please specify)

[Answer]: B. As A (phase Pending/Failed/Unknown, any container not ready, any waiting/terminated reason other than Completed), plus any container that restarted inside the window, judged from the container's last-termination time and the explicit since/until (no wall clock).

## Q4: Missing read permissions at start-up

The start-up self-check (NFR1.2) refuses to serve when the identity has too much access. It does not say what happens when a read the tools need is missing, for example Argo CD `applications` or the Prometheus service proxy.

A. Refuse to start whenever any needed read is missing
B. Start anyway and mark only the affected sources as degraded; their tools return a per-source error (NFR6)
C. Refuse to start if core Kubernetes reads (pods, events, workloads) are missing; degrade the other sources
X. Other (please specify)

[Answer]: C. Refuse to start if the core Kubernetes reads (pods, events, workloads) are missing; degrade the other sources. Every tool output must state which sources are degraded and why (e.g. "Prometheus: not readable, missing permission"). A degraded source must never look like an empty result such as "no alerts".

## Q5: When the permission check runs

The server is started by Claude Code and can live for a whole session. RBAC could change while it runs.

A. Only once at start-up
B. At start-up, and again before a tool call when the last check is older than 5 minutes; a failed re-check stops the server serving
X. Other (please specify)

[Answer]: B. Start-up plus a re-check before a tool call when the last check is older than 5 minutes. Apply the same rules as at start-up: too much access or missing core reads → stop serving (every call returns the constant fail-closed frame); missing optional reads → update the degraded-sources list. Measure the 5 minutes with a monotonic clock inside the server; it never appears in tool output, so replays stay deterministic. The re-check runs before the tool's 5 s timer starts.

## Q6: Redaction count in the evidence header

Each response reports how many values were redacted (FR7.4). The kinds do not reveal the secrets themselves.

A. Total count only
B. Total plus a count per kind, for example `connection-string: 1, public-ip: 2`
X. Other (please specify)

[Answer]: B. Total plus per-kind counts. Report only kind names and counts, never positions, lengths, prefixes or hashes of redacted values.

## Q7: What the 10 KB limit measures

The per-tool limit (NFR3) is "at most 10 KB of text". The header and the redaction count can never be dropped.

A. The whole text the client receives, header included; the header's size is reserved first and items fill what is left
B. Only the evidence items; the header comes on top of the 10 KB
X. Other (please specify)

[Answer]: A. 10 KB measured as UTF-8 bytes of the whole text sent, header included. Reserve the header first; items fill the rest. If items were dropped, the header says how many.

## Q8: Where the call log lives and how long it is kept

The server writes one redacted line per call (NFR9). It must never write to stdout, stderr or the cluster.

A. A fixed file outside the repo, `~/.local/state/ops-mcp/calls.log`, rotated at 5 MB with 3 old files kept
B. A path set by an environment variable, defaulting to A, with the same rotation
C. A git-ignored file inside the repo, `.ops-mcp/calls.log`, with the same rotation
X. Other (please specify)

[Answer]: A. ~/.local/state/ops-mcp/calls.log, rotated at 5 MB, 3 old files kept, created with 0600 permissions. Tests pass a temporary path through the constructor (same injection as R-07); there is no environment variable to change it.

## Follow-up questions (ambiguity analysis)

## Q9: Which namespaces the self-check covers (follows from Q1)

With a namespaced Role only, start-up has no namespace from a call yet. A Role with write or `secrets` access in one namespace is invisible to a cluster-wide check. So the server needs to know which namespaces to check.

A. A fixed list of investigable namespaces in the server's settings (for the game day, `uptime`). Start-up and every re-check run the too-much-access and core-read checks in each listed namespace. A call naming any other namespace is rejected as an argument error.
B. Start-up checks only cluster-wide access. The core reads are checked per call for the namespace it names, and a namespace that cannot be read returns a "not readable" error record.
X. Other (please specify)

[Answer]: X. Other: A, with details: a fixed allow-list of namespaces, passed as a server argument in .mcp.json (default: uptime). Start-up and every re-check run the self-check cluster-wide AND in each listed namespace: write verbs or secrets access in either place → refuse; missing core reads in a listed namespace → refuse. An empty or invalid list (not DNS-1123) → refuse to start. A call naming any namespace not on the list is rejected as an argument error.

## Q10: Timestamp offsets (follows from Q2)

A. Only `Z` or `+00:00` is accepted; any other offset is rejected
B. Any explicit offset is accepted and converted to UTC; only timestamps with no offset are rejected
X. Other (please specify)

[Answer]: A. Only `Z` or `+00:00` is accepted; any other offset is rejected

## Q11: After a failed re-check (follows from Q5)

A. Stopping is permanent: the server keeps returning the fail-closed frame until it is restarted, and the next start runs the full start-up check
B. Later re-checks keep running, and a re-check that passes resumes serving
X. Other (please specify)

[Answer]: A. Stopping is permanent: the server keeps returning the fail-closed frame until it is restarted, and the next start runs the full start-up check
