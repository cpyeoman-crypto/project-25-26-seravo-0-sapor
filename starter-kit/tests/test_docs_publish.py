import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import docs_publish as dp
import project_monitor


class DocumentationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.private, self.public, self.stage = (self.root / n for n in ("private", "public", "stage"))
        for path in (self.private, self.public, self.stage):
            path.mkdir(mode=0o700)
        self.source = self.private / "fleet.md"
        self.put(self.source, "# Fleet\nSynthetic-Hub\n192.168.44.8\n")
        self.map = self.root / "map.json"
        self.put(self.map, json.dumps({"Synthetic-Hub": "x-hub"}))
        self.config_path = self.root / "config.json"
        self.config = {
            "private_root": str(self.private), "public_root": str(self.public),
            "stage": str(self.stage), "redaction_map": str(self.map),
            "documents": {"fleet.md": "README.md"},
        }
        self.save()

    def put(self, path, text):
        path.write_text(text, encoding="utf-8")
        path.chmod(0o600)

    def save(self):
        self.put(self.config_path, json.dumps(self.config))

    def load(self):
        return dp.load(self.config_path)

    def publish(self):
        config = self.load()
        dp.stage(config)
        dp.apply(config, reviewed=True)

    def test_render_masks_and_preserves_loopback_examples(self):
        text = ("Synthetic-Hub 192.168.44.8 aa:bb:cc:dd:ee:ff fd00:1234::1 "
                "person@example.invalid https://ntfy.sh/private-topic "
                "node.tail-test.ts.net tskey-" + "a" * 24 +
                "\npassword: synthetic-password\n127.0.0.1 ::1 192.0.2.10 2001:db8::1\n")
        rendered = dp.render(text, {"Synthetic-Hub": "x-hub"})
        for value in ("Synthetic-Hub", "192.168.44.8", "aa:bb:cc:dd:ee:ff",
                      "fd00:1234::1", "private-topic", "synthetic-password", "person@"):
            self.assertNotIn(value, rendered)
        for value in ("127.0.0.1", "::1", "192.0.2.10", "2001:db8::1"):
            self.assertIn(value, rendered)
        self.assertEqual(dp.scan(rendered, {"Synthetic-Hub": "x-hub"}), [])
        self.assertNotIn("10.8.9.1", dp.render("Address: 10.8.9.1.", {}))
        self.assertIn("0.0.0.0", dp.render("Bind: 0.0.0.0", {}))

    def test_markers_and_exclusion(self):
        result = dp.render("a<!-- private:start -->secret\n<!-- private:end -->b"
                           "<!-- public-only: role description -->", {})
        self.assertEqual(result, "abrole description")
        self.assertIsNone(dp.render("---\npublish: false\n---\nprivate", {}))
        for text in ("<!-- private:end -->", "<!-- private:start -->",
                     "<!-- private:start --><!-- private:start --><!-- private:end -->",
                     "<!-- private:typo -->",
                     "<!-- private:start --><!-- public-only: x --><!-- private:end -->"):
            with self.subTest(text=text), self.assertRaises(dp.Refusal):
                dp.render(text, {})

    def test_leak_scan_line_numbers_and_no_secret_echo(self):
        secret = "synthetic-private-value"
        self.assertEqual(dp.scan("safe\n" + secret + "\n10.7.8.9", {secret: "x"}), [2, 3])
        self.put(self.source, "-----BEGIN PRIVATE KEY-----\n" + secret)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(dp.main(["stage", "--config", str(self.config_path)]), 1)
        self.assertNotIn(secret, stderr.getvalue())
        self.assertNotIn(str(self.private), stderr.getvalue())

    def test_staging_apply_review_and_manifest(self):
        config = self.load()
        self.assertEqual(dp.stage(config), 1)
        self.assertFalse((self.public / "README.md").exists())
        self.assertNotIn("Synthetic-Hub", (self.stage / "review.diff").read_text())
        with self.assertRaises(dp.Refusal):
            dp.apply(config)
        dp.apply(config, True)
        self.assertIn("x-hub", (self.public / "README.md").read_text())
        self.assertEqual(dp.assess(self.config_path)["health"], "healthy")
        for name in ("manifest.json", "vetted.json", "review.diff"):
            self.assertEqual((self.stage / name).stat().st_mode & 0o777, 0o600)

    def test_freshness_coverage_and_missing_evidence(self):
        self.assertEqual(dp.assess(self.config_path)["health"], "attention")
        self.publish()
        record = json.loads((self.stage / "vetted.json").read_text())
        self.assertEqual(dp.assess(self.config_path, record["vetted_at"] + 86401)["health"], "attention")
        self.put(self.public / "unvetted.md", "# Added")
        self.assertEqual(dp.assess(self.config_path)["health"], "attention")
        (self.public / "unvetted.md").unlink()
        self.put(self.source, "# Changed privately")
        self.assertEqual(dp.assess(self.config_path)["health"], "attention")

    def test_vetted_evidence_for_another_checkout_is_not_healthy(self):
        self.publish()
        self.assertEqual(dp.assess(self.config_path, public_root=self.public)["health"], "healthy")
        other = self.root / "other-public"
        other.mkdir()
        self.assertEqual(dp.assess(self.config_path, public_root=other)["health"], "attention")

    def test_approval_never_bypasses_map_change_or_permission_rescan(self):
        self.publish()
        self.put(self.map, json.dumps({"Synthetic-Hub": "x-hub", "Fleet": "x-fleet"}))
        self.assertEqual(dp.assess(self.config_path)["health"], "attention")
        self.put(self.map, json.dumps({"Synthetic-Hub": "x-hub"}))
        self.map.chmod(0o644)
        self.assertEqual(dp.assess(self.config_path)["health"], "attention")

    def test_private_key_blocks_are_refused_case_insensitively(self):
        for key_type in ("PRIVATE KEY", "OPENSSH PRIVATE KEY", "RSA PRIVATE KEY"):
            with self.subTest(key_type=key_type), self.assertRaises(dp.Refusal):
                dp.render(("-----BEGIN " + key_type + "-----\nprivate body").lower(), {})

    def test_modified_stage_or_source_or_public_refused_before_apply(self):
        for target in ("stage", "source", "public"):
            with self.subTest(target=target):
                if (self.stage / "rendered").exists():
                    (self.stage / "rendered" / "README.md").unlink()
                    (self.stage / "rendered").rmdir()
                config = self.load()
                dp.stage(config)
                path = {"stage": self.stage / "rendered/README.md",
                        "source": self.source, "public": self.public / "README.md"}[target]
                self.put(path, "# Modified")
                with self.assertRaises(dp.Refusal):
                    dp.apply(config, True)

    def test_permissions_symlinks_and_layout(self):
        for path in (self.map, self.config_path, self.source):
            path.chmod(0o644)
            self.assertEqual(dp.main(["stage", "--config", str(self.config_path)]), 1)
            path.chmod(0o600)
        self.map.unlink()
        self.map.symlink_to(self.source)
        with self.assertRaises(dp.Refusal):
            self.load()

    def test_no_path_traversal_duplicate_targets_or_private_public_overlap(self):
        for documents in ({"fleet.md": "../escape.md"}, {"../fleet.md": "README.md"},
                          {"fleet.md": "a.md", "other.md": "a.md"}):
            self.config["documents"] = documents
            self.save()
            with self.assertRaises(dp.Refusal):
                self.load()
        self.config["documents"] = {"fleet.md": "README.md"}
        self.config["stage"] = str(self.private)
        self.save()
        with self.assertRaises(dp.Refusal):
            self.load()

    def test_private_index_remains_local_and_knowledge_only(self):
        self.publish()
        self.assertEqual(dp.index(self.load()), 2)
        path = self.stage / "knowledge-index.json"
        data = json.loads(path.read_text())
        self.assertEqual({r["tier"] for r in data["documents"]}, {"private", "public"})
        self.assertTrue(all(r["knowledge_only"] for r in data["documents"]))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.public / "knowledge-index.json").exists())

    def test_check_report_integration_and_no_config_never_green(self):
        self.publish()
        base = {"health": "healthy", "expires_at": time.time() + 300, "findings": []}
        config = {"documentation_publish_config": str(self.config_path)}
        with patch.object(project_monitor, "read_json", side_effect=[config, {}]), \
                patch.object(project_monitor, "snapshot", return_value=("a" * 64, {})), \
                patch.object(project_monitor, "evaluate", return_value=base.copy()):
            result = project_monitor.run(self.public, "unused", "unused")
        self.assertEqual(result["documentation_publishing"]["health"], "healthy")
        self.put(self.source, "# Updated")
        with patch.object(project_monitor, "read_json", side_effect=[config, {}]), \
                patch.object(project_monitor, "snapshot", return_value=("a" * 64, {})), \
                patch.object(project_monitor, "evaluate", return_value=base.copy()):
            self.assertEqual(project_monitor.run(self.public, "unused", "unused")["health"], "attention")

    def test_skipped_documents_never_exported_and_stage_exclusive(self):
        self.put(self.source, "---\npublish: false\n---\nSensitive unpublished")
        config = self.load()
        self.assertEqual(dp.stage(config), 0)
        self.assertFalse((self.stage / "rendered/README.md").exists())
        with self.assertRaises(FileExistsError):
            dp.stage(config)

    def test_bad_replacement_and_partial_marker_rejected(self):
        self.put(self.map, json.dumps({"Synthetic-Hub": "Synthetic-Hub public"}))
        with self.assertRaises(dp.Refusal):
            self.load()
        with self.assertRaises(dp.Refusal):
            dp.render("<!-- public-only: unclosed", {})

    def test_prior_approval_rescanned_and_leaking_public_output_corrected(self):
        self.publish()
        self.put(self.public / "README.md", "# Fleet\nSynthetic-Hub 10.6.7.8\n")
        config = self.load()
        findings = dp.audit(config)
        self.assertEqual(findings, [{"file": 1, "lines": [2]}])
        self.assertEqual(dp.assess(self.config_path)["health"], "attention")
        # Use a fresh review directory, never silently replace an earlier review.
        (self.stage / "rendered/README.md").unlink()
        (self.stage / "rendered").rmdir()
        dp.stage(config)
        dp.apply(config, True)
        self.assertFalse(dp.audit(config))
        self.assertEqual(dp.assess(self.config_path)["health"], "healthy")

    def test_unmapped_public_leak_blocks_apply_and_audit_never_echoes_values(self):
        self.put(self.public / "extra.md", "Synthetic-Hub 10.6.7.8")
        config = self.load()
        dp.stage(config)
        with self.assertRaises(dp.Refusal):
            dp.apply(config, True)
        self.assertFalse((self.public / "README.md").exists())
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(dp.main(["audit", "--config", str(self.config_path)]), 1)
        self.assertNotIn("Synthetic-Hub", stdout.getvalue())
        self.assertNotIn("10.6.7.8", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
