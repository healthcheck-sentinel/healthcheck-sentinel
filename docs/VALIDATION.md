# Validation record

Branch: `feature/system-validation`. Existing uncommitted work was preserved; no commit or history rewrite was performed.

## What existed

FastAPI payment/order/user services; PostgreSQL and Redis readiness checks; deterministic probes, state validation/classification, dependency correlation, incident contract/lifecycle, ChatOps payloads and signature helper; initial Compose, Prometheus and Kubernetes integration. Baseline: 35 tests passed in Linux Python 3.11, 17.02 seconds, 63% aggregate coverage. The deployed monitoring-agent was crash-looping because its image omitted `chatops`.

## Repairs

- Recovered Docker Desktop from stale Windows Unix-socket files for inference, secrets, networking and analytics. Exact runtime files were backed up through WSL; containers and volumes were preserved. No factory reset.
- Added missing ChatOps package to the agent image, psutil to dependencies, secret-safe Docker context exclusions, agent healthcheck, and service health startup ordering.
- Real outage testing exposed a second fault: PostgreSQL DNS failure starved unrelated Redis checks with the default uvloop resolver. Services now explicitly use asyncio; payment/order have bounded resolver retries. The rerun attributed each outage to exactly one dependency.
- Reused probe HTTP connections, removed double metric recording, reused CPU sampler, reset active incident gauges on recovery, and bounded metric reason labels.
- Preserved failure root cause during pending recovery; corrected ZOMBIE-to-DOWN transitions and DOWN root cause precedence; missing services cannot silently resolve incidents.
- Bounded database query/cleanup time; sanitized dependency error details. HTTPX INFO logging is suppressed in the agent so webhook URLs are not logged.
- Detect Slack API `ok:false`; record delivery outcomes/timing; keep failures from crashing monitoring. Added signature freshness checks. Removed inert action buttons and made placeholder handlers explicitly disabled.
- Added read-only status endpoint, real Docker scenario/measurement script, local HTTP webhook recorder, fixed-location shell/PowerShell controls, regression tests, actual alert rules and documentation.
- Kubernetes DB/Redis URLs now reference a Secret. All manifests render; no cluster deployment was performed.

## Automated checks

Final Windows Python 3.12.9 suite: **50 passed in 9.60 seconds; 74% aggregate coverage**. Existing tests cover all main outage/recovery flows; added regressions cover failure-mode changes, recovery evidence, absent-service handling, one-probe/one-metric, CPU sampler reuse, resolved gauges, Slack API rejection/replay, actual ASGI liveness/readiness routes and query-timeout cleanup.

Compose base/demo configuration: valid. Promtool: configuration valid and all three alert rules valid. Kubernetes base/development/production Kustomize renders: passed. Git whitespace check: passed.

## Final measured results

Docker Desktop Linux, three monitored services, four-second polling. All baseline health/readiness endpoints returned 200. PostgreSQL and Redis outages left payment/order liveness at 200 and readiness at 503, created one shared ZOMBIE incident per dependency, and sent exactly one ACTIVE and one recovery payload to the local HTTP recorder. Repeated polls created no duplicates. Stopping payment produced DOWN while order stayed healthy. The brief Redis pause created no incident or notification; poll alignment for that pause is not guaranteed.

| Scenario | Injection command to confirmation | Restart command to recovery | Confirmation to local webhook receipt |
|---|---:|---:|---:|
| postgresql | 6.93s | 5.65s | 19.6ms |
| redis | 7.40s | 5.67s | 20.8ms |
| payment-service | 14.84s | 8.99s | 23.8ms |

Agent CPU: **0.744% of one core**, 0.427 CPU seconds over **57.39 seconds** between agent snapshots during a 60-second measurement sleep. The snapshot interval differs from the sleep because samples are published after polling batches. Initial cadence CPU was 1.378%; both raw reports are retained.

Mean combined HTTP probe duration across the final run (including failure/timeouts): **292.1ms**. This is not a per-endpoint percentile. Both Prometheus targets are UP; all seven required metric families are present.

Zombie detection and CPU targets were achieved in this run, not guaranteed for every environment. Full process-crash detection took 14.84 seconds and is explicitly outside ten seconds; the requested ten-second target applies to zombie detection.

A final smoke rerun on the restored demo configuration also passed: PostgreSQL detection 6.56s, recovery 5.61s, one ACTIVE and one recovery message. Raw evidence: `demo-smoke.json`.

