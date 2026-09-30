"""Unit tests for dependency graph, root cause correlation, and incident lifecycle."""

from datetime import datetime, timedelta, timezone
import json

import pytest

from agent.dependency_graph import DependencyGraph, normalize_dependency_name
from agent.incidents import Incident, IncidentManager
from agent.models import ProbeResult, ServiceConfig, ServiceState, ServiceStatus
from agent.root_cause import RootCauseAnalyzer


START = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def make_status(
    service: str,
    state: ServiceState,
    second: int = 0,
    *,
    healthz: int | None = 200,
    readyz: int | None = 200,
    postgres: bool = True,
    redis: bool = True,
    error: str | None = None,
    detection_time_seconds: float | None = 5.0,
) -> ServiceStatus:
    ts = START + timedelta(seconds=second)
    evidence = ProbeResult(
        service=service,
        timestamp=ts,
        healthz_status=healthz,
        readyz_status=readyz,
        latency_ms=10.0,
        dependencies={"postgres": postgres, "redis": redis},
        error_reason=error,
    )
    return ServiceStatus(
        service=service,
        state=state,
        evidence=evidence,
        reason=f"Status reason for {service}",
        first_failure_observed=ts if state != ServiceState.HEALTHY else None,
        failure_confirmed_at=ts if state != ServiceState.HEALTHY else None,
        recovery_first_observed=ts if state == ServiceState.HEALTHY else None,
        recovery_confirmed_at=ts if state == ServiceState.HEALTHY else None,
        detection_time_seconds=detection_time_seconds if state != ServiceState.HEALTHY else None,
        consecutive_failures=3 if state != ServiceState.HEALTHY else 0,
        consecutive_successes=2 if state == ServiceState.HEALTHY else 0,
    )


def test_dependency_graph_mappings_and_shared_checks() -> None:
    graph = DependencyGraph()
    assert graph.dependencies_for("payment-service") == ["postgresql", "redis"]
    assert graph.dependencies_for("order-service") == ["postgresql", "redis"]
    assert graph.dependencies_for("user-service") == []

    assert graph.is_shared("postgresql") is True
    assert graph.is_shared("postgres") is True
    assert graph.is_shared("redis") is True
    assert set(graph.services_depending_on("postgresql")) == {"payment-service", "order-service"}
    assert graph.get_shared_dependencies() == {"postgresql", "redis"}


