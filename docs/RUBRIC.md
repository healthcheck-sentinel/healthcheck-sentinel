# Rubric evidence and remaining gaps

| Criterion | Evidence | Honest boundary |
|---|---|---|
| Technical architecture (20%) | README diagram; distinct probes, validation, classification, correlation, incident manager and dispatcher | Single monitoring-agent instance |
| Reliability/security (20%) | Repeated observations; ACTIVE/RESOLVED; deduplication; bounded read-only checks; loopback-only host ports; .env/build exclusions; sanitized Slack evidence | In-memory incident state; delivery failure has no automatic retry; demo database defaults are not production credentials |
| Engineering depth (20%) | Real PostgreSQL/Redis outages, process crash, DNS-isolation fix, timing/CPU measurements and regression suite | Brief real pause may miss a poll; full pipeline transient suppression is deterministically tested |
| Developer experience (15%) | Docker Compose, preflight.py, named failure/recovery scripts, DEMO.md, submission draft | Requires Docker Desktop running and Python for host demo script |
| Scalability/efficiency (15%) | Concurrent HTTP checks, reused HTTP client, measured CPU, bounded labels | Three-service measurement only; no multi-agent coordination, history retention bound or scale test |
| Live demo/code (10%) | DEMO.md three-minute script; assertions and saved JSON measurements | Submitter still records/uploads video and completes platform-specific fields |

## Mission mapping

Deep readiness checks use PostgreSQL SELECT 1 and Redis PING. They do not write or lock application data. A service is ZOMBIE only when its process responds and readiness fails with explicit critical-dependency evidence. DOWN is an unreachable liveness endpoint. Optional/inconclusive problems are DEGRADED. Three failed observations confirm an outage and two successful observations confirm recovery.

A PostgreSQL or Redis outage shared by payment/order is grouped by normalized dependency name. One incident carries both services, dependency/root cause, state, timing and evidence. Notification delivery is deduplicated per incident transition. Metrics cover state, duration, failures, incidents, confirmation latency, agent CPU and RSS.

## Claims to avoid

Do not claim zero false positives universally, production-grade exactly-once notification, real Slack delivery without credentials, deployed Kubernetes, or safe remote restart controls. Restart/log actions are disabled rather than exposing arbitrary shell access. The submission can satisfy the demonstrated mission while explicitly disclosing these boundaries.
