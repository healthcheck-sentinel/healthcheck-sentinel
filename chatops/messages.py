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
        if isinstance(evidence, dict):
            # Deliberately exclude raw URLs, exception strings and arbitrary values.
            checks = evidence.get("dependencies", {})
            failed = [str(name) for name, ok in checks.items() if ok is False] if isinstance(checks, dict) else []
            lines.append(f"{service}: healthz={evidence.get('healthz_status')}, readyz={evidence.get('readyz_status')}, failed dependencies={', '.join(failed) or 'none reported'}")
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

    return {
        "text": f"{incident.incident_id}: {incident.state} incident detected",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{incident.incident_id}: {incident.state}"},
            },
            {"type": "section", "text": {"type": "mrkdwn", "text": summary}},

        ],
    }


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
