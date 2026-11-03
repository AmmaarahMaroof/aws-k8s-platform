# NFR Requirements Questions: U1 Safe core (`u1-safe-core`)

These cover only quality targets the requirements and the approved U1 Functional Design leave open. Already settled and not asked again: Python 3.12, `pytest` and `ruff` (requirements A1); the 5-second budget, 4-second source timeouts and 10,000-byte limit (NFR3, NFR5, BR6.3, BR5.3); the call log (BR7.x); read-only identity and redaction rules.

## Q1: How the server talks to the Kubernetes API

The design requires GET-only requests on an allow-listed set of paths (BR1.7, BR3.6), plus the self-review requests. The client choice decides how easily that can be enforced and tested.

A. The official `kubernetes` Python client, wrapped so only ClusterSession can call it
B. A small HTTP client of our own (for example `httpx`) that sends only allow-listed GETs and the two review requests; the official library is used only to load the kubeconfig
C. Our own HTTP client and our own kubeconfig loading, with no Kubernetes library at all
X. Other (please specify)

[Answer]:

## Q2: How `ops_mcp` dependencies are pinned

The repo installs ranges such as `ruff>=0.6,<1`. This server holds a cluster identity and reads production evidence, so supply-chain risk matters more here.

A. A separate `ops_mcp` requirements lock file with exact versions and hashes, installed with `--require-hashes`
B. Exact versions without hashes, in a separate `ops_mcp` requirements file
C. Ranges, in the repo's existing style
X. Other (please specify)

[Answer]:

## Q3: Coverage target for U1

The org default for this scope is 80% line coverage. U1 contains the safety core: the Redactor, the evidence pipeline and the start-up guard.

A. 80% line coverage for `ops_mcp/` as a whole
B. 80% overall, plus 95% branch coverage on the Redactor, EvidencePipeline and StartupGuard modules
X. Other (please specify)

[Answer]:

## Q4: Limit on raw response size before redaction

Redaction runs on everything a source returns before truncation (FR7.7). A very large API response could use up the 5-second budget in redaction alone.

A. Cap each raw source response at 2 MB; a larger one returns a could-not-read record ("response too large; narrow the window")
B. Cap at 5 MB, same behaviour
C. No cap; rely on the 4-second source timeout
X. Other (please specify)

[Answer]:

## Q5: Redaction speed target

A measurable target lets a test catch a slow redaction rule (for example a pattern that backtracks badly) before it breaks the 5-second budget.

A. The Redactor processes 2 MB of mixed text in at most 500 ms in CI, with no rule taking more than linear time on adversarial input
B. No separate target; the end-to-end 5-second budget test is enough
X. Other (please specify)

[Answer]:

## Q6: How many calls at once

Claude Code can send several tool calls in parallel. The design uses a fixed worker pool created at start-up (BR6.3, BR6.8).

A. 4 workers; extra calls wait, and waiting counts against each call's 5-second budget
B. 8 workers, same rule
X. Other (please specify)

[Answer]:

## Q7: Security scanning in the new CI workflow

U1 adds `.github/workflows/ops-assistant.yml` (pytest with coverage, then `ruff`). Extra scans would catch known-vulnerable dependencies or risky code early.

A. Add `pip-audit` on the `ops_mcp` dependencies; it fails the build on a known vulnerability
B. Add `pip-audit` and `bandit` (on `ops_mcp/` only)
C. No extra scans in U1
X. Other (please specify)

[Answer]:

## Q8: Seeing the server's health and error rate

The operation rules ask for at least one health metric and one error-rate metric. The call log records every call's outcome, but nothing summarises it.

A. The call log is enough; the operator guide shows a one-line command to count outcomes
B. Add a small read-only `ops_mcp stats` command that summarises the last N calls by outcome and duration from the call log
X. Other (please specify)

[Answer]:
