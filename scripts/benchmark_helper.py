"""Benchmark helper: measures real detection time, recovery time, CPU overhead, and deduplication efficiency."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import time
import os
import sys

# Ensure workspace root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.dependency_graph import DependencyGraph
from agent.incidents import IncidentManager
from agent.models import ProbeResult, ServiceConfig, ServiceState
from agent.root_cause import RootCauseAnalyzer
from agent.state_manager import StateManager


PAYMENT_CONFIG = ServiceConfig(
    name="payment-service",
    base_url="http://localhost:8001",
    critical_dependencies=("postgres", "redis"),
)


def make_probe(
    service: str = "payment-service",
    *,
    healthz: int = 200,
    readyz: int = 200,
    postgres: bool = True,
    redis: bool = True,
    latency_ms: float = 8.5,
) -> ProbeResult:
    return ProbeResult(
        service=service,
        timestamp=datetime.now(timezone.utc),
        healthz_status=healthz,
        readyz_status=readyz,
        latency_ms=latency_ms,
        dependencies={"postgres": postgres, "redis": redis},
        error_reason=None if readyz == 200 else "Dependency unavailable",
    )


def benchmark_detection_time(failure_threshold: int = 3) -> dict:
    """Measure real wall-clock time required for state manager to confirm failure."""
    sm = StateManager(failure_threshold=failure_threshold, recovery_threshold=2)
    # Start healthy
    sm.observe(PAYMENT_CONFIG, make_probe())

    t0 = time.perf_counter()
    status = None
    for i in range(failure_threshold):
        status = sm.observe(PAYMENT_CONFIG, make_probe(readyz=503, postgres=False))

    elapsed_s = time.perf_counter() - t0
    return {
        "failure_threshold": failure_threshold,
        "confirmed_state": status.state.value,
        "wall_clock_seconds": round(elapsed_s, 6),
        "wall_clock_ms": round(elapsed_s * 1000, 3),
        "detection_time_seconds": status.detection_time_seconds,
    }


def benchmark_recovery_time(recovery_threshold: int = 2) -> dict:
    """Measure real wall-clock time required for state manager to confirm recovery."""
    sm = StateManager(failure_threshold=3, recovery_threshold=recovery_threshold)
    # Force failure
    for _ in range(3):
        sm.observe(PAYMENT_CONFIG, make_probe(readyz=503, postgres=False))

    t0 = time.perf_counter()
    status = None
    for _ in range(recovery_threshold):
        status = sm.observe(PAYMENT_CONFIG, make_probe(readyz=200, postgres=True))

    elapsed_s = time.perf_counter() - t0
    return {
        "recovery_threshold": recovery_threshold,
        "confirmed_state": status.state.value,
        "wall_clock_seconds": round(elapsed_s, 6),
        "wall_clock_ms": round(elapsed_s * 1000, 3),
    }


def benchmark_cpu_and_throughput(iterations: int = 1000) -> dict:
    """Measure CPU overhead and throughput across iterations of state evaluation."""
    sm = StateManager(failure_threshold=3, recovery_threshold=2)
    manager = IncidentManager()

    t0 = time.perf_counter()
    cpu_t0 = time.process_time()

    for i in range(iterations):
        pg_ok = (i % 10) != 0
        status = sm.observe(PAYMENT_CONFIG, make_probe(readyz=200 if pg_ok else 503, postgres=pg_ok))
        manager.process_statuses({"payment-service": status})

    elapsed_wall = time.perf_counter() - t0
    elapsed_cpu = time.process_time() - cpu_t0

    ops_per_sec = iterations / elapsed_wall if elapsed_wall > 0 else 0.0
    cpu_percent = (elapsed_cpu / elapsed_wall * 100.0) if elapsed_wall > 0 else 0.0

    return {
        "iterations": iterations,
        "wall_clock_seconds": round(elapsed_wall, 4),
        "cpu_time_seconds": round(elapsed_cpu, 4),
        "cpu_utilization_pct": round(cpu_percent, 2),
        "evaluations_per_second": round(ops_per_sec, 2),
    }


def benchmark_deduplication(iterations: int = 50) -> dict:
    """Measure duplicate alert count over repeated identical failures."""
    manager = IncidentManager()
    sm = StateManager(failure_threshold=1, recovery_threshold=1)

    # Initial failure
    status = sm.observe(PAYMENT_CONFIG, make_probe(readyz=503, postgres=False))

    for _ in range(iterations):
        manager.process_statuses({"payment-service": status})

    total_created = len(manager.get_all_incidents())
    active_count = len(manager.get_active_incidents())
    duplicate_incidents = total_created - 1

    return {
        "evaluations": iterations,
        "total_incidents_created": total_created,
        "active_incidents": active_count,
        "duplicate_incidents": duplicate_incidents,
        "deduplication_efficiency_pct": round((1.0 - (duplicate_incidents / iterations)) * 100.0, 2),
    }


def run_all_benchmarks() -> None:
    print("=" * 60)
    print(" [*] HealthCheck Sentinel - Synthetic state-machine microbenchmarks (NOT end-to-end targets)")
    print("=" * 60)

    print("\n1. Failure Detection Latency:")
    det = benchmark_detection_time()
    print(f"   - Failure Threshold : {det['failure_threshold']} consecutive probes")
    print(f"   - Confirmed State   : {det['confirmed_state']}")
    print(f"   - Execution Time    : {det['wall_clock_ms']} ms ({det['wall_clock_seconds']} s)")

    print("\n2. Recovery Latency:")
    rec = benchmark_recovery_time()
    print(f"   - Recovery Threshold: {rec['recovery_threshold']} consecutive probes")
    print(f"   - Confirmed State   : {rec['confirmed_state']}")
    print(f"   - Execution Time    : {rec['wall_clock_ms']} ms ({rec['wall_clock_seconds']} s)")

    print("\n3. CPU Overhead & Throughput:")
    cpu = benchmark_cpu_and_throughput(1000)
    print(f"   - Iterations        : {cpu['iterations']}")
    print(f"   - Total Wall Time   : {cpu['wall_clock_seconds']} s")
    print(f"   - Total CPU Time    : {cpu['cpu_time_seconds']} s")
    print(f"   - CPU Utilization   : {cpu['cpu_utilization_pct']}%")
    print(f"   - Throughput        : {cpu['evaluations_per_second']} ops/sec")

    print("\n4. Alert Deduplication:")
    dedup = benchmark_deduplication(50)
    print(f"   - Repeated Events   : {dedup['evaluations']}")
    print(f"   - Total Incidents   : {dedup['total_incidents_created']}")
    print(f"   - Duplicate Alerts  : {dedup['duplicate_incidents']}")
    print(f"   - Deduplication Eff : {dedup['deduplication_efficiency_pct']}%")
    print("=" * 60)


if __name__ == "__main__":
    run_all_benchmarks()
