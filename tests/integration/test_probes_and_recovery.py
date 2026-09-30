"""Integration tests for healthz/readyz probe behavior and dependency failure/recovery scenarios."""

import httpx
import pytest

from agent.classifier import classify
from agent.incidents import IncidentManager
from agent.models import ProbeResult, ServiceConfig, ServiceState
from agent.probes import ProbeRunner
from agent.state_manager import StateManager


PAYMENT_CONFIG = ServiceConfig(
    "payment-service",
    "http://payment-service:8001",
    critical_dependencies=("postgres", "redis"),
)

ORDER_CONFIG = ServiceConfig(
    "order-service",
    "http://order-service:8002",
    critical_dependencies=("postgres", "redis"),
)


@pytest.mark.asyncio
async def test_postgresql_failure_probe_behavior() -> None:
    """Proves: /healthz remains 200, /readyz becomes 503 on PostgreSQL failure."""
    def mock_transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            # Liveness is alive
            return httpx.Response(200, json={"status": "ok", "service": "payment-service"})
        if request.url.path == "/readyz":
            # Readiness fails because postgres is down
            return httpx.Response(
                503,
                json={
                    "status": "not_ready",
                    "service": "payment-service",
                    "checks": {
                        "postgres": {"ok": False, "detail": "connection refused"},
                        "redis": {"ok": True, "detail": "reachable"},
                    },
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_transport)) as client:
        runner = ProbeRunner(client=client)
        probe = await runner.probe(PAYMENT_CONFIG)

    assert probe.healthz_status == 200
    assert probe.readyz_status == 503
    assert probe.dependencies == {"postgres": False, "redis": True}

    state, reason = classify(PAYMENT_CONFIG, probe)
    assert state == ServiceState.ZOMBIE
    assert "POSTGRES" in reason


@pytest.mark.asyncio
async def test_redis_failure_probe_behavior() -> None:
    """Proves: /healthz remains 200, /readyz becomes 503 on Redis failure."""
    def mock_transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"status": "ok", "service": "order-service"})
        if request.url.path == "/readyz":
            return httpx.Response(
                503,
                json={
                    "status": "not_ready",
                    "service": "order-service",
                    "checks": {
                        "postgres": {"ok": True, "detail": "reachable"},
                        "redis": {"ok": False, "detail": "connection timeout"},
                    },
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_transport)) as client:
        runner = ProbeRunner(client=client)
        probe = await runner.probe(ORDER_CONFIG)

    assert probe.healthz_status == 200
    assert probe.readyz_status == 503
    assert probe.dependencies == {"postgres": True, "redis": False}

    state, reason = classify(ORDER_CONFIG, probe)
    assert state == ServiceState.ZOMBIE
    assert "REDIS" in reason


@pytest.mark.asyncio
async def test_service_crash_behavior() -> None:
    """Proves: /healthz non-200/unreachable marks service as DOWN."""
    def mock_transport(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_transport)) as client:
        runner = ProbeRunner(client=client)
        probe = await runner.probe(PAYMENT_CONFIG)

    assert probe.healthz_status is None
    assert probe.readyz_status is None

    state, _ = classify(PAYMENT_CONFIG, probe)
    assert state == ServiceState.DOWN


@pytest.mark.asyncio
async def test_recovery_lifecycle_integration() -> None:
    """Proves: after dependency recovery, /readyz returns 200 and state becomes HEALTHY."""
    # 1. Failing phase
    def failing_transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(
            503,
            json={
                "status": "not_ready",
                "checks": {"postgres": {"ok": False}, "redis": {"ok": True}},
            },
        )

    # 2. Recovered phase
    def healthy_transport(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(
            200,
            json={
                "status": "ready",
                "checks": {"postgres": {"ok": True}, "redis": {"ok": True}},
            },
        )

    sm = StateManager(failure_threshold=1, recovery_threshold=1)
    im = IncidentManager()

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing_transport)) as client:
        probe_fail = await ProbeRunner(client=client).probe(PAYMENT_CONFIG)
        status_fail = sm.observe(PAYMENT_CONFIG, probe_fail)
        im.process_statuses({"payment-service": status_fail})

    assert status_fail.state == ServiceState.ZOMBIE
    assert len(im.get_active_incidents()) == 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(healthy_transport)) as client:
        probe_ok = await ProbeRunner(client=client).probe(PAYMENT_CONFIG)
        status_ok = sm.observe(PAYMENT_CONFIG, probe_ok)
        im.process_statuses({"payment-service": status_ok})

    assert status_ok.state == ServiceState.HEALTHY
    assert len(im.get_active_incidents()) == 0
    assert len(im.get_resolved_incidents()) == 1
    assert im.get_resolved_incidents()[0].status == "RESOLVED"
