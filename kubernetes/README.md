# Kubernetes deployment scaffold

Use Docker Compose for the primary hackathon demo. These manifests are optional and require a working cluster, locally loaded or registry-published images, and separately provisioned PostgreSQL/Redis reachable at the configured URLs.

1. Build the Compose application images, then load them into your cluster or replace image references with pushed tags.
2. Create namespace `healthcheck-sentinel`.
3. Create a Secret named `sentinel-dependencies` in that namespace with keys `PAYMENT_DB_URL`, `ORDER_DB_URL`, `PAYMENT_REDIS_URL`, and `ORDER_REDIS_URL`. Supply values through a private local env file or your secret manager. Never commit the secret or print its values.
4. Render with `kubectl kustomize kubernetes/base`, then apply with `kubectl apply -k kubernetes/base` after the dependencies and images are ready.

Payment/order use `/healthz` as liveness and `/readyz` as readiness. Dependency outages keep the process alive while removing traffic. Agent replicas must remain one because incident and notification state is in memory.

The agent does not receive cluster credentials or a restart endpoint. Authenticated operators can use:

```sh
kubectl -n healthcheck-sentinel rollout restart deployment/payment-service
kubectl -n healthcheck-sentinel rollout status deployment/payment-service
kubectl -n healthcheck-sentinel logs deployment/payment-service --tail=100
```

Use namespace-scoped operator RBAC for deployments; do not expose these commands as unauthenticated Slack actions. Slack secrets can be supplied to the agent through a separately managed Secret. Monitoring a load-balanced service is not per-pod monitoring. Development/production overlays currently inherit the base; they are not production hardening profiles.
