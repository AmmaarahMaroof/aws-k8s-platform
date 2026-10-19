<!-- INVARIANT: examples are single-line HTML comments so a fresh template parses to total=0 (MEMORY_EMPTY). Do NOT un-comment or split across lines. t100 guards this. -->
> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations
<!-- example: 2026-05-29T10:14:32Z — chose REST over GraphQL; the consuming team only needs CRUD, revisit if subscriptions land -->
- 2026-10-16T10:30:00Z — Session-side requirements (report format FR9, fix preparation FR10, session constraints FR11) are owned by InvestigationGuide, which ships the MCP prompt plus the operator guide and settings template; they are realised as instructions and docs, not server enforcement.
- 2026-10-16T10:30:00Z — Added a diagnose_image_pull tool (not in the Q5 list) because Q1 put diagnosis in the server and the session needs a way to call it.

## Deviations
<!-- example: 2026-05-29T10:14:32Z — skipped the optional caching layer the stage prose suggested; the dataset is small enough that it adds risk -->

## Tradeoffs
<!-- example: 2026-05-29T10:14:32Z — picked TDD over BDD this run; the team is unit-first and the domain is well-understood -->
- 2026-10-16T10:30:00Z — Split Redactor from EvidencePipeline even though Q3 named one pipeline; the call log and the fixture recorder must use the identical redaction engine without the response shaping.

## Open questions
<!-- example: 2026-05-29T10:14:32Z — confirm the retention window with compliance before the next stage hardens the schema -->
