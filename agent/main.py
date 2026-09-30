"""Concurrent polling loop for the deterministic monitoring agent with Prometheus observability."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone

from agent.chatops_dispatcher import ChatOpsEventDispatcher
from agent.incidents import IncidentManager
from agent.metrics import MetricsCollector, collector
from agent.models import ServiceConfig
from agent.probes import ProbeRunner
from agent.registry import load_registry
from agent.state_manager import StateManager
from agent.validator import StateValidator

log = logging.getLogger("monitoring-agent")


class MonitoringAgent:
    def __init__(
        self,
        registry: tuple[ServiceConfig, ...] | None = None,
        poll_interval_seconds: float | None = None,
        timeout_seconds: float | None = None,
        failure_threshold: int | None = None,
        recovery_threshold: int | None = None,
        retry_delay_seconds: float | None = None,
        probe_runner: ProbeRunner | None = None,
        metrics_collector: MetricsCollector | None = None,
        incident_manager: IncidentManager | None = None,
        chatops_dispatcher: ChatOpsEventDispatcher | None = None,
    ):
        failure_threshold = int(os.getenv("AGENT_FAILURE_THRESHOLD", "3")) if failure_threshold is None else failure_threshold
        recovery_threshold = int(os.getenv("AGENT_RECOVERY_THRESHOLD", "2")) if recovery_threshold is None else recovery_threshold
        self.registry = registry or load_registry()
        self.poll_interval_seconds = poll_interval_seconds if poll_interval_seconds is not None else float(os.getenv("AGENT_POLL_INTERVAL_SECONDS", "4"))
        timeout_seconds = timeout_seconds if timeout_seconds is not None else float(os.getenv("AGENT_TIMEOUT_SECONDS", "3"))
        retry_delay_seconds = retry_delay_seconds if retry_delay_seconds is not None else float(os.getenv("AGENT_RETRY_DELAY_SECONDS", "1"))
        self.probes = probe_runner or ProbeRunner(timeout_seconds=timeout_seconds)
        self.validator = StateValidator(failure_threshold, recovery_threshold, retry_delay_seconds)
        self.state_manager = StateManager(failure_threshold, recovery_threshold)
        self.metrics = metrics_collector or collector
        self.incidents = incident_manager or IncidentManager()
        self.chatops_dispatcher = chatops_dispatcher or ChatOpsEventDispatcher()
        self.snapshot: dict = {}

    async def _poll_service(self, config: ServiceConfig) -> None:
        initial = await self.probes.probe(config)
        status = self.state_manager.get(config.name)
        results = await self.validator.collect(
            config,
            initial,
            status.state,
            lambda: self.probes.probe(config),
        )
        for result in results:
            self.metrics.record_probe(config.name, result)
            self.state_manager.observe(config, result)

    async def poll_once(self) -> dict[str, dict]:
        await asyncio.gather(*(self._poll_service(config) for config in self.registry))
        for status in self.state_manager.statuses.values():
            self.metrics.record_status(status)

        # Correlate and manage incidents
        active_and_resolved = self.incidents.process_statuses(self.state_manager.statuses)
        self.metrics.record_incidents(active_and_resolved)
        await self.chatops_dispatcher.dispatch(active_and_resolved)
        self.metrics.update_resource_usage()

        statuses = {name: status.to_dict() for name, status in self.state_manager.statuses.items()}
        self.snapshot = {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "services": statuses,
            "incidents": [incident.to_dict() for incident in active_and_resolved],
            "notifications": self.chatops_dispatcher.deliveries,
            "process_cpu_seconds": time.process_time(),
            "process_wall_seconds": time.monotonic(),
        }
        return statuses

    async def run(self, stop: asyncio.Event | None = None, metrics_port: int | None = None) -> None:
        port = metrics_port or int(os.getenv("METRICS_PORT", "9100"))
        try:
            self.metrics.start_server(port=port)
            log.info("Prometheus metrics server started on port %d", port)
        except Exception as exc:
            log.warning("Could not start Prometheus metrics server: %s", exc)

        from agent.status_server import start_status_server
        status_server = start_status_server(self, int(os.getenv("STATUS_PORT", "9101")))
        stop = stop or asyncio.Event()
        try:
            while not stop.is_set():
                await self.poll_once()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self.poll_interval_seconds)
                except asyncio.TimeoutError:
                    pass
        finally:
            status_server.shutdown()
            status_server.server_close()
            await self.probes.aclose()



async def main() -> None:
    logging.basicConfig(
        level=os.getenv("AGENT_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    # HTTPX request logs can contain secret webhook URLs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    await MonitoringAgent().run()


if __name__ == "__main__":
    asyncio.run(main())