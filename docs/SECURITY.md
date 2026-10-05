# Security notes

## Image vulnerability scanning

Every image is scanned twice:

1. **CI (GitHub Actions + Trivy)**: the build fails on any **critical** vulnerability that has a fix available.
2. **ECR scan on push**: every image pushed to the registry is scanned, including vulnerabilities with no fix yet.

The two scanners use different vulnerability databases, so their CVE lists and counts don't always match. Both are reviewed.

## Triage log

### 5 Oct 2026: Perl fixes released, CI gate blocked the build

Debian released `perl-base 5.36.0-7+deb12u4`, fixing critical Perl CVEs that had no fix at the 30 Sep triage.
Because a fix now existed, the CI Trivy gate (`--ignore-unfixed`) **failed the build automatically** until the image was rebuilt.

| CVE (as reported by Trivy) | Package | Severity | Installed | Fixed in | Action |
|---|---|---|---|---|---|
| CVE-2026-13221 | perl-base | Critical | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | ✅ Fixed |
| CVE-2026-42496 | perl-base | Critical | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | ✅ Fixed |
| CVE-2026-8376  | perl-base | Critical | 5.36.0-7+deb12u3 | 5.36.0-7+deb12u4 | ✅ Fixed |

**Change:** the Dockerfile now runs `apt-get upgrade -y` instead of upgrading individual packages, so all pending Debian security updates are applied on every build.
**Trade-off:** builds are slightly less reproducible (package versions can change between builds), in exchange for not shipping known, fixable vulnerabilities.

### 30 Sep 2026: image `uptime-monitor:703b328` → `a2a3bad`

ECR reported 4 critical, 15 high, 11 medium and 4 low findings on `703b328`.
All critical findings were in **base-image OS packages**, not application code.

| CVE (as reported by ECR) | Package | Severity | Fix available at the time? | Action |
|---|---|---|---|---|
| CVE-2026-75803 | openssl 3.0.20 | Critical | Yes (3.0.22) | ✅ **Fixed** in `a2a3bad`: upgraded `openssl` and `libssl3` |
| CVE-2026-57433 | perl 5.36.0 | Critical | No | ⚠️ Accepted risk at the time (fix later released, see 5 Oct) |
| CVE-2026-12087 | perl 5.36.0 | Critical | No | ⚠️ Accepted risk at the time (fix later released, see 5 Oct) |
| CVE-2026-13221 | perl 5.36.0 | Critical | No | ⚠️ Accepted risk at the time (fix later released, see 5 Oct) |

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
- The Docker image applies all pending Debian security updates at build time
- ECR tags are **immutable**, so each tag always maps to one exact build
- Images are scanned on push; old images are removed by a lifecycle policy
- Containers run as a **non-root user**
- No long-lived AWS access keys: people use short-lived console sign-in credentials, and CI uses OIDC with a read-only role

## Follow-ups

- [ ] Push the rebuilt image to ECR and record its scan results here
- [ ] Rebuild the image regularly (`docker build --pull`) to pick up base-image patches
- [ ] Consider moving to a newer Debian base image or a smaller runtime image to reduce OS packages