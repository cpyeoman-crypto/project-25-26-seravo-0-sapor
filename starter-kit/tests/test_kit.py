import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ["NTFY_DRY_RUN"] = "1"

import daily_status  # noqa: E402
import fleet_poll  # noqa: E402
import ntfy_notify as ntfy  # noqa: E402
import resolver  # noqa: E402
import wol_healer  # noqa: E402

NEIGH = """\
192.0.2.10 dev eth0 lladdr AA:BB:CC:DD:EE:01 REACHABLE
192.0.2.11 dev eth0  FAILED
192.0.2.12 dev eth0 lladdr aa-bb-cc-dd-ee-02 STALE
"""


class ResolverTests(unittest.TestCase):
    def test_normalize_mac(self):
        self.assertEqual(resolver.normalize_mac("AA-BB-CC-DD-EE-01"), "aa:bb:cc:dd:ee:01")
        self.assertEqual(resolver.normalize_mac("aabbccddee01"), "aa:bb:cc:dd:ee:01")
        self.assertIsNone(resolver.normalize_mac("nope"))

    def test_parse_neighbor_table_skips_failed(self):
        table = resolver.parse_neighbor_table(NEIGH)
        self.assertEqual(table["aa:bb:cc:dd:ee:01"], ["192.0.2.10"])
        self.assertEqual(table["aa:bb:cc:dd:ee:02"], ["192.0.2.12"])
        self.assertNotIn("192.0.2.11", sum(table.values(), []))

    def test_mac_beats_mesh_beats_last_known(self):
        node = {"macs": ["aa:bb:cc:dd:ee:01"], "mesh_name": "box", "last_known_address": "198.51.100.1"}
        neighbors = resolver.parse_neighbor_table(NEIGH)
        always = lambda addr: True
        self.assertEqual(resolver.resolve(node, neighbors, {"box": "203.0.113.5"}, always).channel, "lan")
        self.assertEqual(resolver.resolve(node, {}, {"box": "203.0.113.5"}, always).channel, "mesh")
        self.assertEqual(resolver.resolve(node, {}, {}, always).channel, "last-known")
        self.assertIsNone(resolver.resolve(node, {}, {}, lambda addr: False))


class PollTests(unittest.TestCase):
    manifest = {"nodes": [{"name": "a", "role": "r", "macs": ["aa:bb:cc:dd:ee:01"]}]}

    def run_poll(self, previous, up, now):
        neighbors = resolver.parse_neighbor_table(NEIGH)
        return fleet_poll.poll_once(self.manifest, previous, neighbors, {}, lambda a, p: up, now)

    def test_first_run_seeds_without_alerting(self):
        _, alerts = self.run_poll({}, False, 1000)
        self.assertEqual(alerts, [])

    def test_alerts_on_change_only(self):
        state, alerts = self.run_poll({}, True, 1000)
        self.assertEqual(alerts, [])
        state, alerts = self.run_poll(state, False, 1100)
        self.assertEqual([a[0] for a in alerts], ["node_down"])
        state, alerts = self.run_poll(state, False, 1200)
        self.assertEqual(alerts, [])  # still down, no repeat
        state, alerts = self.run_poll(state, True, 1300)
        self.assertEqual([a[0] for a in alerts], ["node_up"])

    def test_seeded_down_node_does_not_remind_at_once(self):
        state, _ = self.run_poll({}, False, 1000)
        _, alerts = self.run_poll(state, False, 1120)
        self.assertEqual(alerts, [])

    def test_daily_reminder_when_still_down(self):
        state, _ = self.run_poll({}, True, 0)
        state, _ = self.run_poll(state, False, 100)
        _, alerts = self.run_poll(state, False, 100 + 25 * 3600)
        self.assertEqual([a[0] for a in alerts], ["node_down"])

    def test_stale_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.json").write_text(json.dumps({"epoch": 0}))
            manifest = {"heartbeat_dir": tmp, "heartbeat_max_age_min": 15, "nodes": self.manifest["nodes"]}
            neighbors = resolver.parse_neighbor_table(NEIGH)
            _, alerts = fleet_poll.poll_once(manifest, {}, neighbors, {}, lambda a, p: True, 3600)
            self.assertEqual([a[0] for a in alerts], ["stale"])


class NtfyTests(unittest.TestCase):
    def test_truncate(self):
        text = "line\n" * 2000
        out = ntfy.truncate(text)
        self.assertLessEqual(len(out.encode()), ntfy.MAX_MESSAGE_BYTES + 40)
        self.assertTrue(out.endswith("*…truncated*"))

    def test_payload_shape(self):
        payload = ntfy.build_payload("node_down", "x", headline="NODE OFFLINE · a", topic_name="t")
        self.assertEqual(payload["priority"], 4)
        self.assertTrue(payload["markdown"])
        self.assertEqual(payload["topic"], "t")

    def test_dry_run_sends_nothing(self):
        self.assertTrue(ntfy.send("test", "hello"))


class OtherTests(unittest.TestCase):
    def test_magic_packet(self):
        packet = wol_healer.magic_packet("aa:bb:cc:dd:ee:01")
        self.assertEqual(len(packet), 102)
        self.assertEqual(packet[:6], b"\xff" * 6)

    def test_wake_only_wake_required(self):
        manifest = {"nodes": [
            {"name": "x", "macs": ["aa:bb:cc:dd:ee:01"], "wake_required": True},
            {"name": "y", "macs": ["aa:bb:cc:dd:ee:02"], "wake_required": False},
        ]}
        state = {"x": {"up": False}, "y": {"up": False}}
        self.assertEqual([n["name"] for n in wol_healer.candidates(manifest, state)], ["x"])

    def test_daily_report(self):
        metrics = daily_status.host_metrics()
        headline, body, attention = daily_status.build_report(
            metrics, {"a": {"up": False, "role": "r"}, "b": {"up": True, "role": "r", "channel": "lan"}})
        self.assertIn("ATTENTION", headline)
        self.assertTrue(attention)
        self.assertIn("Down: a", body)


if __name__ == "__main__":
    unittest.main()
