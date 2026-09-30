# Additional rubric coverage

The existing health routes, application routes, incident lifecycle, root-cause grouping and Slack delivery configuration remain in place. These additions provide resource and pool evidence plus an optional authenticated operator endpoint.

## Readiness and target resources

All three readiness endpoints now report memory headroom. Readiness returns 503 when less than the larger of 16 MiB or 5% of the memory limit is available; liveness remains independent. Linux cgroup v2 supplies container memory and CPU counters. Unlimited containers also check host available memory; platforms without cgroup v2 explicitly fall back to host memory and process CPU. CPU percent uses one logical core as 100%, not the entire machine. The first sample has no CPU percentage until two samples exist.

Payment and order use separate bounded health-probe pools for PostgreSQL and Redis, each with at most two clients and 250 ms acquisition timeout. Connection/query timeouts remain bounded. Failed connections are discarded; shutdown closes idle connections. The checks report actual pool usage and read-only backend connection capacity. These are health-probe pools, not fictitious business-application pools: business endpoints in this demo use in-memory stores. PostgreSQL capacity uses aggregate pg_stat_activity counts and Redis uses INFO clients. Capacity permission failures are reported without turning successful connectivity into an outage.

The monitoring agent ingests numeric resource/pool evidence, includes adjacent monitored services in incident evidence, and exports healthcheck_target_resource and healthcheck_dependency_pool_connections. Memory causes are scoped to their service so unrelated memory pressure is not falsely treated as one shared dependency. No Kubernetes cluster collector or deployment is implied.

## Interactive Slack logs and restart

This feature runs as a separate host operator process; the monitoring container has no Docker socket. Existing notifications retain their current format unless SLACK_ACTIONS_ENABLED=true. Set privately in .env:

- SLACK_SIGNING_SECRET: signing secret belonging to the app that posts alerts
- SLACK_ALLOWED_TEAM: exact workspace/team ID
- SLACK_ALLOWED_USERS: comma-separated operator user IDs
- SLACK_ALLOWED_CHANNELS: comma-separated allowed channel IDs
- SLACK_ACTIONS_ENABLED=true only after the endpoint is configured

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m chatops.interactive
```

It listens on 127.0.0.1:9102/slack/actions. Configure an operator-managed public HTTPS tunnel to **only this endpoint**, then set that HTTPS URL in the Slack app's Interactivity settings. Do not expose the agent status, metrics, application readiness or Docker API endpoints. The app posting alerts must own the interactive endpoint/signing secret; a standalone webhook belonging to a different app will not work.

After configuration, recreate only the agent to load the additive button flag:

```powershell
docker compose up -d --no-deps monitoring-agent
```

Slack requests require valid signatures, timestamps within five minutes, and explicit workspace/user/channel authorization. Only payment, order and user service logs/restarts are accepted. Restart buttons require Slack confirmation. Work is acknowledged promptly and executed in a bounded worker queue; results are ephemeral replies. Only Slack HTTPS response URLs are accepted, without redirects. Logs are capped and redact configured secrets, common credential fields, authorization headers and connection URLs. Docker commands use argument arrays and the existing local-engine allowlist. Persistent action deduplication lives in ignored .sentinel-state/slack-actions.sqlite3; restarts are throttled to once per service per minute. A crash after reserving an action can lose execution rather than repeat it; no exactly-once guarantee is made. Notification delivery/deduplication remains process-local as before.

Official interaction contract: https://docs.slack.dev/interactivity/handling-user-interaction/

## Reproducible verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/preflight.py
.\.venv\Scripts\python.exe scripts/measure_target_overhead.py --seconds 30
.\.venv\Scripts\python.exe scripts/validate_enhancements.py
```

The overhead experiment temporarily stops and restarts only the agent, with restoration in finally. It compares target process CPU in quiet baseline and normal polling windows; Docker healthchecks stay on in both. Results apply to the measured workload and machine, not all scales. The failure verifier actually stops PostgreSQL, Redis and payment one at a time, restores each in finally, checks liveness/readiness, shared root cause, deduplication, recovery and resource metrics, and sends notifications through the configured transport. A successful HTTP/API response is delivery evidence, not proof a person viewed a Slack message.

Live Slack button delivery needs the operator's IDs, signing secret and externally reachable HTTPS endpoint. Signed local integration tests do not substitute for a real workspace click. Kubernetes deployment remains optional and is not performed.


## Verified results from this implementation

- Complete suite: 103 tests passed, 83% coverage (including the original 65 unchanged tests).
- Live PostgreSQL ZOMBIE detection: 5.281 s; recovery 3.125 s.
- Live Redis ZOMBIE detection: 7.843 s; recovery 2.875 s.
- Full payment process DOWN detection: 15.438 s; recovery 8.766 s. The sub-ten-second claim applies to dependency-related zombies, not this process-stop scenario.
- Each scenario produced exactly one incident and one recovery notification with successful configured transport responses and no duplicates.
- Target incremental CPU in the paired 30-second windows: payment 0.167%, order 0.233%, user 0.133% of one core. Agent CPU: 0.812%. This is a quiet-host measurement; no loaded-scale guarantee is made.
- Signed local action integration exercised real Docker logs and an actual allowlisted user-service restart. Replies were captured locally; no log contents were posted to Slack during these action checks.
- Resource/pool Prometheus metrics and healthy service recovery were verified against rebuilt containers.
- Real Slack interactivity activation remains operator setup: the signing secret is present locally, but workspace/user/channel allowlists and the HTTPS endpoint have not yet been supplied. The button flag stays disabled until configured.

Machine-readable evidence: enhancement-validation.json and target-overhead.json. Historical validation documents describe earlier builds and remain unchanged.
