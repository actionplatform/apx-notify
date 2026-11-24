"""The plugin: the options an organization fills in, which channels an event goes to, and the delivery the platform's worker runs for each."""

from __future__ import annotations

from typing import TYPE_CHECKING

from action_platform.abc import Option, Plugin, Surface

from apx_notify import cli
from apx_notify.abc import Transport
from apx_notify.channels import CHANNELS
from apx_notify.message import compose
from apx_notify.spec import DEFAULT_EVENTS, Settings
from apx_notify.transport import Https, Refused

if TYPE_CHECKING:
    from action_platform.abc import Event
    from action_platform.plugins import Options

KINDS = (
    "release.created, deployment.started, deployment.succeeded, deployment.failed, "
    "deployment.verified, readiness.blocked, ci.failed"
)


class NotifyPlugin(Plugin):
    slug = "notify"
    name = "Notifications"
    description = "Tell Slack, Discord, Microsoft Teams or a signed webhook when a release is cut, a deploy succeeds or fails, readiness blocks a release or CI fails on a release tag"
    min_core = "0.34"
    needs = [
        "net: the webhook URLs the organization sets (hooks.slack.com, discord.com, the Teams workflow's host, its own endpoint); public addresses only",
        "env: APX_NOTIFY_ALLOW_PRIVATE=1 on the worker lets a webhook reach a private or loopback address (self-hosted platforms)",
    ]
    options = [
        Option(
            "slack_url",
            "Slack webhook URL",
            "secret",
            help="An incoming webhook of the Slack channel (https://hooks.slack.com/services/…).",
            action_label="Create a Slack webhook",
            action_url="https://api.slack.com/messaging/webhooks",
        ),
        Option(
            "discord_url",
            "Discord webhook URL",
            "secret",
            help="Channel settings → Integrations → Webhooks → Copy Webhook URL.",
        ),
        Option(
            "teams_url",
            "Microsoft Teams webhook URL",
            "secret",
            help="The URL of a Teams workflow that posts to a channel when a webhook request is received; the message is an Adaptive Card.",
        ),
        Option(
            "webhook_url",
            "Webhook URL",
            "secret",
            help="Your own HTTPS endpoint: it receives the event envelope as JSON, signed in X-AP-Signature-256.",
        ),
        Option(
            "webhook_secret",
            "Webhook signing secret",
            "secret",
            help="The key of the HMAC-SHA256 signature of the webhook's body; required with a webhook URL.",
        ),
        Option(
            "events",
            "Events",
            help=f"Comma-separated, from: {KINDS}. Empty sends {', '.join(DEFAULT_EVENTS)}.",
        ),
        Option(
            "projects",
            "Projects",
            help="Comma-separated project slugs; empty sends every project's events.",
        ),
    ]

    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport or Https()

    def register(self, surface: Surface) -> None:
        if surface.cli is not None:
            surface.cli.add_typer(cli.app, name="notify")

    def routes(self, event: Event, options: Options) -> list[str]:
        return Settings.of(options).routes(event)

    def deliver(self, event: Event, route: str, options: Options) -> None:
        settings = Settings.of(options)
        channel = CHANNELS.get(route)
        url = settings.urls.get(route, "")

        if channel is None or not url:
            raise Refused(f"{route}: no webhook URL is set any more")

        if route == "webhook" and not settings.secret:
            raise Refused("webhook: set the webhook signing secret")

        body = channel.body(compose(event), event)
        headers = channel.headers(body, event, settings.secret)
        self.transport.post(route, url, body, headers)
        self.logger.info(f"notify: {event.kind} sent to {route}")
