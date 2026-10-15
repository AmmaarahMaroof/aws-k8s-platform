# Incident review: deploy of a non-existent image tag (game day)

**Date:** 13 Oct 2026 · **Type:** planned game day · **Environment:** minikube (Argo CD, GitOps)
**Duration:** 19 minutes (bad merge 14:42, PR #34 → revert merged 15:01, PR #35)
**User impact:** API: none. `gameday.log` shows HTTP 200 throughout.
**Hidden impact:** no uptime checks ran from ~14:42 to ~15:01. The app looked healthy but wasn't doing its job.

## Summary
A change setting the image tag to one that doesn't exist (`gameday-does-not-exist`) passed CI and was merged to `main`. Argo CD synced it within a minute. New API pods couldn't pull the image, but the rolling update kept the old pods serving, so the API stayed up. The checker CronJob uses the same image, and with no old copy to fall back on, every check run failed, so site monitoring went silent without any of my alerts firing. Fixed with `git revert` through a PR, which Argo synced back.

## Timeline
| Time | Event |
|---|---|
| 14:00 | Baseline: healthy, all 200s |
| 14:42 | Bad tag merged to main (PR #34); CI passed |
| 14:42 | Argo synced; new API pod `api-76f95f447f-8w52f` created |
| 14:42–14:43 | New pod: `PodInitializing` → `ErrImagePull` → `ImagePullBackOff` |
| 14:42 onwards | Old API pods keep serving; impact logger still all 200s |
| ~14:45 | Checker CronJob runs also stuck in `ImagePullBackOff`; uptime checks stop |
| 14:56 | Prometheus: `kube_pod_container_status_waiting_reason{reason="ImagePullBackOff"} = 1` for **api** and **checker** |
| 14:58 | Built-in alert `KubePodNotReady` → **Pending** (16 min after the break) |
| 15:01 | Revert merged (PR #35). The alert never reached **Firing**; the earliest it could have fired was ~15:13 (31 min after the break) |
| ~15:02 | Argo synced the revert; API back on the good image; checker runs succeed again |

## Root cause
The image tag in `values-gitops.yaml` pointed to an image that didn't exist in ECR. Nothing in CI checks that a tag exists before merge, and Argo CD deploys whatever is on `main`. Because the API and the checker share one image tag, the bad value broke both. The API was protected by the rolling update; the checker, which starts a new pod on every run, was not.

## What went well
- **The rolling update protected users:** old API pods kept serving until new ones were Ready, so there were no failed requests.
- **Argo CD made the problem obvious** (app marked unhealthy, failing pod highlighted), and recovery was just a `git revert` through a normal PR.
- **Prometheus had the right signal:** `kube_pod_container_status_waiting_reason` showed exactly which pods were stuck and why.

## What didn't
- **CI let a non-existent image tag through:** lint and tests can't know whether a tag exists.
- **A silent failure:** uptime checking stopped, but none of my 3 alerts fired. `MonitoredSiteDown` needs new check results to fire, and there weren't any.
- **Slow detection:** the first built-in alert was only Pending after 16 minutes, and the incident was fixed (19 min) before any alert fired. Detection relied on me watching the screens.
- **Logs didn't help:** the containers never started, so Loki had nothing. Image-pull errors are Kubernetes *events*, not logs.
- **No notification path:** Alertmanager uses the chart's default receiver, so even a firing alert would have notified nobody.

## Actions
| Action | Why | Status |
|---|---|---|
| Alert when no uptime check has succeeded for 10 minutes | Catches the silent failure whatever the cause | open |
| Alert on pods stuck waiting (`kube_pod_container_status_waiting_reason > 0` for 5m) | Detects a bad rollout in ~5 min instead of 30+ | open |
| CI check that the image tag exists in ECR before merging changes to `values-gitops.yaml` | Stops this class of change reaching `main` at all | open |
| Collect Kubernetes events into Loki (Alloy `loki.source.kubernetes_events`) | So pull and scheduling errors are searchable next to logs | open |
| Configure an Alertmanager contact point (email or Slack) | A firing alert must reach a person | open |