def test_one_postgresql_failure() -> None:
    manager = IncidentManager()
    payment_status = make_status("payment-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)
    order_status = make_status("order-service", ServiceState.HEALTHY, second=0)

    manager.process_statuses({"payment-service": payment_status, "order-service": order_status})

    active = manager.get_active_incidents()
    assert len(active) == 1
    inc = active[0]
    assert inc.incident_id == "INC-001"
    assert inc.status == "ACTIVE"
    assert inc.state == "ZOMBIE"
    assert inc.root_cause == "postgresql"
    assert inc.affected_services == ["payment-service"]
    assert "payment-service is alive but not ready" in inc.explanation
    assert "PostgreSQL" in inc.explanation
    assert inc.recovery_time is None
    assert "payment-service" in inc.evidence


def test_payment_and_order_shared_postgresql_failure() -> None:
    manager = IncidentManager()
    payment_status = make_status("payment-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)
    order_status = make_status("order-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)

    manager.process_statuses({"payment-service": payment_status, "order-service": order_status})

    active = manager.get_active_incidents()
    assert len(active) == 1
    inc = active[0]
    assert inc.incident_id == "INC-001"
    assert inc.status == "ACTIVE"
    assert inc.state == "ZOMBIE"
    assert inc.root_cause == "postgresql"
    assert sorted(inc.affected_services) == ["order-service", "payment-service"]
    assert "payment-service" in inc.explanation and "order-service" in inc.explanation
    assert "alive but not ready" in inc.explanation
    assert "PostgreSQL is the shared failing critical dependency" in inc.explanation
    assert "payment-service" in inc.evidence
    assert "order-service" in inc.evidence


def test_shared_redis_failure() -> None:
    manager = IncidentManager()
    payment_status = make_status("payment-service", ServiceState.ZOMBIE, second=0, readyz=503, redis=False)
    order_status = make_status("order-service", ServiceState.ZOMBIE, second=0, readyz=503, redis=False)

    manager.process_statuses({"payment-service": payment_status, "order-service": order_status})

    active = manager.get_active_incidents()
    assert len(active) == 1
    inc = active[0]
    assert inc.incident_id == "INC-001"
    assert inc.status == "ACTIVE"
    assert inc.root_cause == "redis"
    assert sorted(inc.affected_services) == ["order-service", "payment-service"]
    assert "Redis is the shared failing critical dependency" in inc.explanation


def test_unrelated_failures_remain_separate() -> None:
    manager = IncidentManager()
    # payment fails due to postgresql, order fails due to redis
    payment_status = make_status("payment-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False, redis=True)
    order_status = make_status("order-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=True, redis=False)

    manager.process_statuses({"payment-service": payment_status, "order-service": order_status})

    active = manager.get_active_incidents()
    assert len(active) == 2
    causes = {inc.root_cause for inc in active}
    assert causes == {"postgresql", "redis"}

    pg_inc = [inc for inc in active if inc.root_cause == "postgresql"][0]
    redis_inc = [inc for inc in active if inc.root_cause == "redis"][0]

    assert pg_inc.affected_services == ["payment-service"]
    assert redis_inc.affected_services == ["order-service"]
    assert pg_inc.incident_id != redis_inc.incident_id


def test_duplicate_events_do_not_duplicate_incidents() -> None:
    manager = IncidentManager()
    payment_status = make_status("payment-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)
    order_status = make_status("order-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)

    # Poll 1
    manager.process_statuses({"payment-service": payment_status, "order-service": order_status})
    # Poll 2 (duplicate failure snapshot)
    payment_status_2 = make_status("payment-service", ServiceState.ZOMBIE, second=10, readyz=503, postgres=False)
    order_status_2 = make_status("order-service", ServiceState.ZOMBIE, second=10, readyz=503, postgres=False)
    manager.process_statuses({"payment-service": payment_status_2, "order-service": order_status_2})
    # Poll 3
    payment_status_3 = make_status("payment-service", ServiceState.ZOMBIE, second=20, readyz=503, postgres=False)
    order_status_3 = make_status("order-service", ServiceState.ZOMBIE, second=20, readyz=503, postgres=False)
    manager.process_statuses({"payment-service": payment_status_3, "order-service": order_status_3})

    all_incidents = manager.get_all_incidents()
    active_incidents = manager.get_active_incidents()

    assert len(all_incidents) == 1
    assert len(active_incidents) == 1
    assert active_incidents[0].incident_id == "INC-001"


def test_newly_affected_service_updates_incident() -> None:
    manager = IncidentManager()

    # Step 1: Only payment-service fails on postgresql
    payment_status_1 = make_status("payment-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)
    order_status_1 = make_status("order-service", ServiceState.HEALTHY, second=0)
    manager.process_statuses({"payment-service": payment_status_1, "order-service": order_status_1})

    active = manager.get_active_incidents()
    assert len(active) == 1
    assert active[0].incident_id == "INC-001"
    assert active[0].affected_services == ["payment-service"]

    # Step 2: Next poll, order-service also fails on postgresql
    payment_status_2 = make_status("payment-service", ServiceState.ZOMBIE, second=10, readyz=503, postgres=False)
    order_status_2 = make_status("order-service", ServiceState.ZOMBIE, second=10, readyz=503, postgres=False)
    manager.process_statuses({"payment-service": payment_status_2, "order-service": order_status_2})

    active = manager.get_active_incidents()
    assert len(active) == 1
    assert active[0].incident_id == "INC-001"
    assert sorted(active[0].affected_services) == ["order-service", "payment-service"]
    assert "payment-service" in active[0].explanation and "order-service" in active[0].explanation
    assert "alive but not ready" in active[0].explanation


def test_recovery_resolves_incident() -> None:
    manager = IncidentManager()

    # Step 1: Failure occurs
    payment_status_1 = make_status("payment-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)
    order_status_1 = make_status("order-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)
    manager.process_statuses({"payment-service": payment_status_1, "order-service": order_status_1})

    assert len(manager.get_active_incidents()) == 1

    # Step 2: Both recover at second 60
    payment_recovered = make_status("payment-service", ServiceState.HEALTHY, second=60)
    order_recovered = make_status("order-service", ServiceState.HEALTHY, second=60)
    manager.process_statuses({"payment-service": payment_recovered, "order-service": order_recovered})

    assert len(manager.get_active_incidents()) == 0
    resolved = manager.get_resolved_incidents()
    assert len(resolved) == 1

    inc = resolved[0]
    assert inc.status == "RESOLVED"
    assert inc.recovery_time is not None
    assert inc.duration_seconds is not None
    assert inc.duration_seconds == 60.0


def test_incident_lifecycle_timestamps_are_ordered_and_duration_is_positive() -> None:
    manager = IncidentManager()
    failing = make_status("payment-service", ServiceState.ZOMBIE, second=2, readyz=503, postgres=False)
    failing.first_failure_observed = START + timedelta(seconds=5)
    failing.failure_confirmed_at = START + timedelta(seconds=3)
    manager.process_statuses({"payment-service": failing})
    incident = manager.get_active_incidents()[0]

    assert datetime.fromisoformat(incident.first_failure_time) <= datetime.fromisoformat(incident.confirmation_time)

    recovered = make_status("payment-service", ServiceState.HEALTHY, second=12)
    manager.process_statuses({"payment-service": recovered})
    resolved = manager.get_resolved_incidents()[0]
    assert datetime.fromisoformat(resolved.confirmation_time) <= datetime.fromisoformat(resolved.recovery_time)
    assert resolved.duration_seconds is not None and resolved.duration_seconds > 0


def test_partial_recovery_keeps_incident_active() -> None:
    manager = IncidentManager()

    # Failure on both
    payment_status = make_status("payment-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)
    order_status = make_status("order-service", ServiceState.ZOMBIE, second=0, readyz=503, postgres=False)
    manager.process_statuses({"payment-service": payment_status, "order-service": order_status})

    # Only payment recovers; order is still ZOMBIE
    payment_recovered = make_status("payment-service", ServiceState.HEALTHY, second=30)
    order_still_failing = make_status("order-service", ServiceState.ZOMBIE, second=30, readyz=503, postgres=False)
    manager.process_statuses({"payment-service": payment_recovered, "order-service": order_still_failing})

    # Incident should remain ACTIVE
    active = manager.get_active_incidents()
    assert len(active) == 1
    assert active[0].status == "ACTIVE"


def test_incident_json_matches_shared_contract() -> None:
    manager = IncidentManager()
    payment_status = make_status(
        "payment-service",
        ServiceState.ZOMBIE,
        second=0,
        readyz=503,
        postgres=False,
        detection_time_seconds=5.8,
    )
    order_status = make_status(
        "order-service",
        ServiceState.ZOMBIE,
        second=0,
        readyz=503,
        postgres=False,
        detection_time_seconds=5.8,
    )

    manager.process_statuses({"payment-service": payment_status, "order-service": order_status})
    incident = manager.get_active_incidents()[0]

    as_dict = incident.to_dict()
    required_keys = {
        "incident_id",
        "status",
        "state",
        "root_cause",
        "affected_services",
        "first_failure_time",
        "confirmation_time",
        "recovery_time",
        "detection_time_seconds",
        "explanation",
        "evidence",
    }
    assert set(as_dict.keys()) == required_keys

    assert as_dict["incident_id"] == "INC-001"
    assert as_dict["status"] == "ACTIVE"
    assert as_dict["state"] == "ZOMBIE"
    assert as_dict["root_cause"] == "postgresql"
    assert sorted(as_dict["affected_services"]) == ["order-service", "payment-service"]
    assert as_dict["recovery_time"] is None
    assert as_dict["detection_time_seconds"] == 5.8
    assert isinstance(as_dict["evidence"], dict)
    assert isinstance(as_dict["explanation"], str)

    # Valid JSON string
    json_str = incident.to_json()
    parsed = json.loads(json_str)
    assert parsed == as_dict
