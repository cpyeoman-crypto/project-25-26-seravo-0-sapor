import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from test_kit import LAN, LAST_KNOWN, MAC, MESH, TEST_DIR, fleet_poll, ntfy, resolver


class ResolverValidationTests(unittest.TestCase):
    def test_resolution_probes_lan_then_mesh_then_last_known(self):
        node = {"macs": [MAC], "mesh_name": "box", "last_known_address": LAST_KNOWN}
        for reachable, expected, channel in (
            (LAN, [LAN], "lan"),
            (MESH, [LAN, MESH], "mesh"),
            (LAST_KNOWN, [LAN, MESH, LAST_KNOWN], "last-known"),
            (None, [LAN, MESH, LAST_KNOWN], None),
        ):
            with self.subTest(channel=channel):
                calls = []

                def probe(address):
                    calls.append(address)
                    return address == reachable

                result = resolver.resolve(node, {MAC: [LAN]}, {"box": MESH}, probe)
                self.assertEqual(calls, expected)
                self.assertEqual(result.channel if result else None, channel)

    def test_address_placeholders_rejected_before_tcp_connection(self):
        for address in ("x.x.x.x", "xx.xx.xx.xx", "x-mesh-host", "CHANGE-ME"):
            with self.subTest(address=address), \
                    patch.object(fleet_poll.socket, "create_connection") as connect:
                with self.assertRaises(ValueError):
                    fleet_poll.tcp_probe(address, 22)
                connect.assert_not_called()

    def test_discovered_placeholders_never_reach_probe(self):
        cases = (
            ({"macs": [MAC]}, {MAC: ["x.x.x.x"]}, {}),
            ({"mesh_name": "box"}, {}, {"box": "x-mesh-host"}),
            ({"last_known_address": "x.x.x.x"}, {}, {}),
        )
        for node, neighbors, peers in cases:
            with self.subTest(node=node):
                probe = Mock()
                with self.assertRaises(ValueError):
                    resolver.resolve(node, neighbors, peers, probe)
                probe.assert_not_called()

    def test_manifest_placeholders_fail_before_discovery_or_network(self):
        variants = (
            {"macs": ["xx:xx:xx:xx:xx:xx"]},
            {"mesh_name": "x-mesh-host"},
            {"last_known_address": "x.x.x.x"},
            {"wol_broadcast": "x.x.x.x"},
        )
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            manifest_path = Path(directory) / "manifest.json"
            for fields in variants:
                with self.subTest(fields=fields):
                    node = {"name": "a", "macs": [MAC]}
                    manifest = {"nodes": [node]}
                    if "wol_broadcast" in fields:
                        manifest.update(fields)
                    else:
                        node.update(fields)
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                    with patch.object(resolver, "read_neighbors") as neighbors, \
                            patch.object(resolver, "read_mesh_peers") as peers, \
                            patch.object(resolver.subprocess, "run") as subprocess_run, \
                            patch.object(fleet_poll.socket, "create_connection") as connect, \
                            redirect_stdout(io.StringIO()):
                        try:
                            result = fleet_poll.main([
                                "--manifest", str(manifest_path),
                                "--state", str(Path(directory) / "state.json"),
                            ])
                        except ValueError:
                            pass
                        else:
                            self.assertNotEqual(result, 0)
                    for operation in (neighbors, peers, subprocess_run, connect):
                        operation.assert_not_called()

    def test_loopback_manifest_remains_operational(self):
        manifest = {"nodes": [{"name": "a", "macs": [MAC],
                               "last_known_address": LAST_KNOWN, "probe_port": 22}],
                    "wol_broadcast": LAN}
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(resolver.load_manifest(path), manifest)


