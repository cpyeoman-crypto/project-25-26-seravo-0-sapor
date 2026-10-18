import json
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ["NTFY_DRY_RUN"] = "1"

import daily_status  # noqa: E402
import fleet_poll  # noqa: E402
import ntfy_notify as ntfy  # noqa: E402
import resolver  # noqa: E402
import wol_healer  # noqa: E402

TEST_DIR = Path(tempfile.gettempdir())
HUGE_INT = 10 ** 400
NESTED_JSON = '{"nested":' + "[" * 10000 + "0" + "]" * 10000 + "}"
OVERSIZED_JSON = '{"padding":"' + " " * (1024 * 1024) + '"}'
LAN, FAILED, SECOND_LAN, LAST_KNOWN, MESH = (
    f"127.0.0.{number}" for number in (10, 11, 12, 20, 30)
)
MAC, SECOND_MAC = (
    ":".join(f"{byte:02x}" for byte in bytes((2, 0, 0, 0, 0, number)))
    for number in (1, 2)
)
NEIGH = f"""\
{LAN} dev eth0 lladdr {MAC.upper()} REACHABLE
{FAILED} dev eth0  FAILED
{SECOND_LAN} dev eth0 lladdr {SECOND_MAC.replace(':', '-')} STALE
"""


class ResolverTests(unittest.TestCase):
    def test_normalize_mac(self):
        self.assertEqual(resolver.normalize_mac(MAC.upper().replace(":", "-")), MAC)
        self.assertEqual(resolver.normalize_mac(MAC.replace(":", "")), MAC)
        self.assertIsNone(resolver.normalize_mac("nope"))

    def test_parse_neighbor_table_skips_failed(self):
        table = resolver.parse_neighbor_table(NEIGH)
        self.assertEqual(table[MAC], [LAN])
        self.assertEqual(table[SECOND_MAC], [SECOND_LAN])
        self.assertNotIn(FAILED, sum(table.values(), []))

    def test_mac_beats_mesh_beats_last_known(self):
        node = {"macs": [MAC], "mesh_name": "box", "last_known_address": LAST_KNOWN}
        neighbors = resolver.parse_neighbor_table(NEIGH)
        always = lambda addr: True
        self.assertEqual(resolver.resolve(node, neighbors, {"box": MESH}, always).channel, "lan")
        self.assertEqual(resolver.resolve(node, {}, {"box": MESH}, always).channel, "mesh")
        self.assertEqual(resolver.resolve(node, {}, {}, always).channel, "last-known")
        self.assertIsNone(resolver.resolve(node, {}, {}, lambda addr: False))


class PollTests(unittest.TestCase):
    manifest = {"nodes": [{"name": "a", "role": "r", "macs": [MAC]}]}

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
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as tmp:
            Path(tmp, "a.json").write_text(json.dumps({"epoch": 0}))
            manifest = {"heartbeat_dir": tmp, "heartbeat_max_age_min": 15, "nodes": self.manifest["nodes"]}
            neighbors = resolver.parse_neighbor_table(NEIGH)
            _, alerts = fleet_poll.poll_once(manifest, {}, neighbors, {}, lambda a, p: True, 3600)
            self.assertEqual([a[0] for a in alerts], ["stale"])

    def test_missing_and_malformed_heartbeats_mark_reachable_node_stale(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            path = Path(directory) / "a.json"
            manifest = {"heartbeat_dir": directory, "heartbeat_max_age_min": 15,
                        "nodes": self.manifest["nodes"]}
            for raw in (None, "not-json", "[]", "null", "false", "123", '"text"',
                        "{}", '{"epoch": true}', '{"epoch": "1000"}',
                        '{"epoch": 3601}'):
                with self.subTest(raw=raw):
                    if raw is not None:
                        path.write_text(raw, encoding="utf-8")
                    state, alerts = fleet_poll.poll_once(
                        manifest, {}, resolver.parse_neighbor_table(NEIGH), {},
                        lambda address, port: True, 3600
                    )
                    self.assertTrue(state["a"]["up"])
                    self.assertTrue(state["a"]["stale"])
                    self.assertEqual(state["a"]["checked_at"], 3600)
                    self.assertEqual([alert[0] for alert in alerts], ["stale"])

    def test_fresh_heartbeat_does_not_mark_reachable_node_stale(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            Path(directory, "a.json").write_text(json.dumps({"epoch": 3590}), encoding="utf-8")
            manifest = {"heartbeat_dir": directory, "nodes": self.manifest["nodes"]}
            state, alerts = fleet_poll.poll_once(
                manifest, {}, resolver.parse_neighbor_table(NEIGH), {},
                lambda address, port: True, 3600
            )
            self.assertFalse(state["a"]["stale"])
            self.assertEqual(alerts, [])

    def test_giant_nested_and_oversized_heartbeat_data_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            path = Path(directory) / "a.json"
            manifest = {"heartbeat_dir": directory, "nodes": self.manifest["nodes"]}
            for kind, raw in (
                ("giant epoch", json.dumps({"epoch": HUGE_INT})),
                ("deeply nested", NESTED_JSON),
                ("oversized", OVERSIZED_JSON),
            ):
                with self.subTest(kind=kind):
                    path.write_text(raw, encoding="utf-8")
                    state, alerts = fleet_poll.poll_once(
                        manifest, {}, resolver.parse_neighbor_table(NEIGH), {},
                        lambda address, port: True, 3600
                    )
                    self.assertTrue(state["a"]["stale"])
                    self.assertEqual([alert[0] for alert in alerts], ["stale"])


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
        with patch.object(ntfy, "compose", return_value="safe test message"), \
                patch.object(ntfy, "site_name", return_value="test-site"), \
                patch.object(ntfy.urllib.request, "urlopen") as network, \
                redirect_stdout(io.StringIO()):
            self.assertTrue(ntfy.send("test", "hello"))
        network.assert_not_called()


class OtherTests(unittest.TestCase):
    def test_magic_packet(self):
        packet = wol_healer.magic_packet(MAC)
        self.assertEqual(len(packet), 102)
        self.assertEqual(packet[:6], b"\xff" * 6)

    def test_wake_only_wake_required(self):
        manifest = {"nodes": [
            {"name": "x", "macs": [MAC], "wake_required": True},
            {"name": "y", "macs": [SECOND_MAC], "wake_required": False},
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
