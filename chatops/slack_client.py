from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import httpx


def _get_env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is not None and value.strip() == "":
        return default
    return value


def verify_slack_signature(
    body: bytes | str,
    timestamp: str,
    signature: str,
    signing_secret: str,
) -> bool:
    if not timestamp or not signature or not signing_secret:
        return False

    payload = body.encode("utf-8") if isinstance(body, str) else body
    expected = hmac.new(
        signing_secret.encode("utf-8"),
        f"v0:{timestamp}:".encode("utf-8") + payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"v0={expected}", signature)


class SlackClient:
    def __init__(
        self,
        bot_token: str | None = None,
        signing_secret: str | None = None,
        webhook_url: str | None = None,
    ) -> None:
        self.bot_token = bot_token or _get_env("SLACK_BOT_TOKEN")
        self.signing_secret = signing_secret or _get_env("SLACK_SIGNING_SECRET")
        self.webhook_url = webhook_url or _get_env("SLACK_WEBHOOK_URL")

    def send_message(self, payload: dict[str, Any], channel: str | None = None) -> httpx.Response:
        if self.webhook_url:
            response = httpx.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            return response

        if not self.bot_token:
            raise RuntimeError("SLACK_BOT_TOKEN is required when no webhook URL is configured.")

        headers = {"Authorization": f"Bearer {self.bot_token}", "Content-Type": "application/json"}
        data = dict(payload)
        if channel:
            data.setdefault("channel", channel)

        response = httpx.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            json=data,
            timeout=10,
        )
        response.raise_for_status()
        return response

    def verify_request(self, body: bytes | str, timestamp: str, signature: str) -> bool:
        if not self.signing_secret:
            raise RuntimeError("SLACK_SIGNING_SECRET is required for interactive request verification.")
        return verify_slack_signature(body, timestamp, signature, self.signing_secret)
