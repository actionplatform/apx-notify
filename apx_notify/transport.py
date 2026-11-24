"""HTTPS POST to a webhook. The answer decides what happens next: a 2xx is delivered, a 408, 429 or 5xx (or no answer) is tried again later, any other status is refused for good. A URL that resolves to a private, loopback or link-local address is refused unless the operator set `APX_NOTIFY_ALLOW_PRIVATE=1`, so an organization cannot aim the platform's worker at its own network: the host is resolved once, checked, and the connection goes to that address — no proxy, no redirect, no second lookup."""

from __future__ import annotations

import http.client
import ipaddress
import os
import socket
import ssl
from urllib.parse import urlsplit

from action_platform.core.exception import ActionPlatformError

from apx_notify.abc import Transport

TIMEOUT = 10.0
AGAIN = {408, 425, 429}
USER_AGENT = "apx-notify"


class Refused(ActionPlatformError):
    """The service said no, or the URL is not one the plugin sends to; a retry would get the same answer."""


class Unavailable(Exception):
    """The service did not take it this time; the job queue tries again."""


def private_allowed() -> bool:
    return os.environ.get("APX_NOTIFY_ALLOW_PRIVATE", "") == "1"


def guard(channel: str, url: str) -> str | None:
    """The address to connect to, checked; None when the operator allows private addresses and the hostname is resolved as usual."""
    parts = urlsplit(url)
    allowed = ("https", "http") if private_allowed() else ("https",)

    if parts.scheme not in allowed or not parts.hostname:
        raise Refused(f"{channel}: the URL must start with https://")

    if private_allowed():
        return None

    try:
        answers = socket.getaddrinfo(
            parts.hostname, parts.port or 443, type=socket.SOCK_STREAM
        )
    except (socket.gaierror, UnicodeError):
        raise Unavailable(f"{channel}: the webhook's host does not resolve") from None

    addresses = [answer[4][0].split("%")[0] for answer in answers]

    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            raise Refused(f"{channel}: the URL points at a private address")

    if not addresses:
        raise Unavailable(f"{channel}: the webhook's host does not resolve")

    return addresses[0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """TLS to `address`, with the certificate and SNI checked against the URL's hostname."""

    def __init__(self, host: str, address: str, port: int, timeout: float) -> None:
        super().__init__(
            host, port, timeout=timeout, context=ssl.create_default_context()
        )
        self.address = address

    def connect(self) -> None:
        sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class Https(Transport):
    def __init__(self, timeout: float = TIMEOUT) -> None:
        self.timeout = timeout

    def _connection(self, url: str, address: str | None) -> http.client.HTTPConnection:
        parts = urlsplit(url)

        if address is not None:
            return PinnedHTTPSConnection(
                parts.hostname, address, parts.port or 443, self.timeout
            )

        if parts.scheme == "https":
            return http.client.HTTPSConnection(
                parts.hostname, parts.port, timeout=self.timeout
            )

        return http.client.HTTPConnection(
            parts.hostname, parts.port, timeout=self.timeout
        )

    def post(self, channel: str, url: str, body: bytes, headers: dict[str, str]) -> int:
        address = guard(channel, url)
        parts = urlsplit(url)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        connection = self._connection(url, address)

        try:
            connection.request(
                "POST",
                path,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": USER_AGENT,
                    **headers,
                },
            )
            status = connection.getresponse().status
        except (OSError, http.client.HTTPException) as e:
            raise Unavailable(
                f"{channel}: the webhook did not answer ({type(e).__name__})"
            ) from None
        finally:
            connection.close()

        if 200 <= status < 300:
            return status

        if status in AGAIN or status >= 500:
            raise Unavailable(f"{channel}: the webhook answered {status}")

        raise Refused(f"{channel}: the webhook answered {status}")
