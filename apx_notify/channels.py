"""The four channels: Slack and Discord incoming webhooks, a Microsoft Teams workflow webhook (an Adaptive Card), and a generic webhook that receives the event envelope signed with HMAC-SHA256."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING, Any

from apx_notify.abc import Channel
from apx_notify.message import Message

if TYPE_CHECKING:
    from action_platform.abc import Event

COLORS = {"good": 0x2EB67D, "bad": 0xE01E5A, "info": 0x4A90D9}
TEAMS_COLORS = {"good": "Good", "bad": "Attention", "info": "Accent"}


def _json(data: Any) -> bytes:
    return json.dumps(data, separators=(",", ":"), sort_keys=True).encode()


def _slack_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Slack(Channel):
    name = "slack"

    def body(self, message: Message, event: Event) -> bytes:
        title = f"*{_slack_escape(message.title)}*"

        if message.link:
            title = f"*<{message.link}|{_slack_escape(message.title)}>*"

        lines = [title, *(_slack_escape(line) for line in message.lines)]
        lines += [f"<{url}|{_slack_escape(label)}>" for label, url in message.links]

        return _json({"text": "\n".join(lines), "unfurl_links": False})


class Discord(Channel):
    name = "discord"

    def body(self, message: Message, event: Event) -> bytes:
        lines = list(message.lines)
        lines += [f"[{label}]({url})" for label, url in message.links]
        embed: dict[str, Any] = {
            "title": message.title[:256],
            "description": "\n".join(lines)[:4000],
            "color": COLORS[message.tone],
        }

        if message.link:
            embed["url"] = message.link

        return _json({"embeds": [embed], "allowed_mentions": {"parse": []}})


class Teams(Channel):
    name = "teams"

    def body(self, message: Message, event: Event) -> bytes:
        blocks: list[dict[str, Any]] = [
            {
                "type": "TextBlock",
                "text": message.title,
                "weight": "Bolder",
                "size": "Medium",
                "color": TEAMS_COLORS[message.tone],
                "wrap": True,
            }
        ]
        blocks += [
            {"type": "TextBlock", "text": line, "wrap": True, "spacing": "Small"}
            for line in message.lines
        ]
        actions = [
            {"type": "Action.OpenUrl", "title": label, "url": url}
            for label, url in ([("Open", message.link)] if message.link else [])
            + message.links
        ]
        card: dict[str, Any] = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": blocks,
        }

        if actions:
            card["actions"] = actions

        return _json(
            {
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": card,
                    }
                ],
            }
        )


def signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class Webhook(Channel):
    """The envelope as JSON. `X-AP-Signature-256` is `sha256=<hex HMAC of the raw body>` under the organization's secret; `X-AP-Delivery` is the event's id, stable across retries."""

    name = "webhook"

    def body(self, message: Message, event: Event) -> bytes:
        return _json(event.as_dict())

    def headers(self, body: bytes, event: Event, secret: str) -> dict[str, str]:
        return {
            "X-AP-Event": event.kind,
            "X-AP-Delivery": event.id,
            "X-AP-Signature-256": signature(secret, body),
        }


CHANNELS: dict[str, Channel] = {
    c.name: c for c in (Slack(), Discord(), Teams(), Webhook())
}
