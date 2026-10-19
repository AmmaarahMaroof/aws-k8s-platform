<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-16T09:50:00Z — The ops assistant is a local read-only MCP server that Claude Code calls, not a standalone agent; the human reframed Q3/Q4 this way, so the AI, the report and fix preparation live in the Claude Code session and the server only returns redacted evidence.
- 2026-10-16T09:50:00Z — "Introduced by PR #34" is checked on recorded fixtures; a live game-day rerun will have a new PR number, so the live criterion is "names whichever PR introduced the bad tag".

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->
- 2026-10-16T09:50:00Z — Reworded Q5 (who opens the PR) and Q8 (limits as tool latency/output size instead of dollar cost) mid-stage, and added follow-ups Q10 (Git evidence source) and Q11 (what CI can test without an AI session), because the MCP-server answers changed what those questions meant.

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
- 2026-10-16T09:50:00Z — How the server reaches Prometheus/Loki under a get/list/watch-only identity (API-server service proxy with resourceNames vs operator-started port-forward) is left to design (OQ1).
