import hashlib
import hmac

from chatops.actions import build_restart_action, build_view_logs_action
from chatops.messages import build_incident_alert, build_recovery_notification
from chatops.models import Incident
from chatops.slack_client import verify_slack_signature


INCIDENT_PAYLOAD = {
    "incident_id": "INC-001",
    "status": "ACTIVE",
    "state": "ZOMBIE",
    "root_cause": "postgresql",
    "affected_services": ["payment-service", "order-service"],
    "first_failure_time": "timestamp",
    "confirmation_time": "timestamp",
    "recovery_time": None,
    "detection_time_seconds": 5.8,
    "explanation": "PostgreSQL is the shared failing dependency.",
    "evidence": {"db_errors": "connection timeout", "latency_ms": 4000},
}


def test_active_incident_message_formatting() -> None:
    incident = Incident.from_dict(INCIDENT_PAYLOAD)

    payload = build_incident_alert(incident)

    assert payload["text"] == "INC-001: ZOMBIE incident detected"
    assert "INC-001" in payload["blocks"][0]["text"]["text"]
    assert "ZOMBIE" in payload["blocks"][0]["text"]["text"]
    assert "postgresql" in payload["blocks"][1]["text"]["text"]
    assert "payment-service" in payload["blocks"][1]["text"]["text"]
    assert "5.8s" in payload["blocks"][1]["text"]["text"]
    assert payload["blocks"][2]["elements"][0]["action_id"] == "view_logs"
    assert payload["blocks"][2]["elements"][1]["action_id"] == "restart_incident"


def test_resolved_incident_message_formatting() -> None:
    resolved = {
        **INCIDENT_PAYLOAD,
        "status": "RESOLVED",
        "recovery_time": "timestamp",
        "state": "RECOVERED",
        "explanation": "Database recovered and traffic restored.",
        "evidence": {"db_errors": "none"},
    }

    payload = build_recovery_notification(Incident.from_dict(resolved))

    assert payload["text"] == "INC-001: resolved"
    assert "resolved" in payload["blocks"][0]["text"]["text"].lower()
    assert "RECOVERED" in payload["blocks"][0]["text"]["text"]
    assert "Database recovered" in payload["blocks"][1]["text"]["text"]


def test_missing_optional_evidence() -> None:
    incident = Incident.from_dict({**INCIDENT_PAYLOAD, "evidence": {}})

    payload = build_incident_alert(incident)

    assert "No additional evidence attached." in payload["blocks"][1]["text"]["text"]


def test_view_logs_action() -> None:
    action = build_view_logs_action()

    assert action["action_id"] == "view_logs"
    assert action["text"]["text"] == "View Logs"
    assert action["value"] == "recent_logs"


def test_restart_action_placeholder() -> None:
    action = build_restart_action()

    assert action["action_id"] == "restart_incident"
    assert action["text"]["text"] == "Restart"
    assert action["value"] == "placeholder_restart"


def test_invalid_slack_signature_handling() -> None:
    body = b'{"incident_id":"INC-001"}'
    timestamp = "1700000000"
    secret = "super-secret"
    invalid = "v0=badsignature"

    assert verify_slack_signature(body, timestamp, invalid, secret) is False

    computed = hmac.new(secret.encode(), f"v0:{timestamp}:".encode() + body, hashlib.sha256).hexdigest()
    assert verify_slack_signature(body, timestamp, f"v0={computed}", secret) is True
