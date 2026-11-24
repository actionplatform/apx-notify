import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

from action_platform.core.exception import ActionPlatformError

from apx_notify.transport import Https, Refused, Unavailable, guard


class Receiver(BaseHTTPRequestHandler):
    answers: list[int] = []
    seen: list = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Receiver.seen.append((self.path, self.headers, body))
        status = Receiver.answers.pop(0) if Receiver.answers else 200
        self.send_response(status)

        if status == 302:
            self.send_header("Location", "http://169.254.169.254/")

        self.end_headers()

    def log_message(self, *args):
        pass


class GuardTest(unittest.TestCase):
    def test_only_https_to_public_addresses(self):
        with mock.patch.dict(os.environ, {"APX_NOTIFY_ALLOW_PRIVATE": ""}):
            for url in (
                "http://hooks.slack.com/x",
                "https://127.0.0.1/x",
                "https://169.254.169.254/latest",
                "https://10.0.0.8/hook",
                "https://[::1]/x",
                "file:///etc/passwd",
            ):
                with self.assertRaises(Refused, msg=url):
                    guard("webhook", url)

            with mock.patch(
                "socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("192.168.1.10", 443))],
            ):
                with self.assertRaises(Refused):
                    guard("webhook", "https://looks-public.test/x")

            with mock.patch(
                "socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("52.1.2.3", 443))],
            ):
                guard("webhook", "https://hooks.slack.com/x")


class PinningTest(unittest.TestCase):
    def test_the_connection_goes_to_the_address_that_was_checked(self):
        connected = []

        def refuse(address, timeout):
            connected.append(address)
            raise ConnectionRefusedError()

        with (
            mock.patch.dict(os.environ, {"APX_NOTIFY_ALLOW_PRIVATE": ""}),
            mock.patch(
                "socket.getaddrinfo",
                return_value=[(2, 1, 6, "", ("52.1.2.3", 443))],
            ),
            mock.patch("socket.create_connection", side_effect=refuse),
        ):
            with self.assertRaises(Unavailable):
                Https().post("slack", "https://hooks.slack.com/services/x", b"{}", {})

        self.assertEqual(connected, [("52.1.2.3", 443)])


class HttpsTest(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), Receiver)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"
        Receiver.answers, Receiver.seen = [], []
        patcher = mock.patch.dict(os.environ, {"APX_NOTIFY_ALLOW_PRIVATE": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_posts_json_with_the_headers(self):
        status = Https().post(
            "webhook", self.url, b'{"a":1}', {"X-AP-Event": "ci.failed"}
        )

        path, headers, body = Receiver.seen[0]
        self.assertEqual((status, path, json.loads(body)), (200, "/hook", {"a": 1}))
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["X-AP-Event"], "ci.failed")

    def test_the_answer_decides_retry_or_refusal(self):
        for status, error in (
            (500, Unavailable),
            (429, Unavailable),
            (404, Refused),
            (302, Refused),
        ):
            Receiver.answers = [status]

            with self.assertRaises(error, msg=status) as raised:
                Https().post("slack", self.url, b"{}", {})

            self.assertEqual(
                isinstance(raised.exception, ActionPlatformError), error is Refused
            )
            self.assertNotIn("127.0.0.1", str(raised.exception))

        self.assertEqual(len(Receiver.seen), 4)

    def test_nobody_listening_is_tried_again(self):
        self.server.shutdown()
        self.server.server_close()

        with self.assertRaises(Unavailable):
            Https(timeout=2).post("teams", self.url, b"{}", {})

    def test_the_cli_sends_a_signed_sample(self):
        from typer.testing import CliRunner

        from apx_notify.cli import app

        result = CliRunner().invoke(
            app,
            ["test", "webhook", "--kind", "release.created"],
            env={"APX_NOTIFY_URL": self.url, "APX_NOTIFY_SECRET": "s"},
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("webhook: delivered (200)", result.output)
        _, headers, body = Receiver.seen[0]
        self.assertTrue(headers["X-AP-Signature-256"].startswith("sha256="))
        self.assertEqual(json.loads(body)["kind"], "release.created")
