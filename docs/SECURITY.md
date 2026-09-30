# Security notes

## Image vulnerability scanning

Every image is scanned twice:

1. **CI (GitHub Actions + Trivy)**: the build fails on any **critical** vulnerability that has a fix available.
2. **ECR scan on push**: every image pushed to the registry is scanned, including vulnerabilities with no fix yet.

## Triage log

### 30 Sep 2026: image `uptime-monitor:703b328` → `a2a3bad`

ECR reported 4 critical, 15 high, 11 medium and 4 low findings on `703b328`.
All critical findings were in **base-image OS packages**, not application code.

| CVE | Package | Severity | Fix available? | Action |
|---|---|---|---|---|
| CVE-2026-75803 | openssl 3.0.20 | Critical | Yes (3.0.22) | ✅ **Fixed** in `a2a3bad`: Dockerfile upgrades `openssl` and `libssl3` |
| CVE-2026-57433 | perl 5.36.0 | Critical | No | ⚠️ **Accepted risk**: Perl is not executed by the application |
| CVE-2026-12087 | perl 5.36.0 | Critical | No | ⚠️ **Accepted risk**: Perl is not executed by the application |
| CVE-2026-13221 | perl 5.36.0 | Critical | No | ⚠️ **Accepted risk**: Perl is not executed by the application |

**Result after fix (`a2a3bad`):**

| Severity | Before | After |
|---|---|---|
| Critical | 4 | 3 |
| High | 15 | 11 |
| Medium | 11 | 7 |
| Low | 4 | 2 |

## Controls in place

- CI blocks merges when tests fail or a fixable critical vulnerability is found
- `main` is protected: changes only via pull requests with passing checks
- ECR tags are **immutable**, so each tag always maps to one exact build
- Images are scanned on push; old images are removed by a lifecycle policy
- Containers run as a **non-root user**
- No long-lived AWS access keys; the CLI uses short-lived console sign-in credentials

## Follow-ups

- [ ] Re-check the Perl CVEs weekly and rebuild when Debian publishes fixes
- [ ] Rebuild the image regularly (`docker build --pull`) to pick up base-image patches
- [ ] Consider moving to a newer Debian base image or a smaller runtime image to reduce OS packages