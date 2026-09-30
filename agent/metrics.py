"""Prometheus metrics exporter for the HealthCheck Sentinel agent."""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Mapping

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    REGISTRY,
    generate_latest,
    start_http_server,
)

from agent.incidents import Incident
from agent.models import ProbeResult, ServiceState, ServiceStatus


STATE_NUMERIC_MAP = {
    ServiceState.HEALTHY.value: 1,
    ServiceState.DEGRADED.value: 2,
    ServiceState.ZOMBIE.value: 3,
    ServiceState.DOWN.value: 4,
}


class MetricsCollector:
    """Manages Prometheus metrics registration and updates for healthcheck-sentinel."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or REGISTRY

        # Service state & status
        self.service_status = Gauge(
            "healthcheck_service_status",
            "One-hot confirmed service state (1=current, 0=inactive)",
            ["service", "state"],
            registry=self.registry,
        )

        # Probe durations and failures
        self.probe_duration = Histogram(
            "healthcheck_probe_duration_seconds",
            "Duration of health and readiness probes in seconds",
            ["service", "probe_type"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
            registry=self.registry,
        )
        self.probe_failures = Counter(
            "healthcheck_probe_failures_total",
            "Total count of failed health and readiness probes",
            ["service", "probe_type", "reason"],
            registry=self.registry,
        )

        # Detection and incident tracking
        self.detection_seconds = Gauge(
            "healthcheck_detection_seconds",
            "Detection time latency in seconds for confirmed state transitions",
            ["service", "state"],
            registry=self.registry,
        )
        self.incidents_total = Counter(
            "healthcheck_incidents_total",
            "Total count of generated incidents",
            ["root_cause", "status"],
            registry=self.registry,
        )
        self.active_incidents = Gauge(
            "healthcheck_active_incidents",
            "Number of currently active incidents by root cause",
            ["root_cause"],
            registry=self.registry,
        )

        # Process CPU and memory overhead
        self.cpu_percent = Gauge(
            "healthcheck_process_cpu_percent",
            "Current CPU utilization percent of the monitoring agent",
            registry=self.registry,
        )
        self.memory_bytes = Gauge(
            "healthcheck_process_memory_bytes",
            "Current memory consumption in bytes of the monitoring agent",
            registry=self.registry,
        )

        self.target_resource_available = Gauge('healthcheck_target_resource_available',
            'One when the latest probe includes target resource evidence', ['service'], registry=self.registry)
        self.target_resources = Gauge('healthcheck_target_resource',
            'Target container/process resource evidence; resource label specifies unit',
            ['service','resource'], registry=self.registry)
        self.pool_connections = Gauge('healthcheck_dependency_pool_connections',
            'Bounded health-probe connection pool and backend capacity',
            ['service','dependency','kind'], registry=self.registry)

        self._seen_incidents: set[str] = set()
        self._known_causes: set[str] = set()
        self._process = psutil.Process() if _HAS_PSUTIL else None
        if self._process:
            self._process.cpu_percent(interval=None)
        self._start_time = time.time()

    def record_target_resources(self, service, result):
        import math
        self.target_resource_available.labels(service=service).set(bool(result.resources))
        for key,value in result.resources.items():
            if key in ('cpu_percent','memory_used_bytes','memory_limit_bytes','memory_available_bytes','process_cpu_seconds','probe_cpu_seconds','probe_requests') and isinstance(value,(int,float)) and math.isfinite(value):
                self.target_resources.labels(service=service,resource=key).set(value)
        for dependency,evidence in result.pools.items():
            if dependency not in ('postgres','redis'):
                continue
            for group,values in evidence.items():
                for kind,value in values.items():
                    self.pool_connections.labels(service=service,dependency=dependency,kind=group+'_'+kind).set(value)

    def record_probe(self, service: str, result: ProbeResult) -> None:
        """Record probe duration and failure metrics."""
        self.record_target_resources(service, result)
        duration_s = result.latency_ms / 1000.0
        self.probe_duration.labels(service=service, probe_type="combined").observe(duration_s)

        # Check healthz status
        if result.healthz_status is None or not (200 <= result.healthz_status < 300):
            reason = "unreachable" if result.healthz_status is None else f"http_{result.healthz_status}"
            self.probe_failures.labels(service=service, probe_type="healthz", reason=reason).inc()

        # Check readyz status
        if result.readyz_status is None or not (200 <= result.readyz_status < 300):
            reason = "unreachable" if result.readyz_status is None else f"http_{result.readyz_status}"
            self.probe_failures.labels(service=service, probe_type="readyz", reason=reason).inc()

    def record_status(self, status: ServiceStatus) -> None:
        """Update service state gauge and detection latency."""
        state_str = status.state.value if hasattr(status.state, "value") else str(status.state)

        # Clear other states for this service to avoid duplicate 1s
        for s in ServiceState:
            val = 1 if s.value == state_str else 0
            self.service_status.labels(service=status.service, state=s.value).set(val)

        if status.detection_time_seconds is not None:
            self.detection_seconds.labels(service=status.service, state=state_str).set(
                status.detection_time_seconds
            )

    def record_incidents(self, incidents: list[Incident]) -> None:
        """Update incident metrics and active incident counts."""
        active_counts: dict[str, int] = {}

        for inc in incidents:
            if inc.incident_id not in self._seen_incidents and inc.status == "ACTIVE":
                self.incidents_total.labels(root_cause=inc.root_cause, status="ACTIVE").inc()
                self._seen_incidents.add(inc.incident_id)

            if inc.status == "ACTIVE":
                active_counts[inc.root_cause] = active_counts.get(inc.root_cause, 0) + 1

        self._known_causes.update(active_counts)
        for cause in self._known_causes:
            self.active_incidents.labels(root_cause=cause).set(active_counts.get(cause, 0))

    def update_resource_usage(self) -> tuple[float, int]:
        """Sample and update CPU percent and memory usage."""
        cpu = 0.0
        mem = 0
        if self._process is not None:
            try:
                proc = self._process
                cpu = proc.cpu_percent(interval=None)
                mem = proc.memory_info().rss
            except Exception:
                pass
        self.cpu_percent.set(cpu)
        self.memory_bytes.set(mem)
        return cpu, mem

    def generate_metrics_text(self) -> bytes:
        """Return Prometheus metrics formatted payload."""
        self.update_resource_usage()
        return generate_latest(self.registry)

    def start_server(self, port: int = 9100) -> None:
        """Start the Prometheus HTTP metrics server on specified port."""
        start_http_server(port, registry=self.registry)


# Module-level default collector
collector = MetricsCollector()
