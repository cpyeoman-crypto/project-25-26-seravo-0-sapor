import json
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ["NTFY_DRY_RUN"] = "1"

import node_pulse  # noqa: E402


def snapshot(**overrides):
    base = {
        "schema": node_pulse.SCHEMA,
        "host": "node",
        "timestamp": "2026-01-01T00:00:00Z",
        "platform": {"system": "Linux", "release": "x", "machine": "x"},
        "uptime_seconds": 90000,
        "load": {"1m": 0.5, "5m": 0.5, "15m": 0.5},
        "cpu_count": 4,
        "memory": {"total_bytes": 100, "available_bytes": 50, "available_pct": 50.0},
        "disks": [{"path": "/", "total_bytes": 100, "used_bytes": 10, "used_pct": 10.0}],
        "failed_units": [],
        "docker": None,
        "mesh": None,
        "temperatures_c": None,
    }
    base.update(overrides)
    return base


class EvaluateIssuesTests(unittest.TestCase):
    def test_healthy_snapshot_has_no_issues(self):
        self.assertEqual(node_pulse.evaluate_issues(snapshot()), {})

    def test_disk_memory_load_unit_docker_mesh_issues(self):
        issues = node_pulse.evaluate_issues(snapshot(
            disks=[{"path": "/", "total_bytes": 100, "used_bytes": 95, "used_pct": 95.0}],
            memory={"total_bytes": 100, "available_bytes": 2, "available_pct": 2.0},
            load={"1m": 9.0, "5m": 9.0, "15m": 9.0},
            cpu_count=1,
            failed_units=["backup.service"],
            docker=[{"name": "db", "image": "db", "state": "restarting", "status": "Restarting"}],
            mesh={"self_online": False, "peers_online": 0, "peers_total": 3},
        ))
        self.assertEqual(
            set(issues),
            {"disk:/", "memory", "load", "unit:backup.service", "docker:db", "mesh"},
        )

    def test_thresholds_are_configurable(self):
        with patch.dict(os.environ, {"NODE_DISK_ALERT_PCT": "50"}):
            issues = node_pulse.evaluate_issues(snapshot(
                disks=[{"path": "/", "total_bytes": 100, "used_bytes": 60, "used_pct": 60.0}],
            ))
        self.assertIn("disk:/", issues)


class StateAndSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"NODE_STATE_DIR": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_save_snapshot_writes_status_and_history(self):
        saved = node_pulse.save_snapshot(snapshot(), {"memory": "low"})
        self.assertFalse(saved["ok"])
        status = json.loads(node_pulse.status_path().read_text(encoding="utf-8"))
        self.assertEqual(status["issues"], [{"key": "memory", "message": "low"}])
        history = node_pulse.history_path().read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(history), 1)

    def test_pulse_state_round_trip_and_since_preserved(self):
        now = "2026-01-02T00:00:00Z"
        first = node_pulse._next_issue_state({"memory": "low"}, {}, now)
        self.assertEqual(first["memory"]["since"], now)
        later = node_pulse._next_issue_state({"memory": "still low"}, first, "2026-01-03T00:00:00Z")
        self.assertEqual(later["memory"]["since"], now)
        node_pulse._write_atomic(node_pulse.pulse_state_path(),
                                 json.dumps({"issues": later, "digest_date": "2026-01-03"}))
        state = node_pulse.load_pulse_state()
        self.assertEqual(state["digest_date"], "2026-01-03")
        self.assertIn("memory", state["issues"])

    def test_corrupt_pulse_state_resets(self):
        node_pulse._write_atomic(node_pulse.pulse_state_path(), "{not json")
        self.assertEqual(node_pulse.load_pulse_state(), {"issues": {}, "digest_date": None})

    def test_resolved_issue_messages(self):
        self.assertEqual(
            node_pulse._resolved_issue_message("unit:x.service", "2026-01-01T00:00:00Z"),
            "systemd unit x.service failed")
        self.assertEqual(
            node_pulse._resolved_issue_message("memory", {"message": "kept", "since": "x"}),
            "kept")


class MainFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"NODE_STATE_DIR": self.tmp.name, "NTFY_DRY_RUN": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_main_sends_alert_recovery_and_digest_on_transitions(self):
        sent = []
        with patch.object(node_pulse, "collect", return_value=snapshot(
                memory={"total_bytes": 100, "available_bytes": 2, "available_pct": 2.0})), \
                patch.object(node_pulse.ntfy_notify, "send",
                             side_effect=lambda kind, *a, **k: sent.append(kind) or True):
            self.assertEqual(node_pulse.main([]), 0)
        self.assertEqual(sent, ["pulse_alert", "pulse_digest"])

        sent.clear()
        with patch.object(node_pulse, "collect", return_value=snapshot()), \
                patch.object(node_pulse.ntfy_notify, "send",
                             side_effect=lambda kind, *a, **k: sent.append(kind) or True):
            self.assertEqual(node_pulse.main([]), 0)
        self.assertEqual(sent, ["pulse_recovered"])

    def test_no_notify_never_touches_delivery(self):
        with patch.object(node_pulse, "collect", return_value=snapshot()), \
                patch.object(node_pulse.ntfy_notify, "send") as send:
            self.assertEqual(node_pulse.main(["--no-notify"]), 0)
        send.assert_not_called()

    def test_digest_fires_once_per_day(self):
        sent = []
        with patch.object(node_pulse, "collect", return_value=snapshot()), \
                patch.object(node_pulse.ntfy_notify, "send",
                             side_effect=lambda kind, *a, **k: sent.append(kind) or True):
            node_pulse.main([])
            node_pulse.main([])
        self.assertEqual(sent.count("pulse_digest"), 1)

    def test_dry_run_default_without_topic(self):
        # With no topic configured the shared delivery path prints instead of sending.
        with patch.object(node_pulse, "collect", return_value=snapshot()), \
                patch.object(node_pulse.ntfy_notify, "_post") as post, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(node_pulse.main([]), 0)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
