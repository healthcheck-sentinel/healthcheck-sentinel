"""Deliver incident lifecycle notifications to ChatOps independently of creation."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from collections.abc import Sequence

from agent.incidents import Incident
from chatops.messages import build_incident_alert, build_recovery_notification
from chatops.models import Incident as ChatOpsIncident
from chatops.slack_client import SlackClient

log = logging.getLogger(__name__)


class ChatOpsEventDispatcher:
    """Send at most one Slack delivery attempt per incident lifecycle transition."""

    def __init__(self, slack_client: SlackClient | None = None, channel: str | None = None) -> None:
        self.slack_client = slack_client or SlackClient()
        self.channel = channel or os.getenv("SLACK_ALERT_CHANNEL")
        self._dispatched: set[tuple[str, str]] = set()
        self.deliveries: list[dict] = []

    async def dispatch(self, incidents: Sequence[Incident]) -> None:
        for incident in incidents:
            status = incident.status.upper()
            if status == "ACTIVE":
                event = "ACTIVE"
                payload = build_incident_alert(ChatOpsIncident.from_dict(incident.to_dict()))
            elif status == "RESOLVED":
                event = "RESOLVED"
                payload = build_recovery_notification(ChatOpsIncident.from_dict(incident.to_dict()))
            else:
                continue

            key = (incident.incident_id, event)
            if key in self._dispatched:
                continue

            # Record before delivery so repeated polling never duplicates a transition.
            self._dispatched.add(key)
            started = time.perf_counter()
            delivery = {"incident_id": incident.incident_id, "status": event, "outcome": "failed"}
            try:
                await asyncio.to_thread(
                    self.slack_client.send_message,
                    payload,
                    channel=self.channel,
                )
                delivery["outcome"] = "delivered"
            except Exception:
                log.warning(
                    "Slack delivery failed for incident %s (%s); incident state is preserved.",
                    incident.incident_id,
                    event,
                )
            finally:
                delivery["dispatch_seconds"] = time.perf_counter() - started
                delivery["completed_at"] = datetime.now(timezone.utc).isoformat()
                self.deliveries.append(delivery)