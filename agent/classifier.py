"""Pure rule-based mapping from probe evidence to service state."""

from agent.models import ProbeResult, ServiceConfig, ServiceState


def classify(config: ServiceConfig, result: ProbeResult) -> tuple[ServiceState, str]:
    if result.healthz_status is None:
        return ServiceState.DOWN, result.error_reason or "The service process did not respond to /healthz."

    failed_critical = [
        name for name in config.critical_dependencies
        if result.dependencies.get(name) is False
    ]
    if result.readyz_status is None or not 200 <= result.readyz_status < 300:
        if failed_critical:
            names = ", ".join(name.upper() for name in failed_critical)
            return ServiceState.ZOMBIE, f"Process is alive but {names} critical dependency is unavailable."
        return ServiceState.DEGRADED, result.error_reason or "The process is alive but readiness failed without critical dependency evidence."

    if failed_critical:
        names = ", ".join(name.upper() for name in failed_critical)
        return ServiceState.DEGRADED, f"Service is ready, but {names} reports unhealthy."

    failed_optional = [
        name for name, healthy in result.dependencies.items()
        if healthy is False and name not in config.critical_dependencies
    ]
    if failed_optional:
        return ServiceState.DEGRADED, f"Service is ready with warning: {', '.join(failed_optional)} is unhealthy."
    if result.healthz_status is not None and not 200 <= result.healthz_status < 300:
        return ServiceState.DEGRADED, "Process responded but its liveness check failed."
    if any(name not in result.dependencies for name in config.critical_dependencies):
        return ServiceState.DEGRADED, "Readiness response is missing required dependency evidence."
    if result.error_reason:
        return ServiceState.DEGRADED, result.error_reason
    return ServiceState.HEALTHY, "Liveness, readiness, and all critical dependencies are healthy."