# Reviewer commands for real probe evidence

Run from the repository root with Docker Desktop running. The thin reviewer_demo.py entry point calls demo.py; scripts/demo_states.py is an internal lease writer, not a command-line interface.

```powershell
.\.venv\Scripts\python.exe reviewer_demo.py healthy
.\.venv\Scripts\python.exe reviewer_demo.py status
.\.venv\Scripts\python.exe reviewer_demo.py degraded
.\.venv\Scripts\python.exe reviewer_demo.py recover
.\.venv\Scripts\python.exe reviewer_demo.py zombie
.\.venv\Scripts\python.exe reviewer_demo.py recover
.\.venv\Scripts\python.exe reviewer_demo.py down
.\.venv\Scripts\python.exe reviewer_demo.py recover
```

Run one failure at a time and recover before the next. Status is read-only and displays actual HTTP probe evidence separately from Docker liveness. The real agent confirms incidents and the configured Slack transport sends lifecycle notifications; no fake Slack messages or fabricated probe return codes are used.

DEGRADED explicitly enables payment-service's latency middleware and writes a 45-second lease that delays actual health/readiness responses by two seconds. Both endpoints retain their original response status and dependency checks. The agent detects actual measured latency above its threshold and validates repeated failures. The lease expires even if the terminal closes. Normal Compose startup defaults SENTINEL_DEMO_ENABLED to 0; no .env change is needed. Recover clears the lease immediately. A later ordinary Compose startup removes the process-level opt-in as well.

ZOMBIE stops the real PostgreSQL container. Payment/order liveness stays available while readiness fails, and the agent attributes a shared incident to PostgreSQL. DOWN stops payment-service. These two commands intentionally leave the failure visible until recover; always run recover after presenting. The separate scripts/safe_demo.py helper remains available for a timed DOWN drill with a detached recovery watchdog (see SAFE_DEMO.md).

The old demo_overlay.py wrapper was unused and has been removed. Earlier demo-states-validation.json records an older synthetic-readiness implementation and is historical evidence, not validation of this command set. Current tests cover actual latency classification and incident/recovery flows.
