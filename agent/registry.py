"""Default service registry, overridable with SERVICE_REGISTRY_JSON."""

from __future__ import annotations

import json
import os

from agent.models import ServiceConfig


def load_registry() -> tuple[ServiceConfig, ...]:
    """Load service definitions from JSON or use the local Compose defaults."""
    degraded_latency_ms = float(os.getenv("AGENT_DEGRADED_LATENCY_MS", "1500"))
    configured = os.getenv("SERVICE_REGISTRY_JSON")
    if configured:
        entries = json.loads(configured)
        return tuple(
            ServiceConfig(
                name=item["name"],
                base_url=item["base_url"].rstrip("/"),
                healthz_path=item.get("healthz_path", "/healthz"),
                readyz_path=item.get("readyz_path", "/readyz"),
                critical_dependencies=tuple(item.get("critical_dependencies", ())),
                degraded_latency_ms=float(item.get("degraded_latency_ms", degraded_latency_ms)),
            )
            for item in entries
        )

    return (
        ServiceConfig("payment-service", os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8001"), critical_dependencies=("postgres", "redis"), degraded_latency_ms=degraded_latency_ms),
        ServiceConfig("order-service", os.getenv("ORDER_SERVICE_URL", "http://localhost:8002"), critical_dependencies=("postgres", "redis"), degraded_latency_ms=degraded_latency_ms),
        ServiceConfig("user-service", os.getenv("USER_SERVICE_URL", "http://localhost:8003"), degraded_latency_ms=degraded_latency_ms),
    )