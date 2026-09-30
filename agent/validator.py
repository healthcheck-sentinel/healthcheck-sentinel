"""Collect delayed repeated probes before accepting failure or recovery."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from agent.classifier import classify
from agent.models import ProbeResult, ServiceConfig, ServiceState


class StateValidator:
    def __init__(self, failure_threshold: int = 3, recovery_threshold: int = 2, retry_delay_seconds: float = 1.0):
        if failure_threshold < 1 or recovery_threshold < 1 or retry_delay_seconds < 0:
            raise ValueError("Thresholds must be positive and retry delay cannot be negative.")
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self.retry_delay_seconds = retry_delay_seconds

    async def collect(
        self,
        config: ServiceConfig,
        initial: ProbeResult,
        current_state: ServiceState,
        probe: Callable[[], Awaitable[ProbeResult]],
    ) -> list[ProbeResult]:
        results = [initial]
        first_state, _ = classify(config, initial)
        if first_state in (ServiceState.DOWN, ServiceState.ZOMBIE):
            goal = self.failure_threshold
            is_failure = True
        elif current_state in (ServiceState.DOWN, ServiceState.ZOMBIE):
            goal = self.recovery_threshold
            is_failure = False
        else:
            return results

        consecutive = 1
        while consecutive < goal:
            await asyncio.sleep(self.retry_delay_seconds)
            result = await probe()
            results.append(result)
            state, _ = classify(config, result)
            matches = state in (ServiceState.DOWN, ServiceState.ZOMBIE) if is_failure else state in (ServiceState.HEALTHY, ServiceState.DEGRADED)
            consecutive = consecutive + 1 if matches else 0
            if not matches:
                return results
        return results