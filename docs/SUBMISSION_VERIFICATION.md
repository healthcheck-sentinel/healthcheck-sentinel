# Final reviewer verification

Verified 1 October 2026 (Asia/Kolkata), against local branch `feature/system-validation`, commit `43a8e0c`, plus the uncommitted dashboard. No application code, tests, secrets or Compose configuration changed during this verification.

## Results

- Full Python suite: **141 passed**, **85% aggregate coverage**, 10.30 seconds. One existing Starlette/httpx deprecation warning.
- Dashboard: **9 tests passed**; Vite production build passed. JavaScript bundle 232.42 kB (72.81 kB gzip), CSS 8.53 kB (2.61 kB gzip).
- `npm audit` in dashboard: zero reported vulnerabilities. This is not an exhaustive security audit.
- Compose syntax and normal startup passed. Six configured container healthchecks healthy; Prometheus and the optional local webhook recorder running (neither has a Docker healthcheck).
- All six application `/healthz` and `/readyz` endpoints returned success after recovery. All three agent service states HEALTHY.
- Prometheus: both scrape targets UP; configuration and all three rules passed promtool validation.
- Dashboard opened in the browser with live data. Its page and all three API proxy routes returned 200. POST status requests returned 405 and unknown API routes returned 404.
- Submission-file credential scan: no configured long-secret or credential-pattern matches across 141 tracked/untracked, non-ignored files. `.env`, virtual environment, node_modules and build output are ignored. This check is not a complete history/security audit.

## Real reviewer scenarios

| Scenario | Incident | First observed failure to confirmation | Final lifecycle | Delivery receipts |
|---|---|---:|---|---|
| PostgreSQL outage / ZOMBIE | INC-006 | 3.036s | RESOLVED | 1 ACTIVE + 1 RESOLVED, delivered |
| Payment process stop / DOWN | INC-007 | 8.020s | RESOLVED | 1 ACTIVE + 1 RESOLVED, delivered |
| Payment latency / DEGRADED | INC-008 | 6.033s | RESOLVED | 1 ACTIVE + 1 RESOLVED, delivered |

These timings start at the agent's first failure observation, not at the injection command. ZOMBIE retained healthz=200 with readyz=503 and one shared PostgreSQL incident affecting Order and Payment. DEGRADED retained both HTTP statuses at 200 while measured latency exceeded the threshold. All recoveries passed. Repeated polling produced no duplicate delivery receipts for these three incidents. Receipts prove transport acceptance, not human visibility in Slack.

Normal `docker compose up -d` restored `SENTINEL_DEMO_ENABLED=0` after testing. No failure remains enabled. A fresh sample measured **0.663% agent CPU of one logical core over 44.26 seconds**. This does not measure target-service probe overhead or guarantee future load performance. Redis failure is covered by the existing automated suite and prior local validation, not reinjected in this pass.

## Submission considerations

- At verification time, the dashboard and this report were uncommitted. The subsequent submission update includes them on `feature/system-validation`; use that branch when reviewing the complete project.
- Interactive Slack buttons still require operator allowlists and HTTPS interactivity setup. Ordinary incident/recovery delivery passed.
- Incident/deduplication state is in memory; durable persistence and delivery retries remain future work.
- Kubernetes manifests remain optional; no cluster was deployed.
- Compose reports the preserved optional webhook recorder as an orphan when starting only the base configuration. It is an existing demo helper, not a failed service. It was not removed.

## Reviewer startup

From the repository root, with Docker Desktop running:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe scripts/preflight.py
npm.cmd --prefix dashboard ci
npm.cmd --prefix dashboard run dev
```

Open http://127.0.0.1:5173 and the configured Slack channel. If port 5173 is occupied by the already-running dashboard, reuse it.

In a second terminal at the repository root:

```powershell
.\.venv\Scripts\python.exe reviewer_demo.py healthy
.\.venv\Scripts\python.exe reviewer_demo.py zombie
.\.venv\Scripts\python.exe reviewer_demo.py recover
```

Always recover before another scenario or after an interrupted presentation.
