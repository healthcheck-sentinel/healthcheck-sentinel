# Safe timed presentation demo

Run from the existing repository root in PowerShell with Docker Desktop running and all services healthy. This reuses the existing selected-service stop/start mechanism. No application route, probe, Docker configuration or Slack configuration changes. Normal Compose startup never enables it. No credentials or fabricated alerts are used.

Start the explicitly enabled 45-second payment-service failure:

```powershell
.\.venv\Scripts\python.exe scripts/safe_demo.py start
```

Restore immediately (in a second terminal if the first is counting down):

```powershell
.\.venv\Scripts\python.exe scripts/safe_demo.py restore
```

The service is automatically restarted after approximately 45 seconds from invocation. A detached local recovery helper is armed and acknowledged **before** stopping the selected container, so closing the foreground terminal does not disable recovery. Ctrl+C also requests recovery. Manual restore cancels that run's timer. An old timer cannot restore a later demo run. If Docker becomes unavailable, the helper retries when the local engine returns. No software can guarantee recovery while the computer/engine is unavailable; manual restore remains available after reopening Docker. Container startup does not read the demo's private bookkeeping files, so a normal Compose startup cannot inherit an injected failure flag.

Default target is payment-service. The optional --service argument accepts only payment-service, order-service or user-service; use the same target for restore. The optional --seconds argument is limited to 30 through 60. PostgreSQL, Redis and monitoring containers are never selected by this helper. It refuses remote Docker contexts and refuses to begin if the selected service is not already healthy. Local timing state is stored only in ignored .sentinel-state.

## Reviewer flow

1. Show http://127.0.0.1:9101/status with three HEALTHY services and your configured Slack channel.
2. Run start. Only payment-service stops; its health endpoint becomes unavailable. The agent calls this confirmed unhealthy state DOWN, not a literal UNHEALTHY label and not ZOMBIE. Explain that ZOMBIE is reserved for a responding process with broken critical dependencies.
3. Refresh status after repeated probes (allow roughly 15 seconds). Show one ACTIVE incident attributed to payment-service and one real Slack incident notification. Order/user should remain HEALTHY.
4. Keep the failed state visible; polling must not create duplicate notifications.
5. Either wait for automatic recovery or run restore. Starting the container is followed by repeated successful probes; allow another 5-15 seconds for HEALTHY and RESOLVED.
6. Show the matching Slack recovery notification and the resolved incident. These messages are sent only by the existing real monitoring/ChatOps path.

This is a local hackathon failure drill, not a production control endpoint. No GitHub push is part of this change.

## Verified locally

117 tests passed (the original 103 unchanged plus 14 new safety tests), with 83% existing package coverage. The live demo produced a real payment-service DOWN incident. The foreground process was deliberately terminated; the detached timer still restored payment-service, the incident resolved, and the configured Slack transport reported exactly one incident and one recovery delivery. Manual restore was also verified. Normal docker compose up -d and the existing preflight passed afterward, with all three monitored services HEALTHY. No existing tracked file was changed and nothing was pushed.
