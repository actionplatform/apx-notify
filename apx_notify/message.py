"""What an event says to a person, before any channel shapes it: a title, a few lines, where to look, and whether it is good news."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from action_platform.abc import Event

Tone = Literal["good", "bad", "info"]

CHANGELOG_LINES = 12
LINE = 300


@dataclass(frozen=True)
class Message:
    title: str
    tone: Tone
    lines: list[str] = field(default_factory=list)
    link: str | None = None
    links: list[tuple[str, str]] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join([self.title, *self.lines])


def _clip(text: Any, limit: int = LINE) -> str:
    value = " ".join(str(text or "").split())

    return value if len(value) <= limit else value[: limit - 1] + "…"


def _where(event: Event) -> str:
    return "/".join(p for p in (event.project, event.app) if p) or event.organization


def _stage(payload: dict[str, Any]) -> str:
    return f" to {payload['stage']}" if payload.get("stage") else ""


def _version(payload: dict[str, Any]) -> str:
    return str(payload.get("version") or payload.get("tag") or "a new version")


def _by(event: Event) -> list[str]:
    return [f"by {event.actor}"] if event.actor else []


def _target(payload: dict[str, Any]) -> list[str]:
    parts = [str(payload[k]) for k in ("target", "executor") if payload.get(k)]

    return [" · ".join(parts)] if parts else []


def _release(event: Event) -> Message:
    p = event.payload
    lines = [_clip(p["name"])] if p.get("name") else []
    changelog = [
        _clip(line) for line in str(p.get("changelog") or "").splitlines() if line
    ]
    lines += changelog[:CHANGELOG_LINES]

    if len(changelog) > CHANGELOG_LINES:
        lines.append(f"… {len(changelog) - CHANGELOG_LINES} more lines")

    pre = " (pre-release)" if p.get("prerelease") else ""

    return Message(
        f"Released {p.get('tag') or _version(p)} of {_where(event)}{pre}",
        "info",
        lines + _by(event),
        event.url,
    )


def _deployment(event: Event) -> Message:
    p = event.payload
    what = f"{_version(p)} of {_where(event)}"
    links = [("Run", p["url"])] if p.get("url") else []

    if event.kind == "deployment.started":
        return Message(
            f"Deploying {what}{_stage(p)}",
            "info",
            _target(p) + _by(event),
            event.url,
            links,
        )

    if event.kind == "deployment.failed":
        error = [_clip(p["error"])] if p.get("error") else []

        return Message(
            f"Deploy of {what}{_stage(p)} failed",
            "bad",
            error + _target(p) + _by(event),
            event.url,
            links,
        )

    if event.kind == "deployment.verified":
        stage = f" on {p['stage']}" if p.get("stage") else ""

        return Message(
            f"{what} is live{stage}",
            "good",
            _target(p),
            event.url,
            [("Open", p["url"])] if p.get("url") else [],
        )

    return Message(
        f"Deployed {what}{_stage(p)}",
        "good",
        _target(p) + _by(event),
        event.url,
        links,
    )


def _blocked(event: Event) -> Message:
    p = event.payload
    lines = []

    for check in p.get("checks") or []:
        line = f"{check.get('id')}: {_clip(check.get('detail'))}"
        lines.append(line + (f" — {_clip(check['fix'])}" if check.get("fix") else ""))

    stage = f" for {p['stage']}" if p.get("stage") else ""

    return Message(
        f"{p.get('tag') or 'A release'} of {_where(event)} is blocked{stage}",
        "bad",
        lines,
        event.url,
    )


def _ci(event: Event) -> Message:
    p = event.payload
    run = " ".join(str(p[k]) for k in ("name", "run") if p.get(k))

    return Message(
        f"CI failed on {p.get('tag') or 'a release tag'} of {_where(event)}",
        "bad",
        ([f"run {run}"] if run else []) + _by(event),
        event.url,
        [("Run", p["url"])] if p.get("url") else [],
    )


def compose(event: Event) -> Message:
    if event.kind == "release.created":
        return _release(event)

    if event.kind.startswith("deployment."):
        return _deployment(event)

    if event.kind == "readiness.blocked":
        return _blocked(event)

    if event.kind == "ci.failed":
        return _ci(event)

    return Message(f"{event.kind} in {_where(event)}", "info", _by(event), event.url)
