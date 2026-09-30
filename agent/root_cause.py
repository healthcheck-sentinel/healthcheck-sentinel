"""Deterministic root-cause correlation and explanation generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from agent.dependency_graph import DependencyGraph, normalize_dependency_name
from agent.models import ProbeResult, ServiceState, ServiceStatus


@dataclass(frozen=True)
class CorrelatedFailure:
    """Represents a grouped failure attributed to a single root cause."""

    root_cause: str
    state: str
    affected_services: list[str]
    explanation: str
    evidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    first_failure_time: str | None = None
    confirmation_time: str | None = None
    detection_time_seconds: float | None = None


class RootCauseAnalyzer:
    """Deterministic, dependency-aware root-cause analyzer."""

    def __init__(self, dependency_graph: DependencyGraph | None = None) -> None:
        self.graph = dependency_graph or DependencyGraph()

    def identify_service_root_causes(self, status: ServiceStatus | dict[str, Any]) -> list[str]:
        """Identify candidate root causes for a single service failure."""
        if isinstance(status, ServiceStatus):
            state_val = status.state.value if hasattr(status.state, "value") else str(status.state)
            evidence = status.evidence
            service = status.service
        else:
            state_val = status.get("state", "HEALTHY")
            service = status.get("service", "unknown")
            ev_raw = status.get("evidence")
            evidence = ProbeResult(**ev_raw) if isinstance(ev_raw, dict) else ev_raw

        if state_val == ServiceState.HEALTHY.value:
            return []

        causes: list[str] = []

        # Check dependency failures from probe evidence
        if evidence and hasattr(evidence, "dependencies") and evidence.dependencies:
            for dep_name, is_healthy in evidence.dependencies.items():
                if is_healthy is False:
                    causes.append(normalize_dependency_name(dep_name))

        if causes:
            return causes

        if state_val == ServiceState.DOWN.value:
            return [service]

        if state_val in (ServiceState.ZOMBIE.value, ServiceState.DEGRADED.value):
            # If no specific dependency reported false, attribute to service readiness
            return [f"{service}_readiness"]

        return [service]

    def correlate(self, statuses: Mapping[str, ServiceStatus | dict[str, Any]]) -> list[CorrelatedFailure]:
        """Group failing services by root cause and produce correlated failure summaries."""
        # Map: root_cause -> list of (service_name, status_obj_or_dict, evidence_dict)
        cause_to_services: dict[str, list[tuple[str, Any, dict[str, Any]]]] = {}

        for name, status in statuses.items():
            if isinstance(status, ServiceStatus):
                state_val = status.state.value if hasattr(status.state, "value") else str(status.state)
                ev_dict = status.evidence.to_dict() if status.evidence else {}
            else:
                state_val = status.get("state", "HEALTHY")
                ev_dict = status.get("evidence") or {}

            if state_val in (ServiceState.HEALTHY.value, "HEALTHY"):
                continue

            causes = self.identify_service_root_causes(status)
            for cause in causes:
                cause_to_services.setdefault(cause, []).append((name, status, ev_dict))

        correlations: list[CorrelatedFailure] = []

        for cause, entries in sorted(cause_to_services.items(), key=lambda x: x[0]):
            services = sorted([e[0] for e in entries])
            evidence_map = {e[0]: e[2] for e in entries}

            # Determine dominant state across affected services (DOWN > ZOMBIE > DEGRADED)
            states = []
            for _, st, _ in entries:
                if isinstance(st, ServiceStatus):
                    states.append(st.state.value if hasattr(st.state, "value") else str(st.state))
                else:
                    states.append(st.get("state", "UNKNOWN"))

            if ServiceState.DOWN.value in states:
                dominant_state = ServiceState.DOWN.value
            elif ServiceState.ZOMBIE.value in states:
                dominant_state = ServiceState.ZOMBIE.value
            elif ServiceState.DEGRADED.value in states:
                dominant_state = ServiceState.DEGRADED.value
            else:
                dominant_state = states[0] if states else "UNKNOWN"

            # Compute earliest first_failure_time, confirmation_time, max detection_time_seconds
            first_failures: list[str] = []
            confirmations: list[str] = []
            detection_times: list[float] = []

            for _, st, _ in entries:
                if isinstance(st, ServiceStatus):
                    if st.first_failure_observed:
                        first_failures.append(st.first_failure_observed.isoformat())
                    if st.failure_confirmed_at:
                        confirmations.append(st.failure_confirmed_at.isoformat())
                    if st.detection_time_seconds is not None:
                        detection_times.append(st.detection_time_seconds)
                else:
                    if st.get("first_failure_observed"):
                        first_failures.append(st["first_failure_observed"])
                    if st.get("failure_confirmed_at"):
                        confirmations.append(st["failure_confirmed_at"])
                    if st.get("detection_time_seconds") is not None:
                        detection_times.append(float(st["detection_time_seconds"]))

            earliest_failure = min(first_failures) if first_failures else None
            latest_confirmation = max(confirmations) if confirmations else earliest_failure
            max_detection_time = max(detection_times) if detection_times else None

            explanation = self.generate_explanation(cause, services, dominant_state)

            correlations.append(
                CorrelatedFailure(
                    root_cause=cause,
                    state=dominant_state,
                    affected_services=services,
                    explanation=explanation,
                    evidence=evidence_map,
                    first_failure_time=earliest_failure,
                    confirmation_time=latest_confirmation,
                    detection_time_seconds=max_detection_time,
                )
            )

        return correlations

    def generate_explanation(self, root_cause: str, affected_services: list[str], state: str) -> str:
        """Generate a clear, human-readable explanation for the correlated failure."""
        display_cause = "PostgreSQL" if root_cause == "postgresql" else ("Redis" if root_cause == "redis" else root_cause)
        services = sorted(affected_services)

        if len(services) == 1:
            svc = services[0]
            if root_cause in ("postgresql", "redis"):
                return f"{svc} is alive but not ready. It reports {display_cause} connectivity failure."
            if state == ServiceState.DOWN.value:
                return f"{svc} process is down and unreachable on /healthz probe."
            return f"{svc} is {state.lower()} with root cause {display_cause}."

        # Multiple services affected
        if len(services) == 2:
            svc_phrase = f"{services[0]} and {services[1]}"
            both_or_all = "Both"
        else:
            svc_phrase = f"{', '.join(services[:-1])} and {services[-1]}"
            both_or_all = "All"

        if root_cause in ("postgresql", "redis") or self.graph.is_shared(root_cause):
            return f"{svc_phrase} are alive but not ready. {both_or_all} report {display_cause} connectivity failure. {display_cause} is the shared failing critical dependency."

        return f"{svc_phrase} are {state.lower()} due to shared failure in {display_cause}."
