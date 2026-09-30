# Observability

The agent exports probe, confirmed state, incident, process CPU and RSS metrics on port 9100. Prometheus scrapes it every five seconds. See the root README for metric names, semantics, queries and measured demo instructions. Rules cover ZOMBIE, DOWN and an unavailable monitor; the agent owns ChatOps notifications.
