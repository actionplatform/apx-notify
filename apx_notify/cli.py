"""`action-platform notify …` — check a webhook from this machine before an organization saves it on the platform."""

from __future__ import annotations

import typer
from action_platform.core.exception import ActionPlatformError

from apx_notify.channels import CHANNELS
from apx_notify.message import compose
from apx_notify.sample import sample
from apx_notify.transport import Https, Unavailable

app = typer.Typer(
    help="Notifications: Slack, Discord, Teams, webhook.", no_args_is_help=True
)


@app.callback()
def notify() -> None:
    """Notifications: Slack, Discord, Teams, webhook."""


@app.command("test")
def test(
    route: str = typer.Argument(..., help="slack, discord, teams or webhook"),
    url: str = typer.Option(
        ...,
        envvar="APX_NOTIFY_URL",
        prompt="Webhook URL",
        hide_input=True,
        help="Read from APX_NOTIFY_URL or asked for, so it stays out of the shell history.",
    ),
    secret: str = typer.Option(
        "",
        envvar="APX_NOTIFY_SECRET",
        help="The signing secret, for the webhook route.",
    ),
    kind: str = typer.Option("deployment.succeeded", help="The event kind to send."),
) -> None:
    """Send a sample event to a webhook and say whether it arrived."""
    channel = CHANNELS.get(route)

    if channel is None:
        raise typer.BadParameter(f"{route}: one of {', '.join(CHANNELS)}")

    if route == "webhook" and not secret:
        raise typer.BadParameter(
            "the webhook route needs --secret or APX_NOTIFY_SECRET"
        )

    event = sample(kind)
    body = channel.body(compose(event), event)

    try:
        status = Https().post(route, url, body, channel.headers(body, event, secret))
    except (ActionPlatformError, Unavailable) as e:
        typer.echo(str(e), err=True)

        raise typer.Exit(1)

    typer.echo(f"{route}: delivered ({status})")
