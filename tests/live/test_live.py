"""Against real webhooks, when their URLs are in the environment — skipped anywhere else. Each sends one sample event and expects it accepted."""

import os
import unittest

from apx_notify import NotifyPlugin
from apx_notify.sample import sample

URLS = {
    route: os.environ.get(f"APX_NOTIFY_LIVE_{route.upper()}_URL", "")
    for route in ("slack", "discord", "teams", "webhook")
}


class Values(dict):
    pass


@unittest.skipUnless(any(URLS.values()), "needs APX_NOTIFY_LIVE_<ROUTE>_URL")
class LiveTest(unittest.TestCase):
    def test_each_configured_channel_accepts_a_sample(self):
        options = Values(
            {f"{route}_url": url for route, url in URLS.items() if url},
            webhook_secret=os.environ.get("APX_NOTIFY_LIVE_WEBHOOK_SECRET", "live"),
        )
        plugin = NotifyPlugin()
        event = sample("deployment.succeeded")

        for route in plugin.routes(event, options):
            plugin.deliver(event, route, options)
