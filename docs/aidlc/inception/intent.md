# Intent: ops assistant

## Problem
In my game day (docs/incidents/2026-10-13-bad-image-tag.md), I found the problem by watching screens myself; none of my alerts fired.
Investigating meant running kubectl, Prometheus queries and Loki searches by hand, across four tools.

## Goal
An AI agent that can investigate an incident using read-only tools (pods, events, logs, metrics, recent deploys),
explain the likely cause with evidence, and suggest a fix as a pull request.

## Rules (non-negotiable)
- The agent can only READ the cluster. No kubectl apply, delete, scale or exec.
- Any fix must go through Git as a pull request that a human reviews and merges.
- Secrets, passwords and connection strings must never be sent to the AI. Redact before sending.
- Every conclusion must show the evidence it came from.

## Success looks like
- On the bad-image-tag scenario, it names the cause: a non-existent image tag (ImagePullBackOff), introduced by PR #34
- It spots the hidden impact: the checker CronJob shares the image, so uptime checks stopped
- It proposes the right fix: revert PR #34
- It shows its evidence (events, metrics, the Git change), not just a conclusion