"""Run a deterministic local incident-to-Slack integration simulation."""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from agent.chatops_dispatcher import ChatOpsEventDispatcher
from agent.main import MonitoringAgent
from agent.models import ProbeResult, ServiceConfig

START = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
REGISTRY = (
    ServiceConfig("payment-service", "http://payment", critical_dependencies=("postgres", "redis")),
    ServiceConfig("order-service", "http://order", critical_dependencies=("postgres", "redis")),
)


def _result(service: str, second: float, postgres_ok: bool) -> ProbeResult:
    return ProbeResult(
        service=service,
        timestamp=START + timedelta(seconds=second),
        healthz_status=200,
        readyz_status=200 if postgres_ok else 503,
        latency_ms=17.0,
        dependencies={"postgres": postgres_ok, "redis": True},
    )


class DemoProbeRunner:
    def __init__(self) -> None:
        self._pending: dict[str, list[ProbeResult]] = {}

    def set_batch(self, results: dict[str, list[ProbeResult]]) -> None:
        self._pending = {service: list(items) for service, items in results.items()}

    async def probe(self, config: ServiceConfig) -> ProbeResult:
        return self._pending[config.name].pop(0)


class DemoSlackTransport:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_message(self, payload: dict[str, Any], channel: str | None = None) -> None:
        self.messages.append(payload)


class NoopMetrics:
    def record_probe(self, service: str, result: ProbeResult) -> None:
        pass

    def record_status(self, status: Any) -> None:
        pass

    def record_incidents(self, incidents: list[Any]) -> None:
        pass

    def update_resource_usage(self) -> None:
        pass


async def run_demo() -> dict[str, Any]:
    probes = DemoProbeRunner()
    slack = DemoSlackTransport()
    agent = MonitoringAgent(
        registry=REGISTRY,
        failure_threshold=2,
        recovery_threshold=2,
        retry_delay_seconds=0,
        probe_runner=probes,
        metrics_collector=NoopMetrics(),
        chatops_dispatcher=ChatOpsEventDispatcher(slack_client=slack, channel="#demo-alerts"),
    )

    probes.set_batch({service.name: [_result(service.name, 0, True)] for service in REGISTRY})
    await agent.poll_once()

    failing = {
        service.name: [
            _result(service.name, 5.8, False),
            _result(service.name, 11.6, False),
        ]
        for service in REGISTRY
    }
    probes.set_batch(failing)
    await agent.poll_once()
    active_sample = copy.deepcopy(agent.incidents.get_active_incidents()[0].to_dict())

    repeated = {
        service.name: [
            _result(service.name, 12.0, False),
            _result(service.name, 13.0, False),
        ]
        for service in REGISTRY
    }
    probes.set_batch(repeated)
    await agent.poll_once()
    active_alert_count_after_repeat = sum(
        message.get("text", "").endswith("incident detected") for message in slack.messages
    )

    recovered = {
        service.name: [
            _result(service.name, 15.0, True),
            _result(service.name, 20.0, True),
        ]
        for service in REGISTRY
    }
    probes.set_batch(recovered)
    await agent.poll_once()
    resolved_sample = copy.deepcopy(agent.incidents.get_resolved_incidents()[0].to_dict())

    return {
        "active_incident": active_sample,
        "resolved_incident": resolved_sample,
        "slack_alert": slack.messages[0],
        "slack_recovery": slack.messages[1],
        "deduplication": {
            "active_alerts_after_repeated_failure_cycle": active_alert_count_after_repeat,
            "total_messages_after_recovery": len(slack.messages),
        },
    }


async def main() -> None:
    print(json.dumps(await run_demo(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())