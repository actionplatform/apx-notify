"""The webhooks in memory: every post recorded, the status each service would answer scripted. Bodies are what Slack, Discord, Teams and a webhook receiver read — a test asserts on them, not on the plugin's internals."""

from __future__ import annotations

import json

from apx_notify.abc import Transport
from apx_notify.transport import AGAIN, Refused, Unavailable


class FakeTransport(Transport):
    def __init__(self, answers: dict[str, int] | None = None) -> None:
        self.answers = answers or {}
        self.sent: list[tuple[str, str, dict, dict[str, str]]] = []

    def post(self, channel: str, url: str, body: bytes, headers: dict[str, str]) -> int:
        status = self.answers.get(channel, 200)

        if status in AGAIN or status >= 500:
            raise Unavailable(f"{channel}: the webhook answered {status}")

        if not 200 <= status < 300:
            raise Refused(f"{channel}: the webhook answered {status}")

        self.sent.append((channel, url, json.loads(body), headers))

        return status
