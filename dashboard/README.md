# HealthCheck Sentinel dashboard

An isolated, read-only React + Vite dashboard. No backend, Compose, Slack, or monitoring changes are required. Start the existing Docker Compose stack as usual first.

Requires Node.js 22.12+ (tested with Node 24). From the repository root:

```powershell
cd dashboard
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. The server binds only to localhost. Stop with Ctrl+C.

## Verification and built preview

```powershell
npm.cmd test
npm.cmd run build
npm.cmd run preview
```

Preview is at http://127.0.0.1:4173 and provides the same read-only proxy. These local servers are for development/presentation, not public production hosting. Serving `dist` alone requires an equivalent restricted proxy; it will not connect directly to backend ports.

## Data and safety

- `/api/status` proxies the existing `127.0.0.1:9101/status` snapshot.
- `/api/prometheus/targets` proxies `127.0.0.1:9090/api/v1/targets`.
- `/api/prometheus/resources` runs a fixed query for agent CPU and memory metrics.
- Only these exact GET routes are allowed. No credentials, write actions, log/restart actions, or Slack sending are added.
- Polling happens every four seconds after the previous request finishes; requests time out after five seconds. Data older than 30 seconds becomes UNKNOWN. Failed fetches do not imply a service is DOWN.
- HEALTHY, DEGRADED, ZOMBIE and DOWN are preserved from the real agent. RECOVERED denotes a historical recovery event, not current service health.
- PostgreSQL and Redis states are inferred from fresh service dependency checks, not direct database access. Conflicting probes are DEGRADED.
- Monitoring Agent health indicates fresh status publication. Prometheus health uses its own and the agent's scrape targets.
- Overall status is DOWN if any component is DOWN, otherwise DEGRADED for any DEGRADED/ZOMBIE component, UNKNOWN for missing evidence, otherwise HEALTHY.
- Slack displays actual transport receipts. Delivered does not prove a reviewer has read the message or that the connection remains healthy.
- Timeline and receipt totals cover only the records retained in the status snapshot. On fetch failure, history remains visible with a stale-data notice.
- Raw probe error strings, infrastructure URLs and credentials are not rendered. No external fonts, analytics, or assets are fetched.

For reviewers, show the healthy cards, then use the existing approved failure/recovery commands in the project documentation. Watch actual classification and incident receipts update; the dashboard does not inject failures. Show the real Slack channel alongside the dashboard.
