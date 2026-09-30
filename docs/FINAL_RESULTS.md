# Final submission verification

Measured 2026-09-30T12:29:16.062832+00:00 on Docker Desktop Linux, with localhost-only published ports and four-second polling. Prior measurements are preserved in validation-results.json and validation-before-tuning.json.

## Results actually run

- Automated suite: **52 passed in 7.70 seconds**, **74%** aggregate coverage.
- Healthy baseline: all six health/readiness endpoints HTTP 200; all three services HEALTHY.
- PostgreSQL and Redis: both affected services retained /healthz=200 while /readyz=503; exactly one shared ZOMBIE incident per dependency.
- Full payment process stop: DOWN, with unaffected order service remaining healthy.
- All three incidents recovered to RESOLVED; exactly three ACTIVE and three recovery messages were delivered to the local HTTP webhook receiver. Zero duplicate incidents or notifications.
- Brief Redis pause: zero new incidents/messages; alignment with a probe is not guaranteed. Deterministic full-pipeline transient suppression also passed.
- Prometheus: both scrape targets UP; seven required metric families available; live promtool configuration and all three rules valid.
- Compose configuration and Kubernetes base rendering passed; no Kubernetes cluster deployment.
- Credential-pattern scan: no matches in tracked/new non-ignored files; .env ignored. Pattern scanning is not an exhaustive secret audit.
- Post-run preflight: all checks passed; eight containers running, all configured healthchecks healthy; host ports bound to 127.0.0.1.

| Scenario | Injection to confirmation | Restart to recovery | Confirmation to webhook receipt | ACTIVE / recovery messages |
|---|---:|---:|---:|---:|
| postgresql | 5.64s | 5.58s | 35.1ms | 1 / 1 |
| redis | 7.31s | 5.63s | 32.8ms | 1 / 1 |
| payment-service | 14.86s | 9.06s | 21.5ms | 1 / 1 |

Agent CPU: **0.737% of one logical core**, measured from 0.453 process CPU seconds over **61.46s** between snapshots. Mean combined HTTP probe duration across the full run, including failures: **260.3ms**.

The zombie-detection and agent CPU targets passed on this machine. Full process-crash detection was 14.86s; do not present it as under ten seconds. Zero false positives were observed in these tested scenarios; no universal zero-false-positive guarantee is claimed.

## Remaining rubric gaps

No real Slack credentials are configured, so workspace delivery is not verified. Persistence, notification retries, distributed scale testing, and authenticated interactive restart actions are deferred. Kubernetes manifests are validated scaffolding. A recorded demo video and platform submission are submitter-owned tasks. Docker Desktop on this host has had recurring stale runtime socket startup failures; the engine is restored and running at handoff. Keep Docker running for the live demo.

## Where to start

DEMO.md contains the three-minute judge script and exact commands. docs/SUBMISSION.md is the submission draft; docs/RUBRIC.md maps evidence to all six criteria. scripts/preflight.py checks demo readiness without injecting failures. scripts/verify_slack.py checks private .env settings; --send-test sends an explicitly labeled test after credentials are configured.
