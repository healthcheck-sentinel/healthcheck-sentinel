from __future__ import annotations

from datetime import datetime
from typing import Any

from chatops.models import Incident


def _format_services(incident: Incident) -> str:
    services = incident.affected_services or ["unknown-service"]
    return ", ".join(services)


def _format_detection_time(incident: Incident) -> str:
    if incident.detection_time_seconds is None:
        return "n/a"
    return f"{incident.detection_time_seconds}s"


def _format_evidence(incident: Incident) -> str:
    if not incident.evidence:
        return "No additional evidence attached."

    lines = []
    for service, evidence in incident.evidence.items():
        if isinstance(evidence, dict) and not service.startswith("_"):
            # Deliberately exclude raw URLs, exception strings and arbitrary values.
            checks = evidence.get("dependencies", {})
            failed = [str(name) for name, ok in checks.items() if ok is False] if isinstance(checks, dict) else []
            lines.append(f"{service}: healthz={evidence.get('healthz_status')}, readyz={evidence.get('readyz_status')}, failed dependencies={', '.join(failed) or 'none reported'}")
    adjacent = incident.evidence.get('_adjacent_resources', {})
    if isinstance(adjacent,dict):
        for name,resources in adjacent.items():
            if isinstance(resources,dict):
                cpu = resources.get('cpu_percent')
                available = resources.get('memory_available_bytes')
                if isinstance(cpu,(int,float)) and isinstance(available,(int,float)):
                    lines.append(f"{name}: CPU={cpu:.2f}% of one core, memory headroom={available/1048576:.1f} MiB")
    return "\n".join(lines)[:1500] or "Additional evidence retained in the private incident record."



def _format_duration(incident: Incident) -> str:
    if not incident.first_failure_time or not incident.recovery_time:
        return "n/a"
    try:
        start = datetime.fromisoformat(incident.first_failure_time)
        end = datetime.fromisoformat(incident.recovery_time)
        return f"{max(0.0, (end - start).total_seconds()):.1f}s"
    except ValueError:
        return "n/a"


def build_incident_alert(incident: Incident) -> dict[str, Any]:
    summary = (
        f"*Incident ID*: {incident.incident_id}\n"
        f"*State*: {incident.state}\n"
        f"*Root cause*: {incident.root_cause}\n"
        f"*Affected services*: {_format_services(incident)}\n"
        f"*Detection time*: {_format_detection_time(incident)}\n"
        f"*Explanation*: {incident.explanation or 'No explanation provided.'}\n"
        f"*Evidence*: {_format_evidence(incident)}"
    )

    payload = {
        "text": f"{incident.incident_id}: {incident.state} incident detected",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{incident.incident_id}: {incident.state}"},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": summary}},

        ],
    }

    import os
    if os.getenv('SLACK_ACTIONS_ENABLED','false').lower() == 'true':
        from chatops.interactive import action_blocks
        payload['blocks'].extend(action_blocks(incident.affected_services))
    return payload


def build_recovery_notification(incident: Incident) -> dict[str, Any]:
    message = (
        f"*Incident ID*: {incident.incident_id}\n"
        f"*Status*: RESOLVED\n"
        f"*Original incident state*: {incident.state}\n"
        f"*Root cause*: {incident.root_cause}\n"
        f"*Affected services*: {_format_services(incident)}\n"
        f"*Detection time*: {_format_detection_time(incident)}\n"
        f"*Recovery time*: {incident.recovery_time or 'n/a'}\n"
        f"*Incident duration*: {_format_duration(incident)}\n"
        f"*Explanation*: {incident.explanation or 'Recovery confirmed.'}"
    )

    return {
        "text": f"{incident.incident_id}: resolved",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{incident.incident_id}: RESOLVED ({incident.state})"},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": message}},
        ],
    }
