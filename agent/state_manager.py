"""Evidence-preserving state machine with failure and recovery thresholds."""

from __future__ import annotations

from agent.classifier import classify
from agent.events import EventEmitter, StateChangeEvent
from agent.models import ProbeResult, ServiceConfig, ServiceState, ServiceStatus


class StateManager:
    def __init__(self, failure_threshold: int = 3, recovery_threshold: int = 2, emitter: EventEmitter | None = None):
        if failure_threshold < 1 or recovery_threshold < 1:
            raise ValueError("Thresholds must be positive.")
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self.emitter = emitter or EventEmitter()
        self.statuses: dict[str, ServiceStatus] = {}

    def get(self, service: str) -> ServiceStatus:
        return self.statuses.setdefault(service, ServiceStatus(service=service))

    def observe(self, config: ServiceConfig, result: ProbeResult) -> ServiceStatus:
        status = self.get(config.name)
        candidate, reason = classify(config, result)
        status.evidence = result

        failed = candidate in (ServiceState.DOWN, ServiceState.ZOMBIE)
        currently_failed = status.state in (ServiceState.DOWN, ServiceState.ZOMBIE)
        if not currently_failed and failed:
            if status.consecutive_failures == 0:
                status.first_failure_observed = result.timestamp
            status.consecutive_failures += 1
            status.consecutive_successes = 0
            if status.consecutive_failures >= self.failure_threshold:
                status.failure_confirmed_at = result.timestamp
                if status.first_failure_observed:
                    status.detection_time_seconds = (result.timestamp - status.first_failure_observed).total_seconds()
                self._transition(status, candidate, reason, result)
            else:
                status.reason = f"Unconfirmed {candidate.value} probe ({status.consecutive_failures}/{self.failure_threshold}): {reason}"
            return status

        if currently_failed and not failed:
            if status.consecutive_successes == 0:
                status.recovery_first_observed = result.timestamp
            status.consecutive_successes += 1
            status.consecutive_failures = 0
            if status.consecutive_successes >= self.recovery_threshold:
                status.recovery_confirmed_at = result.timestamp
                self._transition(status, candidate, reason, result)
            else:
                status.reason = f"Recovery pending ({status.consecutive_successes}/{self.recovery_threshold}): {reason}"
            return status

        if failed:
            status.consecutive_failures = min(status.consecutive_failures + 1, self.failure_threshold)
            status.consecutive_successes = 0
            return status

        status.consecutive_failures = 0
        status.consecutive_successes = 0
        if candidate != status.state:
            self._transition(status, candidate, reason, result)
        else:
            status.reason = reason
        return status

    def _transition(self, status: ServiceStatus, state: ServiceState, reason: str, result: ProbeResult) -> None:
        previous = status.state
        status.state = state
        status.reason = reason
        status.consecutive_failures = 0
        status.consecutive_successes = 0
        self.emitter.emit(StateChangeEvent(
            service=status.service,
            previous_state=previous,
            current_state=state,
            timestamp=result.timestamp,
            reason=reason,
            evidence=result,
        ))