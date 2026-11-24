import hmac
import json
import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from action_platform.abc import Event
from action_platform.core.exception import ActionPlatformError
from action_platform.plugins import Loaded, Plugins, PluginState, registry

from apx_notify import NotifyPlugin
from apx_notify.transport import Refused, Unavailable
from tests.fake import FakeTransport


class Values:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


def event(kind="deployment.succeeded", project="shop", **payload):
    return Event(
        kind,
        "acme",
        project,
        "api",
        actor="ana",
        payload={"stage": "prod", "version": "1.2.0", "target": "app", **payload},
        url="https://ap.test/projects/p1/apps/a1/deployments",
        id="e1",
        at="2026-11-24T20:00:00+00:00",
    )


ALL = {
    "slack_url": "https://hooks.slack.com/services/T/B/x",
    "discord_url": "https://discord.com/api/webhooks/1/x",
    "teams_url": "https://example.webhook.office.com/x",
    "webhook_url": "https://hooks.acme.test/ap",
    "webhook_secret": "s3cret",
}


class RoutesTest(unittest.TestCase):
    def setUp(self):
        self.plugin = NotifyPlugin(FakeTransport())

    def test_every_configured_channel_is_a_route(self):
        self.assertEqual(
            self.plugin.routes(event(), Values(ALL)),
            ["slack", "discord", "teams", "webhook"],
        )
        self.assertEqual(
            self.plugin.routes(event(), Values({"discord_url": ALL["discord_url"]})),
            ["discord"],
        )
        self.assertEqual(self.plugin.routes(event(), Values({})), [])

    def test_started_and_verified_are_opt_in(self):
        slack = {"slack_url": ALL["slack_url"]}

        for kind in ("deployment.started", "deployment.verified"):
            self.assertEqual(self.plugin.routes(event(kind), Values(slack)), [])

        chosen = {**slack, "events": "deployment.started, deployment.failed"}

        self.assertEqual(
            self.plugin.routes(event("deployment.started"), Values(chosen)), ["slack"]
        )
        self.assertEqual(self.plugin.routes(event(), Values(chosen)), [])

    def test_projects_filter_by_slug(self):
        only = {"slack_url": ALL["slack_url"], "projects": "shop,blog"}

        self.assertEqual(
            self.plugin.routes(event(project="blog"), Values(only)), ["slack"]
        )
        self.assertEqual(self.plugin.routes(event(project="crm"), Values(only)), [])


class DeliverTest(unittest.TestCase):
    def setUp(self):
        self.transport = FakeTransport()
        self.plugin = NotifyPlugin(self.transport)

    def sent(self, route, e=None):
        self.plugin.deliver(e or event(), route, Values(ALL))
        channel, url, body, headers = self.transport.sent[-1]

        self.assertEqual((channel, url), (route, ALL[f"{route}_url"]))

        return body, headers

    def test_slack_gets_a_linked_title_and_the_lines(self):
        body, _ = self.sent("slack", event("deployment.failed", error="boom <x>"))

        self.assertEqual(
            body["text"].splitlines()[0],
            "*<https://ap.test/projects/p1/apps/a1/deployments|Deploy of 1.2.0 of shop/api to prod failed>*",
        )
        self.assertIn("boom &lt;x&gt;", body["text"])
        self.assertFalse(body["unfurl_links"])

    def test_discord_gets_an_embed_and_never_pings(self):
        body, _ = self.sent("discord")

        embed = body["embeds"][0]
        self.assertEqual(embed["title"], "Deployed 1.2.0 of shop/api to prod")
        self.assertEqual(
            embed["url"], "https://ap.test/projects/p1/apps/a1/deployments"
        )
        self.assertEqual(body["allowed_mentions"], {"parse": []})

    def test_teams_gets_an_adaptive_card_with_a_link(self):
        body, _ = self.sent("teams")

        attachment = body["attachments"][0]
        self.assertEqual(
            attachment["contentType"], "application/vnd.microsoft.card.adaptive"
        )
        card = attachment["content"]
        self.assertEqual(card["body"][0]["text"], "Deployed 1.2.0 of shop/api to prod")
        self.assertEqual(
            card["actions"][0]["url"], "https://ap.test/projects/p1/apps/a1/deployments"
        )

    def test_the_webhook_gets_the_envelope_signed(self):
        self.plugin.deliver(event(), "webhook", Values(ALL))
        _, _, body, headers = self.transport.sent[-1]
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        expected = "sha256=" + hmac.new(b"s3cret", raw, sha256).hexdigest()

        self.assertEqual(headers["X-AP-Signature-256"], expected)
        self.assertEqual(headers["X-AP-Event"], "deployment.succeeded")
        self.assertEqual(headers["X-AP-Delivery"], "e1")
        self.assertEqual(
            (body["kind"], body["organization"], body["project"]),
            ("deployment.succeeded", "acme", "shop"),
        )

    def test_a_webhook_without_a_secret_is_refused(self):
        unsigned = {k: v for k, v in ALL.items() if k != "webhook_secret"}

        with self.assertRaises(ActionPlatformError):
            self.plugin.deliver(event(), "webhook", Values(unsigned))

        self.assertEqual(self.transport.sent, [])

    def test_a_route_whose_url_was_removed_is_refused(self):
        with self.assertRaises(Refused):
            self.plugin.deliver(event(), "slack", Values({}))

    def test_a_server_error_is_retried_and_a_client_error_is_not(self):
        self.transport.answers = {"slack": 503, "discord": 404}

        with self.assertRaises(Unavailable) as again:
            self.plugin.deliver(event(), "slack", Values(ALL))

        self.assertNotIsInstance(again.exception, ActionPlatformError)

        with self.assertRaises(ActionPlatformError) as refused:
            self.plugin.deliver(event(), "discord", Values(ALL))

        self.assertNotIn("discord.com", str(refused.exception))


class RegistryTest(unittest.TestCase):
    def test_the_core_sees_a_plugin_that_takes_events(self):
        with TemporaryDirectory() as tmp:
            plugins = Plugins(
                [Loaded(NotifyPlugin(), "apx-notify", "0.1.0")],
                PluginState(file=Path(tmp) / "plugins.json"),
            )
            registry._current = plugins
            self.addCleanup(registry.reset)

            self.assertEqual([r.slug for r in plugins.listeners()], ["notify"])
            row = plugins.rows()[0]

        self.assertTrue(row["events"])
        self.assertEqual(
            {o["key"] for o in row["options"] if o["kind"] == "secret"},
            {"slack_url", "discord_url", "teams_url", "webhook_url", "webhook_secret"},
        )
