from __future__ import annotations

from typing import Any

from chatops.actions import build_restart_action, build_view_logs_action
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
    for key, value in incident.evidence.items():
        lines.append(f"*{key}*: {value}")
    return "\n".join(lines)


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

    return {
        "text": f"{incident.incident_id}: {incident.state} incident detected",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{incident.incident_id}: {incident.state}"},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
            {
                "type": "actions",
                "elements": [build_view_logs_action(), build_restart_action()],
            },
        ],
    }


def build_recovery_notification(incident: Incident) -> dict[str, Any]:
    message = (
        f"*Incident ID*: {incident.incident_id}\n"
        f"*Status*: RESOLVED\n"
        f"*Service state*: {incident.state}\n"
        f"*Recovery time*: {incident.recovery_time or 'n/a'}\n"
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
