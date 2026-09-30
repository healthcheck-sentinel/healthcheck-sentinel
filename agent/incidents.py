"""Incident management and lifecycle engine following the shared incident contract."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, Mapping

from agent.dependency_graph import DependencyGraph
from agent.models import ServiceState, ServiceStatus
from agent.root_cause import CorrelatedFailure, RootCauseAnalyzer


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Incident:
    """Shared Incident Contract model consumed across healthcheck-sentinel."""

    incident_id: str
    status: str
    state: str
    root_cause: str
    affected_services: list[str]
    first_failure_time: str
    confirmation_time: str
    recovery_time: str | None = None
    detection_time_seconds: float | None = None
    explanation: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize incident to the exact shared JSON-compatible dictionary."""
        return {
            "incident_id": self.incident_id,
            "status": self.status,
            "state": self.state,
            "root_cause": self.root_cause,
            "affected_services": list(self.affected_services),
            "first_failure_time": self.first_failure_time,
            "confirmation_time": self.confirmation_time,
            "recovery_time": self.recovery_time,
            "detection_time_seconds": self.detection_time_seconds,
            "explanation": self.explanation,
            "evidence": copy.deepcopy(self.evidence),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize incident to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @property
    def duration_seconds(self) -> float | None:
        """Calculate total incident duration in seconds once resolved."""
        if not self.recovery_time or not self.first_failure_time:
            return None
        try:
            start = datetime.fromisoformat(self.first_failure_time)
            end = datetime.fromisoformat(self.recovery_time)
            return round((end - start).total_seconds(), 2)
        except Exception:
            return None


class IncidentManager:
    """Manages creation, deduplication, correlation, and resolution of incidents."""

    def __init__(
        self,
        dependency_graph: DependencyGraph | None = None,
        analyzer: RootCauseAnalyzer | None = None,
    ) -> None:
        self.graph = dependency_graph or DependencyGraph()
        self.analyzer = analyzer or RootCauseAnalyzer(dependency_graph=self.graph)
        self.incidents: dict[str, Incident] = {}
        self.active_incidents_by_cause: dict[str, str] = {}  # root_cause -> incident_id
        self._counter: int = 1

    def _next_incident_id(self) -> str:
        incident_id = f"INC-{self._counter:03d}"
        self._counter += 1
        return incident_id

    def process_statuses(
        self,
        statuses: Mapping[str, ServiceStatus | dict[str, Any]],
    ) -> list[Incident]:
        """
        Process the latest snapshot of service statuses.
        - Correlates failing services by root cause
        - Creates or updates active incidents (deduplication)
        - Resolves incidents when all affected services recover
        """
        # 1. Correlate current failures
        correlations: list[CorrelatedFailure] = self.analyzer.correlate(statuses)
        current_failing_causes = {c.root_cause for c in correlations}

        # 2. Update or create incidents for active failures
        for corr in correlations:
            cause = corr.root_cause
            if cause in self.active_incidents_by_cause:
                # Deduplication / Update active incident
                incident_id = self.active_incidents_by_cause[cause]
                incident = self.incidents[incident_id]

                # Merge affected services and evidence
                merged_services = sorted(set(incident.affected_services).union(corr.affected_services))
                incident.affected_services = merged_services
                incident.evidence.update(corr.evidence)
                incident.state = corr.state

                # Update explanation with the full set of affected services
                incident.explanation = self.analyzer.generate_explanation(
                    cause,
                    incident.affected_services,
                    incident.state,
                )

                if corr.confirmation_time and corr.confirmation_time > incident.confirmation_time:
                    incident.confirmation_time = corr.confirmation_time

                if corr.detection_time_seconds is not None:
                    incident.detection_time_seconds = corr.detection_time_seconds
            else:
                # Create new incident
                incident_id = self._next_incident_id()
                first_failure = corr.first_failure_time or _utc_iso_now()
                confirmation = corr.confirmation_time or first_failure

                incident = Incident(
                    incident_id=incident_id,
                    status="ACTIVE",
                    state=corr.state,
                    root_cause=cause,
                    affected_services=corr.affected_services,
                    first_failure_time=first_failure,
                    confirmation_time=confirmation,
                    recovery_time=None,
                    detection_time_seconds=corr.detection_time_seconds,
                    explanation=corr.explanation,
                    evidence=corr.evidence,
                )
                self.incidents[incident_id] = incident
                self.active_incidents_by_cause[cause] = incident_id

        # 3. Check for recovery on existing active incidents
        resolved_causes: list[str] = []
        for cause, incident_id in list(self.active_incidents_by_cause.items()):
            if cause not in current_failing_causes:
                incident = self.incidents[incident_id]

                # Check if all affected services are healthy or no longer reporting this failure
                all_recovered = True
                recovery_timestamps: list[str] = []

                for svc_name in incident.affected_services:
                    svc_status = statuses.get(svc_name)
                    if svc_status is None:
                        all_recovered = False
                        break
                    if svc_status is not None:
                        if isinstance(svc_status, ServiceStatus):
                            is_healthy = svc_status.state == ServiceState.HEALTHY
                            rec_time = svc_status.recovery_confirmed_at or svc_status.recovery_first_observed
                            if rec_time:
                                recovery_timestamps.append(rec_time.isoformat())
                        else:
                            is_healthy = svc_status.get("state") in (ServiceState.HEALTHY.value, "HEALTHY")
                            rec_time_str = svc_status.get("recovery_confirmed_at") or svc_status.get("recovery_first_observed")
                            if rec_time_str:
                                recovery_timestamps.append(rec_time_str)

                        if not is_healthy:
                            # Service is still failing (possibly on this or another cause)
                            all_recovered = False
                            break

                if all_recovered:
                    # Resolve incident
                    incident.status = "RESOLVED"
                    incident.recovery_time = max(recovery_timestamps) if recovery_timestamps else _utc_iso_now()
                    resolved_causes.append(cause)

        for cause in resolved_causes:
            del self.active_incidents_by_cause[cause]

        return list(self.incidents.values())

    def get_active_incidents(self) -> list[Incident]:
        """Return all currently active incidents."""
        return [self.incidents[inc_id] for inc_id in self.active_incidents_by_cause.values()]

    def get_resolved_incidents(self) -> list[Incident]:
        """Return all resolved incidents."""
        return [inc for inc in self.incidents.values() if inc.status == "RESOLVED"]

    def get_all_incidents(self) -> list[Incident]:
        """Return all tracked incidents."""
        return list(self.incidents.values())

    def get_incident(self, incident_id: str) -> Incident | None:
        """Lookup an incident by its ID."""
        return self.incidents.get(incident_id)
