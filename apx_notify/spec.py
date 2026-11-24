"""What an organization asked for, read once from the plugin's options: the URL of each channel, the signing secret, and which events of which projects it wants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from action_platform.abc import Event
    from action_platform.plugins import Options

ROUTES = ("slack", "discord", "teams", "webhook")
DEFAULT_EVENTS = (
    "release.created",
    "deployment.succeeded",
    "deployment.failed",
    "readiness.blocked",
    "ci.failed",
)


def _names(value: Any) -> tuple[str, ...]:
    if not value:
        return ()

    items = value if isinstance(value, (list, tuple)) else str(value).split(",")

    return tuple(dict.fromkeys(i.strip() for i in items if str(i).strip()))


@dataclass(frozen=True)
class Settings:
    urls: dict[str, str]
    secret: str
    events: tuple[str, ...]
    projects: tuple[str, ...]

    @classmethod
    def of(cls, options: Options) -> Settings:
        return cls(
            urls={
                route: str(options.get(f"{route}_url") or "").strip()
                for route in ROUTES
            },
            secret=str(options.get("webhook_secret") or ""),
            events=_names(options.get("events")) or DEFAULT_EVENTS,
            projects=_names(options.get("projects")),
        )

    def wants(self, event: Event) -> bool:
        if event.kind not in self.events:
            return False

        return not self.projects or event.project in self.projects

    def routes(self, event: Event) -> list[str]:
        if not self.wants(event):
            return []

        return [route for route in ROUTES if self.urls[route]]