class NtfyValidationTests(unittest.TestCase):
    def settings(self, endpoint, token):
        values = {"NTFY_TOKEN": token, "NTFY_SERVER": endpoint}
        return lambda name, default=None: values.get(name, default)

    def test_endpoint_topic_token_placeholders_never_open_network(self):
        for endpoint, topic, token in (
            ("https://x.x.x.x", "test-topic", None),
            ("https://x-ntfy-host", "test-topic", None),
            ("http://127.0.0.1", "x-topic", None),
            ("http://127.0.0.1", "test-topic", "x-token"),
            ("http://127.0.0.1", "xx", None),
        ):
            with self.subTest(endpoint=endpoint, topic=topic, token_present=token is not None), \
                    patch.object(ntfy, "setting", side_effect=self.settings(endpoint, token)), \
                    patch.object(ntfy.urllib.request, "urlopen") as network:
                with self.assertRaises(ValueError):
                    ntfy._post({"topic": topic, "message": "test"})
                network.assert_not_called()

    def test_post_uses_bearer_authorization_and_json(self):
        token = "test-only-noncredential"
        payload = {"topic": "test-topic", "message": "test"}
        with patch.object(ntfy, "setting",
                          side_effect=self.settings("http://127.0.0.1", token)), \
                patch.object(ntfy.urllib.request, "urlopen") as network:
            network.return_value.__enter__.return_value.status = 200
            ntfy._post(payload, timeout=3)
        request = network.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1/")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + token)
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), payload)
        self.assertEqual(network.call_args.kwargs["timeout"], 3)

    def test_post_without_token_has_no_authorization_header(self):
        with patch.object(ntfy, "setting",
                          side_effect=self.settings("http://127.0.0.1", None)), \
                patch.object(ntfy.urllib.request, "urlopen") as network:
            network.return_value.__enter__.return_value.status = 200
            ntfy._post({"topic": "test-topic", "message": "test"})
        self.assertIsNone(network.call_args.args[0].get_header("Authorization"))

    def test_send_rejects_placeholders_before_network_spool_or_retry(self):
        for endpoint, topic, token in (
            ("https://x.x.x.x", "test-topic", None),
            ("http://127.0.0.1", "x-topic", None),
            ("http://127.0.0.1", "test-topic", "x-token"),
        ):
            with self.subTest(endpoint=endpoint, topic=topic, token_present=token is not None), \
                    patch.dict(os.environ, {}, clear=True), \
                    patch.object(ntfy, "setting", side_effect=self.settings(endpoint, token)), \
                    patch.object(ntfy, "compose", return_value="safe test message"), \
                    patch.object(ntfy, "site_name", return_value="test-site"), \
                    patch.object(ntfy, "flush_spool") as flush, \
                    patch.object(ntfy, "_spool") as spool, \
                    patch.object(ntfy.urllib.request, "urlopen") as network, \
                    redirect_stdout(io.StringIO()) as output:
                sleep = Mock()
                self.assertFalse(ntfy.send("test", "test", topic_name=topic, sleep=sleep))
                for operation in (network, flush, spool, sleep):
                    operation.assert_not_called()
                self.assertIn("nothing sent", output.getvalue())
                self.assertNotIn(endpoint, output.getvalue())

    def test_invalid_queued_notifications_never_post_and_remain_in_spool(self):
        private_marker = "untrusted-queued-payload-marker"
        lines = (
            json.dumps({"topic": "x-topic", "message": private_marker}),
            private_marker + " malformed-json",
            json.dumps([private_marker]),
        )
        with tempfile.TemporaryDirectory(dir=TEST_DIR) as directory:
            path = Path(directory) / "spool.jsonl"
            for line in lines:
                with self.subTest(kind="json" if line.startswith(("{", "[")) else "corrupt"):
                    path.write_text(line + "\n", encoding="utf-8")
                    with patch.object(ntfy, "_spool_path", return_value=path), \
                            patch.object(ntfy, "setting",
                                         side_effect=self.settings("http://127.0.0.1", None)), \
                            patch.object(ntfy.urllib.request, "urlopen") as network, \
                            redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(ntfy.flush_spool(), 0)
                    network.assert_not_called()
                    self.assertEqual(path.read_text(encoding="utf-8"), line + "\n")
                    self.assertIn("Invalid queued notification retained", output.getvalue())
                    self.assertNotIn(private_marker, output.getvalue())
                    self.assertNotIn("x-topic", output.getvalue())


if __name__ == "__main__":
    unittest.main()
