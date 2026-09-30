from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from agent.chatops_dispatcher import ChatOpsEventDispatcher
from agent.main import MonitoringAgent
from agent.models import ProbeResult, ServiceConfig, ServiceState

START = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
REGISTRY = (
    ServiceConfig("payment-service", "http://payment", critical_dependencies=("postgres", "redis")),
    ServiceConfig("order-service", "http://order", critical_dependencies=("postgres", "redis")),
)


class ScenarioProbes:
    def __init__(self) -> None:
        self.results: dict[str, ProbeResult] = {}

    def set_state(self, second: int, *, payment_postgres_ok: bool, order_postgres_ok: bool) -> None:
        for service, postgres_ok in (
            ("payment-service", payment_postgres_ok),
            ("order-service", order_postgres_ok),
        ):
            self.results[service] = ProbeResult(
                service=service,
                timestamp=START + timedelta(seconds=second),
                healthz_status=200,
                readyz_status=200 if postgres_ok else 503,
                latency_ms=18.0,
                dependencies={"postgres": postgres_ok, "redis": True},
            )

    async def probe(self, config: ServiceConfig) -> ProbeResult:
        return self.results[config.name]


class RecordingSlackTransport:
    def __init__(self, fail: bool = False) -> None:
        self.messages: list[dict[str, Any]] = []
        self.fail = fail

    def send_message(self, payload: dict[str, Any], channel: str | None = None) -> None:
        self.messages.append(payload)
        if self.fail:
            raise RuntimeError("Slack is unavailable")


class NoopMetrics:
    def record_probe(self, service: str, result: ProbeResult) -> None:
        pass

    def record_status(self, status: Any) -> None:
        pass

    def record_incidents(self, incidents: list[Any]) -> None:
        pass

    def update_resource_usage(self) -> None:
        pass


def make_agent(
    probes: ScenarioProbes,
    transport: RecordingSlackTransport,
) -> MonitoringAgent:
    dispatcher = ChatOpsEventDispatcher(slack_client=transport, channel="#alerts")
    return MonitoringAgent(
        registry=REGISTRY,
        failure_threshold=1,
        recovery_threshold=1,
        retry_delay_seconds=0,
        probe_runner=probes,
        metrics_collector=NoopMetrics(),
        chatops_dispatcher=dispatcher,
    )


def message_text(payload: dict[str, Any]) -> str:
    return "\n".join(
        block.get("text", {}).get("text", "")
        for block in payload.get("blocks", [])
    )


@pytest.mark.asyncio
async def test_healthy_services_create_no_slack_alert() -> None:
    probes = ScenarioProbes()
    probes.set_state(0, payment_postgres_ok=True, order_postgres_ok=True)
    transport = RecordingSlackTransport()
    agent = make_agent(probes, transport)

    statuses = await agent.poll_once()

    assert all(status["state"] == ServiceState.HEALTHY.value for status in statuses.values())
    assert agent.incidents.get_all_incidents() == []
    assert transport.messages == []


@pytest.mark.asyncio
async def test_postgresql_shared_failure_creates_one_active_incident_and_alert() -> None:
    probes = ScenarioProbes()
    probes.set_state(1, payment_postgres_ok=False, order_postgres_ok=False)
    transport = RecordingSlackTransport()
    agent = make_agent(probes, transport)

    await agent.poll_once()

    active = agent.incidents.get_active_incidents()
    assert len(active) == 1
    assert active[0].root_cause == "postgresql"
    assert active[0].state == "ZOMBIE"
    assert sorted(active[0].affected_services) == ["order-service", "payment-service"]
    assert len(transport.messages) == 1
    alert = transport.messages[0]
    text = message_text(alert)
    assert "INC-001" in alert["text"]
    assert "ZOMBIE" in text
    assert "postgresql" in text
    assert "payment-service" in text and "order-service" in text
    assert "Detection time" in text
    assert "Explanation" in text
    assert "postgres" in text


@pytest.mark.asyncio
async def test_repeated_failures_do_not_duplicate_active_alert() -> None:
    probes = ScenarioProbes()
    probes.set_state(1, payment_postgres_ok=False, order_postgres_ok=False)
    transport = RecordingSlackTransport()
    agent = make_agent(probes, transport)

    await agent.poll_once()
    probes.set_state(2, payment_postgres_ok=False, order_postgres_ok=False)
    await agent.poll_once()

    assert len(agent.incidents.get_active_incidents()) == 1
    assert len(transport.messages) == 1


@pytest.mark.asyncio
async def test_newly_affected_service_updates_incident_without_duplicate_alert() -> None:
    probes = ScenarioProbes()
    probes.set_state(1, payment_postgres_ok=False, order_postgres_ok=True)
    transport = RecordingSlackTransport()
    agent = make_agent(probes, transport)

    await agent.poll_once()
    probes.set_state(2, payment_postgres_ok=False, order_postgres_ok=False)
    await agent.poll_once()

    active = agent.incidents.get_active_incidents()
    assert len(active) == 1
    assert sorted(active[0].affected_services) == ["order-service", "payment-service"]
    assert len(transport.messages) == 1


@pytest.mark.asyncio
async def test_recovery_resolves_incident_and_sends_one_recovery_notification() -> None:
    probes = ScenarioProbes()
    probes.set_state(1, payment_postgres_ok=False, order_postgres_ok=False)
    transport = RecordingSlackTransport()
    agent = make_agent(probes, transport)
    await agent.poll_once()

    probes.set_state(10, payment_postgres_ok=True, order_postgres_ok=True)
    await agent.poll_once()
    await agent.poll_once()

    resolved = agent.incidents.get_resolved_incidents()
    assert len(resolved) == 1
    assert resolved[0].recovery_time == (START + timedelta(seconds=10)).isoformat()
    assert len(transport.messages) == 2
    recovery = transport.messages[1]
    text = message_text(recovery)
    assert recovery["text"] == "INC-001: resolved"
    assert "postgresql" in text
    assert "payment-service" in text and "order-service" in text
    assert "Recovery time" in text
    assert "Incident duration" in text


@pytest.mark.asyncio
async def test_slack_failure_does_not_stop_monitoring_or_lose_incident(caplog: pytest.LogCaptureFixture) -> None:
    probes = ScenarioProbes()
    probes.set_state(1, payment_postgres_ok=False, order_postgres_ok=False)
    transport = RecordingSlackTransport(fail=True)
    agent = make_agent(probes, transport)

    statuses = await agent.poll_once()

    assert len(agent.incidents.get_active_incidents()) == 1
    assert all(status["state"] == ServiceState.ZOMBIE.value for status in statuses.values())
    assert "Slack delivery failed for incident INC-001 (ACTIVE)" in caplog.text
    assert "incident state is preserved" in caplog.text