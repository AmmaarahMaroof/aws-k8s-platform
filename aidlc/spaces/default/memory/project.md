# Project-Level Rules

> Project-specific specialisation and corrections. Loaded after `org.md` and
> `team.md` as strict-additive guidance; contradictions with broader policy
> are rejected. Populated by practices-discovery and the self-learning loop.
>
> Use sparingly: most teams don't need a project layer. Reach for it
> only when this specific project needs stable, durable guidance beyond the
> team practice (for example, package-specific release checks or an additional
> regression suite for a legacy component).

## Way of Working

<!-- Project-specific specialisation. Example: -->
<!-- This monorepo requires package-scoped branch names and a package owner -->
<!-- review in addition to the team's normal merge policy. -->

## Walking Skeleton

<!-- Project-specific specialisation. Example: -->
<!-- The walking skeleton must exercise the legacy service adapter as well -->
<!-- as the new service boundary. -->

## Testing Posture

<!-- Project-specific specialisation. -->

- "Introduced by PR #34" is checked on the recorded game-day fixtures; a live game-day rerun has a new PR number, so its criterion is naming whichever PR introduced the bad tag. (learned 2026-10-16) <!-- cid:261015-ops-assistant:requirements-analysis:8e5cabd96ae75b0d83dcaeaa71872da59f99fc1a60e5b6ca6b020f95cdc02069 -->

## Guard Policy

<!-- Project-specific. Mode: strict, relaxed, or off. Strict here holds for every intent, whatever one person asks in chat; relaxed or off here applies to every intent whose policy came from its scope, unless the person sets another; changing this line changes it. A section under the retired Change Control heading, written by an earlier release, is still read. -->

## Deployment

<!-- Project-specific specialisation. -->

## Code Style

<!-- Project-specific specialisation. -->

## Tech Stack

<!-- Technology choices locked for this project. -->

## Decided

<!-- Decisions made in earlier stages that should not be re-asked. -->
<!-- Format: DECIDED: [decision] (Stage [slug], [date]) -->

## Scope Overrides

<!-- Custom scope rules for this project. -->

## Forbidden

<!-- Populated by practices-discovery affirmation gate. -->
<!-- Format: NEVER [behavior] (affirmed [date]) -->
<!-- Example: NEVER throw exceptions across service layer boundaries (affirmed 2026-05-17) -->

- NEVER write a real public IP address (such as the operator's home allow-list CIDR) into AI-DLC docs or the codekb; write it as `<home-ip>/32`. Private ranges (10.x, 172.16-31.x, 192.168.x) are fine. (learned 2026-10-16) <!-- cid:261015-ops-assistant:reverse-engineering:f80c86b0412b3841ebafca781b2a0d928443cb416b8afd13e92fa847cc6bff47 -->

## Mandated

<!-- Populated by practices-discovery affirmation gate. -->
<!-- Format: ALWAYS [behavior] (affirmed [date]) -->
<!-- Example: ALWAYS use Result<T,E> for fallible operations in service layer (affirmed 2026-05-17) -->

## Corrections

<!-- Project-specific corrections from human feedback. -->
<!-- Format: NEVER/ALWAYS [behavior] (learned [date]) -->
- Reverse Engineering scans the whole repo, with emphasis on the surfaces the ops assistant must read: Helm values and image tags, the API and checker CronJob, Argo CD, Prometheus/Alertmanager/Loki, CI and RBAC. (learned 2026-10-16) <!-- cid:261015-ops-assistant:reverse-engineering:b1e6295eb1c80babe7893846ac4a3c214a6c4ee89199cf2dc4239bb8e63229ce -->
- The ops assistant is a local read-only MCP server that Claude Code calls, not a standalone agent: the server makes no AI calls and only returns redacted evidence; reasoning, the report and fix preparation live in the Claude Code session. (learned 2026-10-16) <!-- cid:261015-ops-assistant:requirements-analysis:23111df4372168652327dcb08f4892350dce5c2dfc734e44cabf51b2e39d6ab0 -->
- When an answer changes the architecture mid-stage, reword the still-pending questions to fit it and add follow-ups for the gaps it opens, rather than asking questions that no longer apply. (learned 2026-10-16) <!-- cid:261015-ops-assistant:requirements-analysis:5d28b0a4496ce4c65bf4f44d46f99c11645344ad2aaa8cf6cf20e718ad63a576 -->