Final Docker verification: payment, order, user, PostgreSQL, Redis and monitoring-agent healthy; Prometheus and local webhook recorder running. Real Slack workspace delivery remains unverified because no token/webhook is configured.

## Remaining limits

No non-placeholder Slack webhook or bot token is configured: delivery is tested against a real local HTTP recorder, not a Slack workspace. Incidents/deduplication remain in memory, delivery attempts are at-most-once per transition, and failed deliveries require operator follow-up. Kubernetes is rendered scaffolding requiring dependencies, images and Secrets. A short real Redis pause may fall between polls; observed transient suppression is also tested deterministically. No claim of production perfection or universal latency/CPU guarantees is made.

## Final demo commands

```powershell
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
.\.venv\Scripts\python.exe scripts/docker_demo.py --full
docker compose -f docker-compose.yml -f docker-compose.demo.yml ps
```

The no-argument script demonstrates PostgreSQL only. `--full` also covers Redis, DOWN, short pause and a 60-second CPU sample. Every stopped dependency/service is started in a `finally` block. Inspect http://127.0.0.1:9101/status, http://127.0.0.1:18080/messages and http://localhost:9090.

## Modified and new files

Complete working-tree inventory, including inherited uncommitted integration work preserved during this task:

- `.dockerignore`
- `.env.example`
- `README.md`
- `agent/Dockerfile`
- `agent/chatops_dispatcher.py`
- `agent/classifier.py`
- `agent/incidents.py`
- `agent/integration_demo.py`
- `agent/main.py`
- `agent/metrics.py`
- `agent/probes.py`
- `agent/root_cause.py`
- `agent/state_manager.py`
- `agent/status_server.py`
- `chatops/actions.py`
- `chatops/messages.py`
- `chatops/slack_client.py`
- `docker-compose.demo.yml`
- `docker-compose.yml`
- `docs/VALIDATION.md`
- `docs/demo-smoke.json`
- `docs/architecture/README.md`
- `docs/runbooks/README.md`
- `docs/validation-before-tuning.json`
- `docs/validation-results.json`
- `kubernetes/README.md`
- `kubernetes/base/kustomization.yaml`
- `kubernetes/base/monitoring-agent.yaml`
- `kubernetes/base/order-service.yaml`
- `kubernetes/base/payment-service.yaml`
- `kubernetes/base/user-service.yaml`
- `kubernetes/overlays/development/kustomization.yaml`
- `kubernetes/overlays/production/kustomization.yaml`
- `prometheus/README.md`
- `prometheus/prometheus.yml`
- `prometheus/rules/alerts.yml`
- `scripts/benchmark_helper.py`
- `scripts/docker_demo.py`
- `scripts/fail_postgres.ps1`
- `scripts/fail_postgres.sh`
- `scripts/fail_redis.ps1`
- `scripts/fail_redis.sh`
- `scripts/recover_postgres.ps1`
- `scripts/recover_postgres.sh`
- `scripts/recover_redis.ps1`
- `scripts/recover_redis.sh`
- `scripts/restart_payment.ps1`
- `scripts/restart_payment.sh`
- `scripts/slack_recorder.py`
- `scripts/stop_payment.ps1`
- `scripts/stop_payment.sh`
- `services/order_service/Dockerfile`
- `services/order_service/checks.py`
- `services/order_service/config.py`
- `services/payment_service/Dockerfile`
- `services/payment_service/checks.py`
- `services/payment_service/config.py`
- `services/requirements.txt`
- `services/user_service/Dockerfile`
- `tests/Dockerfile`
- `tests/integration/test_incident_chatops_flow.py`
- `tests/integration/test_probes_and_recovery.py`
- `tests/unit/test_chatops.py`
- `tests/unit/test_metrics.py`
- `tests/unit/test_regressions.py`

Latest submission preparation adds localhost-only Compose publishing, redacted Slack evidence, a full-pipeline transient regression and an alert-redaction regression. The suite now has **52 passing tests** (7.70 seconds, 74% aggregate coverage). See `docs/RUBRIC.md`, `DEMO.md`, `docs/SUBMISSION.md` and `docs/SUBMISSION_CHECKLIST.md` for the final handoff. Fresh measurements are recorded separately in `docs/submission-validation.json` so prior evidence remains intact.
