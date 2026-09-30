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
    return {
        "status": "ok",
        "action": "view_logs",
        "logs": [
            "2026-09-30T12:00:00Z INFO payment-service healthy",
            "2026-09-30T12:00:05Z ERROR payment-service postgres connection timeout",
            "2026-09-30T12:00:08Z ERROR order-service dependency failure detected",
        ],
    }


def handle_restart_action() -> dict[str, Any]:
    return {
        "status": "accepted",
        "action": "restart_incident",
        "backend": "placeholder",
        "message": "restart request queued for orchestration integration",
    }
