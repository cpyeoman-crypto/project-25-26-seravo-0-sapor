import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ntfy_reports as reports  # noqa: E402


class Response:
    def __init__(self, body):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


class NtfyReportsTests(unittest.TestCase):
    def test_fetches_multiple_topics_and_sorts_messages(self):
        responses = [
            Response(json.dumps({"event": "message", "time": 20, "message": "report"})),
            Response(json.dumps({"event": "message", "time": 10, "message": "alert"})),
        ]
        opener = Mock(side_effect=responses)
        messages = reports.fetch_topics(
            "https://ntfy.example", ["fleet_reports", "fleet_alerts"],
            since="12h", limit=7, opener=opener,
        )
        self.assertEqual([item["message"] for item in messages], ["alert", "report"])
        self.assertEqual([item["source_topic"] for item in messages],
                         ["fleet_alerts", "fleet_reports"])
        self.assertEqual(opener.call_count, 2)

    def test_fetches_optional_authentication(self):
        opener = Mock(return_value=Response(""))
        reports.fetch_messages("https://ntfy.example", "fleet_reports", token="sample", opener=opener)
        self.assertTrue(opener.call_args.args[0].get_header("Authorization").startswith("Bearer "))

    def test_caps_results_if_server_ignores_limit(self):
        events = [{"event": "message", "time": i, "message": str(i)} for i in range(5)]
        opener = Mock(return_value=Response("\n".join(map(json.dumps, events))))
        messages = reports.fetch_messages("https://ntfy.example", "fleet_reports", limit=2, opener=opener)
        self.assertEqual([message["message"] for message in messages], ["3", "4"])

    def test_bad_timestamp_does_not_break_aggregation(self):
        responses = [
            Response(json.dumps({"event": "message", "time": "bad", "message": "unknown-time"})),
            Response(json.dumps({"event": "message", "time": 1, "message": "dated"})),
        ]
        messages = reports.fetch_topics(
            "https://ntfy.example", ["one", "two"], opener=Mock(side_effect=responses),
        )
        self.assertEqual([item["message"] for item in messages], ["unknown-time", "dated"])

    def test_empty_response_returns_no_messages(self):
        self.assertEqual(
            reports.fetch_messages("https://ntfy.example", "fleet_reports",
                                   opener=Mock(return_value=Response(""))),
            [],
        )

    def test_rejects_unsafe_topics_servers_and_limits(self):
        for args in (
            ("https://ntfy.example", "../topic", "24h", 50),
            ("file:///tmp", "topic", "24h", 50),
            ("https://user:pw@ntfy.example", "topic", "24h", 50),
            ("https://ntfy.example?q=1", "topic", "24h", 50),
            ("https://ntfy.example", "topic", "24h", 101),
            ("https://ntfy.example", "topic", "24h", 0),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                reports.endpoint(*args)

    def test_escapes_message_content_and_withholds_topic_names(self):
        rendered = reports.render_report(
            [{"time": 0, "title": "<script>", "priority": 4,
              "tags": ["warning"], "message": "<img src=x onerror=alert(1)>"}],
            ["secret_topic_name"],
        )
        self.assertIn("&lt;script&gt;", rendered)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("secret_topic_name", rendered)

    def test_topics_come_from_configuration(self):
        with patch.dict("os.environ", {"NTFY_TOPICS": "one, two, one"}):
            self.assertEqual(reports.topics(), ["one", "two"])
        with patch.dict("os.environ", {"NTFY_TOPICS": ""}, clear=False), \
                patch.object(reports.ntfy_notify, "setting", return_value=None):
            self.assertEqual(reports.topics(), [])

    def test_placeholder_topics_are_refused(self):
        for value in ("x-topic", "mynet-x", "<topic>"):
            with self.subTest(value=value), \
                    patch.dict("os.environ", {"NTFY_TOPICS": value}), \
                    self.assertRaises(ValueError):
                reports.topics()

    def test_main_refuses_to_run_unconfigured(self):
        with patch.object(reports, "topics", return_value=[]):
            self.assertEqual(reports.main([]), 1)


if __name__ == "__main__":
    unittest.main()
