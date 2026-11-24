"""HTTPS POST to a webhook. The answer decides what happens next: a 2xx is delivered, a 408, 429 or 5xx (or no answer) is tried again later, any other status is refused for good. A URL that resolves to a private, loopback or link-local address is refused unless the operator set `APX_NOTIFY_ALLOW_PRIVATE=1`, so an organization cannot aim the platform's worker at its own network."""

from __future__ import annotations

import ipaddress
import os
import socket
import urllib.error
import urllib.request
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


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def private_allowed() -> bool:
    return os.environ.get("APX_NOTIFY_ALLOW_PRIVATE", "") == "1"


def guard(channel: str, url: str) -> None:
    parts = urlsplit(url)
    allowed = ("https", "http") if private_allowed() else ("https",)

    if parts.scheme not in allowed or not parts.hostname:
        raise Refused(f"{channel}: the URL must start with https://")

    if private_allowed():
        return

    try:
        answers = socket.getaddrinfo(parts.hostname, parts.port or 443)
    except socket.gaierror:
        raise Unavailable(f"{channel}: the webhook's host does not resolve") from None

    for answer in answers:
        address = ipaddress.ip_address(answer[4][0].split("%")[0])

        if not address.is_global:
            raise Refused(f"{channel}: the URL points at a private address")


class Https(Transport):
    def __init__(self, timeout: float = TIMEOUT) -> None:
        self.timeout = timeout
        self.opener = urllib.request.build_opener(NoRedirect)

    def post(self, channel: str, url: str, body: bytes, headers: dict[str, str]) -> int:
        guard(channel, url)
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                **headers,
            },
        )

        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                status = response.status
        except urllib.error.HTTPError as e:
            status = e.code
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            reason = getattr(e, "reason", e)

            raise Unavailable(
                f"{channel}: the webhook did not answer ({type(reason).__name__})"
            ) from None

        if 200 <= status < 300:
            return status

        if status in AGAIN or status >= 500:
            raise Unavailable(f"{channel}: the webhook answered {status}")

        raise Refused(f"{channel}: the webhook answered {status}")
