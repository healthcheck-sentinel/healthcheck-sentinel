from __future__ import annotations

from typing import Any


def build_view_logs_action() -> dict[str, Any]:
    return {
        "type": "button",
        "text": {"type": "plain_text", "text": "View Logs", "emoji": True},
        "action_id": "view_logs",
        "value": "recent_logs",
    }


def build_restart_action() -> dict[str, Any]:
    return {
        "type": "button",
        "text": {"type": "plain_text", "text": "Restart", "emoji": True},
        "action_id": "restart_incident",
        "value": "placeholder_restart",
    }


def handle_view_logs_action() -> dict[str, Any]:
    return {"status": "disabled", "action": "view_logs", "message": "Use authenticated operator logs; no log backend is configured."}


def handle_restart_action() -> dict[str, Any]:
    return {"status": "disabled", "action": "restart_incident", "message": "Use authenticated Docker or Kubernetes operator access; remote restart is disabled."}
