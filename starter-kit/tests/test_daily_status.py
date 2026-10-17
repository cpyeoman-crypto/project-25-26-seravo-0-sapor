import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from test_kit import HUGE_INT, MAC, NESTED_JSON, OVERSIZED_JSON, TEST_DIR, daily_status, fleet_poll


NOW = 100000
METRICS = {
    "kernel": "test-kernel", "load": (0.1, 0.2, 0.3), "cores": 2,
    "mem_pct": 25, "disk_pct": 10, "disk_free_gb": 20,
}
PROJECT = ("Project: healthy\nChecks: 2/2 passed", False)


def fleet_state(stamp=NOW):
    return {"a": {"up": True, "stale": False, "role": "test",
                  "channel": "lan", "checked_at": stamp}}


class DailyReportTests(unittest.TestCase):
    def report(self, state=None, project=PROJECT, **kwargs):
        return daily_status.build_report(
            METRICS, fleet_state() if state is None else state,
            project=project, now=NOW, **kwargs
        )

    def test_only_fresh_fleet_and_successful_project_can_be_green(self):
        title, body, attention = self.report()
        self.assertFalse(attention)
        self.assertIn("ALL GREEN", title)
        self.assertIn(PROJECT[0], body)
        self.assertIn("1/1 reachable", body)

    def test_fleet_timestamp_boundary_and_invalid_values(self):
        for stamp, attention in (
            (NOW, False), (NOW - 600, False), (NOW - 601, True),
            (NOW + 1, True), (None, True), (True, True), ("100000", True),
        ):
            with self.subTest(stamp=stamp):
                title, _, actual = self.report(state=fleet_state(stamp))
                self.assertEqual(actual, attention)
                self.assertEqual("ATTENTION" in title, attention)

    def test_missing_timestamp_or_empty_fleet_is_not_green(self):
        missing = fleet_state()
        del missing["a"]["checked_at"]
        for state in (missing, {}):
            with self.subTest(state=state):
                self.assertTrue(self.report(state=state)[2])

    def test_project_missing_stale_invalid_or_blocked_overrides_healthy_nodes(self):
        for project in (
            None, ("Project: monitoring data missing, stale or invalid", True),
            ("Connector-2: blocked; prerequisites outstanding: approval", True),
        ):
            with self.subTest(project=project):
                title, body, attention = self.report(project=project)
                self.assertTrue(attention)
                self.assertIn("ATTENTION", title)
                self.assertIn("Project maintenance", body)

    def test_disk_down_stale_and_fleet_coverage_warnings_remain(self):
        state = fleet_state()
        state["a"].update(up=False, stale=True)
        metrics = dict(METRICS, disk_pct=95)
        title, body, attention = daily_status.build_report(
            metrics, state, project=PROJECT, fleet_issue="Fleet coverage incomplete", now=NOW
        )
        self.assertTrue(attention)
        self.assertIn("ATTENTION", title)
        for warning in ("Down: a", "Not reporting: a", "95%", "Fleet coverage incomplete"):
            self.assertIn(warning, body)

    def test_poll_records_check_timestamp_for_up_and_down_nodes(self):
        manifest = {"nodes": [{"name": "a", "macs": [MAC]}]}
        for reachable in (False, True):
            with self.subTest(reachable=reachable):
                state, _ = fleet_poll.poll_once(
                    manifest, {}, {MAC: ["127.0.0.10"]}, {},
                    lambda address, port: reachable, NOW
                )
                self.assertEqual(state["a"]["checked_at"], NOW)
                self.assertEqual(state["a"]["up"], reachable)


class DailyCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=TEST_DIR)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.state = self.root / "fleet.json"
        self.state.write_text(json.dumps(fleet_state()), encoding="utf-8")
        self.manifest = {"nodes": [{"name": "a", "macs": [MAC]}]}

    def invoke(self, *, send=False, delivered=True, project=PROJECT):
        argv = ["daily_status.py", "--state", str(self.state),
                "--manifest", str(self.root / "manifest.json"),
                "--project-state", str(self.root / "project.json")]
        if send:
            argv.append("--send")
        with patch.object(sys, "argv", argv), \
                patch.object(daily_status, "host_metrics", return_value=METRICS), \
                patch.object(daily_status.time, "time", return_value=NOW), \
                patch.object(daily_status.resolver, "load_manifest", return_value=self.manifest), \
                patch.object(daily_status.project_monitor, "summary", return_value=project), \
                patch.object(daily_status.ntfy, "compose", return_value="safe test report"), \
                patch.object(daily_status.ntfy, "send", return_value=delivered) as notify, \
                redirect_stdout(io.StringIO()) as output:
            code = daily_status.main()
        return code, notify, output.getvalue()

    def test_healthy_dry_run_exits_zero_without_delivery(self):
        code, notify, output = self.invoke()
        self.assertEqual(code, 0)
        notify.assert_not_called()
        self.assertEqual(output.strip(), "safe test report")

    def test_attention_dry_run_exits_nonzero(self):
        self.assertEqual(self.invoke(project=("Project: attention", True))[0], 1)

    def test_successful_send_preserves_health_exit_and_priority(self):
        for project, expected, priority in (
            (PROJECT, 0, "default"), (("Project: attention", True), 1, "high")
        ):
            with self.subTest(attention=project[1]):
                code, notify, output = self.invoke(send=True, project=project)
                self.assertEqual(code, expected)
                self.assertEqual(notify.call_args.kwargs["priority"], priority)
                self.assertEqual(output, "")

    def test_delivery_failure_exits_nonzero_even_when_healthy(self):
        self.assertEqual(self.invoke(send=True, delivered=False)[0], 1)

    def test_missing_malformed_or_untyped_fleet_never_exits_success(self):
        for raw in (None, "not-json", "[]", '{"a": null}',
                    '{"a": {"up": "yes", "stale": false}}'):
            with self.subTest(raw=raw):
                if raw is None:
                    self.state.unlink()
                else:
                    self.state.write_text(raw, encoding="utf-8")
                self.assertEqual(self.invoke()[0], 1)

    def test_configured_node_missing_from_state_is_attention(self):
        self.manifest["nodes"].append({"name": "b", "macs": [MAC]})
        self.assertEqual(self.invoke()[0], 1)

    def test_giant_nested_and_oversized_fleet_data_exit_attention(self):
        for kind, raw in (
            ("giant timestamp", json.dumps(fleet_state(HUGE_INT))),
            ("deeply nested", NESTED_JSON),
            ("oversized", OVERSIZED_JSON),
        ):
            with self.subTest(kind=kind):
                self.state.write_text(raw, encoding="utf-8")
                self.assertEqual(self.invoke()[0], 1)


if __name__ == "__main__":
    unittest.main()
