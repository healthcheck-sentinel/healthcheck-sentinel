# Three-minute demo and recording guide

## Before recording

Start Docker Desktop and run from the repository root:

```powershell
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
.\.venv\Scripts\python.exe scripts/preflight.py
```

Open http://127.0.0.1:9101/status, http://127.0.0.1:18080/messages and http://localhost:9090. Keep .env and terminals containing credentials off screen. Local webhook recording is the default; call it a local receiver, not a Slack workspace.

## 0:00-0:30 — Explain the failure mode

“A green liveness endpoint does not mean a service can handle requests. Sentinel catches services whose process is alive but critical dependencies are broken.”

Show all three services HEALTHY and the README architecture. Explain that payment/order share PostgreSQL and Redis.

## 0:30-1:45 — Run the real outage/recovery

```powershell
.\.venv\Scripts\python.exe scripts/docker_demo.py --output docs/recording-demo.json
```

“This script stops the actual PostgreSQL container. Both applications still return 200 for liveness and 503 for readiness. After repeated checks, Sentinel confirms ZOMBIE, identifies PostgreSQL as the shared root cause and creates one incident.”

Show the console's endpoint results and incident evidence in /status. During the hold, refresh the local receiver: one ACTIVE payload. The script automatically restores PostgreSQL, confirms recovery and checks exactly one recovery payload.

## 1:45-2:30 — Show evidence

Show the resolved incident, two notification receipts, and metrics. In Prometheus run:

```
healthcheck_service_status == 1
healthcheck_active_incidents
healthcheck_process_cpu_percent
```

“The recorded full run also tested Redis, a complete service crash, transient behavior and duplicate suppression. Zombie detection was below ten seconds. Agent CPU was 0.74% of one core on this machine.”

## 2:30-3:00 — Close honestly

“Monitoring is entirely deterministic. Slack webhook and bot delivery are implemented; this demo uses a local HTTP receiver unless workspace credentials are configured. Kubernetes manifests are validated but not deployed, and incident storage is currently in memory.”

Mention 52 passing tests and point judges to docs/VALIDATION.md. Record the screen with your normal screen recorder; this guide is not a generated video. Preview the recording and check audio and link permissions before submission.

## Emergency recovery

```powershell
docker compose start postgres redis payment-service
```

If Docker reports a missing Linux-engine pipe, start Docker Desktop and wait for its engine. The prior host issue involved stale runtime socket files; do not factory-reset Docker or erase volumes to fix a demo issue.
