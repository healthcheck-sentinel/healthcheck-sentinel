"""Concurrent polling loop for the deterministic monitoring agent."""

from __future__ import annotations

import asyncio
import os

from agent.models import ServiceConfig, ServiceState
from agent.probes import ProbeRunner
from agent.registry import load_registry
from agent.state_manager import StateManager
from agent.validator import StateValidator


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
    ):
        failure_threshold = failure_threshold or int(os.getenv("AGENT_FAILURE_THRESHOLD", "3"))
        recovery_threshold = recovery_threshold or int(os.getenv("AGENT_RECOVERY_THRESHOLD", "2"))
        self.registry = registry or load_registry()
        self.poll_interval_seconds = poll_interval_seconds if poll_interval_seconds is not None else float(os.getenv("AGENT_POLL_INTERVAL_SECONDS", "30"))
        timeout_seconds = timeout_seconds if timeout_seconds is not None else float(os.getenv("AGENT_TIMEOUT_SECONDS", "3"))
        retry_delay_seconds = retry_delay_seconds if retry_delay_seconds is not None else float(os.getenv("AGENT_RETRY_DELAY_SECONDS", "1"))
        self.probes = probe_runner or ProbeRunner(timeout_seconds=timeout_seconds)
        self.validator = StateValidator(failure_threshold, recovery_threshold, retry_delay_seconds)
        self.state_manager = StateManager(failure_threshold, recovery_threshold)

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
            self.state_manager.observe(config, result)

    async def poll_once(self) -> dict[str, dict]:
        await asyncio.gather(*(self._poll_service(config) for config in self.registry))
        return {name: status.to_dict() for name, status in self.state_manager.statuses.items()}

    async def run(self, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        while not stop.is_set():
            await self.poll_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.poll_interval_seconds)
            except asyncio.TimeoutError:
                pass


async def main() -> None:
    await MonitoringAgent().run()


if __name__ == "__main__":
    asyncio.run(main())