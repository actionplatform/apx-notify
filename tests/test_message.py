import unittest

from action_platform.abc import EVENT_KINDS, Event

from apx_notify.message import compose
from apx_notify.sample import PAYLOADS, sample


def event(kind, **payload):
    return Event(
        kind,
        "acme",
        "shop",
        "api",
        actor="ana",
        payload=payload,
        url="https://ap.test/x",
    )


class ComposeTest(unittest.TestCase):
    def test_every_kind_the_core_raises_has_a_sample_and_a_title(self):
        self.assertEqual(set(PAYLOADS), set(EVENT_KINDS))

        for kind in EVENT_KINDS:
            message = compose(sample(kind))

            self.assertTrue(message.title, kind)
            self.assertNotIn(kind, message.title, kind)

    def test_a_release_carries_its_changelog_clipped(self):
        changelog = "\n".join(f"- change {i}" for i in range(20))
        message = compose(
            event("release.created", tag="v1.3.0", changelog=changelog, prerelease=True)
        )

        self.assertEqual(message.title, "Released v1.3.0 of shop/api (pre-release)")
        self.assertIn("- change 0", message.lines)
        self.assertIn("… 8 more lines", message.lines)
        self.assertEqual(message.lines[-1], "by ana")

    def test_a_blocked_release_lists_each_check_with_its_fix(self):
        message = compose(
            event(
                "readiness.blocked",
                tag="v1.3.0",
                stage="prod",
                checks=[
                    {"id": "aws.permissions", "detail": "denied", "fix": "grant it"}
                ],
            )
        )

        self.assertEqual(message.title, "v1.3.0 of shop/api is blocked for prod")
        self.assertEqual(message.lines, ["aws.permissions: denied — grant it"])
        self.assertEqual(message.tone, "bad")

    def test_a_failed_ci_run_links_the_run(self):
        message = compose(
            event("ci.failed", tag="v1.3.0", run=8, name="publish", url="https://ci/8")
        )

        self.assertEqual(message.title, "CI failed on v1.3.0 of shop/api")
        self.assertEqual(message.links, [("Run", "https://ci/8")])

    def test_an_unknown_kind_still_says_something(self):
        self.assertEqual(compose(event("app.renamed")).title, "app.renamed in shop/api")
