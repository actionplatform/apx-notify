"""One contract per responsibility: a `Channel` turns a message into the body one service accepts, a `Transport` carries it there and says whether to try again."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from action_platform.abc import Event

    from apx_notify.message import Message


class Channel(ABC):
    """Where a message goes: Slack, Discord, Teams, a generic webhook."""

    name: str

    @abstractmethod
    def body(self, message: Message, event: Event) -> bytes:
        """The request body the service accepts."""

    def headers(self, body: bytes, event: Event, secret: str) -> dict[str, str]:
        """Headers beyond `Content-Type: application/json`."""
        return {}


class Transport(ABC):
    """Sends a body to a URL. Raises `Refused` when the answer will not change on a retry and `Unavailable` when it may."""

    @abstractmethod
    def post(self, channel: str, url: str, body: bytes, headers: dict[str, str]) -> int:
        """The status the service answered with, once it is a 2xx."""
