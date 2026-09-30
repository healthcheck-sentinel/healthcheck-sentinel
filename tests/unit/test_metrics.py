"""Unit tests for Prometheus metrics collection and formatting."""

from datetime import datetime, timezone
import pytest
from prometheus_client import CollectorRegistry

from agent.incidents import Incident
from agent.metrics import MetricsCollector
from agent.models import ProbeResult, ServiceState, ServiceStatus


def test_prometheus_metrics_registration_and_recording() -> None:
    custom_registry = CollectorRegistry()
    collector = MetricsCollector(registry=custom_registry)

    # 1. Record probe
    probe = ProbeResult(
        service="payment-service",
        timestamp=datetime.now(timezone.utc),
        healthz_status=200,
        readyz_status=503,
        latency_ms=15.0,
        dependencies={"postgres": False, "redis": True},
        error_reason="DB down",
    )
    collector.record_probe("payment-service", probe)

    # 2. Record service status
    status = ServiceStatus(
        service="payment-service",
        state=ServiceState.ZOMBIE,
        detection_time_seconds=3.5,
    )
    collector.record_status(status)

    # 3. Record incident
    incident = Incident(
        incident_id="INC-001",
        status="ACTIVE",
        state="ZOMBIE",
        root_cause="postgresql",
        affected_services=["payment-service"],
        first_failure_time="2026-09-30T12:00:00+00:00",
        confirmation_time="2026-09-30T12:00:03+00:00",
        detection_time_seconds=3.5,
        explanation="PostgreSQL is down.",
    )
    collector.record_incidents([incident])

    # 4. Generate Prometheus text
    output = collector.generate_metrics_text().decode("utf-8")

    assert "healthcheck_service_status" in output
    assert 'healthcheck_service_status{service="payment-service",state="ZOMBIE"} 1.0' in output
    assert 'healthcheck_service_status{service="payment-service",state="HEALTHY"} 0.0' in output
    assert "healthcheck_probe_duration_seconds" in output
    assert "healthcheck_probe_failures_total" in output
    assert 'healthcheck_detection_seconds{service="payment-service",state="ZOMBIE"} 3.5' in output
    assert 'healthcheck_incidents_total{root_cause="postgresql",status="ACTIVE"} 1.0' in output
    assert 'healthcheck_active_incidents{root_cause="postgresql"} 1.0' in output
    assert "healthcheck_process_cpu_percent" in output
    assert "healthcheck_process_memory_bytes" in output
