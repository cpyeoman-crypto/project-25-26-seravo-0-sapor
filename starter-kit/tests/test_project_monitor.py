import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_kit import HUGE_INT, NESTED_JSON, OVERSIZED_JSON, TEST_DIR
import project_monitor


NOW = 100000
REVISION = "a" * 64
PRIVATE = "untrusted-sensitive-evidence-marker"


class ProjectMonitorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=TEST_DIR)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = {
            "max_age_seconds": 3600,
            "required_checks": ["tests", "lint"],
            "connectors": {"rave": {"implemented": False}, "ntfy": {"implemented": True}},
        }
        self.docs = {"README.md": "b" * 64}
        self.evidence = {
            "checks": {
                name: {"status": "passed", "checked_at": NOW - 60, "revision": REVISION}
                for name in ("tests", "lint")
            },
            "docs": self.docs.copy(),
            "connectors": {
                name: {
                    "status": "verified",
                    "revision": REVISION,
                    "checked_at": NOW - 60,
                    "prerequisites": dict.fromkeys(project_monitor.GATES, True),
                }
                for name in ("rave", "ntfy")
            },
        }

    def write(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def evaluate(self):
        return project_monitor.evaluate(self.config, self.evidence, REVISION, self.docs, NOW)

    def test_passed_checks_and_verified_implemented_connector(self):
        result = self.evaluate()
        self.assertEqual([row["status"] for row in result["checks"]], ["passed", "passed"])
        self.assertEqual(result["last_successful_check"], NOW - 60)
        self.assertEqual(result["documentation_review_count"], 0)
        self.assertEqual(result["connectors"][0]["status"], "verified")

    def test_rave_never_verified_even_if_policy_claims_implementation(self):
        for implemented in (False, True):
            for lifecycle in ("implemented", "verified"):
                with self.subTest(implemented=implemented, lifecycle=lifecycle):
                    self.config["connectors"]["rave"]["implemented"] = implemented
                    self.evidence["connectors"]["rave"]["status"] = lifecycle
                    result = self.evaluate()
                    self.assertEqual(result["health"], "attention")
                    self.assertEqual(result["connectors"][1]["status"], "blocked")
                    self.assertTrue(
                        {"interface", "verification"} <= set(result["connectors"][1]["missing"])
                    )

    def test_unimplemented_policy_blocks_claimed_implemented_and_verified_status(self):
        self.config["connectors"]["ntfy"]["implemented"] = False
        for lifecycle in ("implemented", "verified"):
            with self.subTest(lifecycle=lifecycle):
                self.evidence["connectors"]["ntfy"]["status"] = lifecycle
                row = self.evaluate()["connectors"][0]
                self.assertEqual(row["status"], "blocked")
                self.assertEqual(set(row["missing"]), {"interface", "verification"})

    def test_connector_requires_every_gate(self):
        for gate in project_monitor.GATES:
            with self.subTest(gate=gate):
                self.evidence["connectors"]["ntfy"]["prerequisites"] = dict.fromkeys(
                    project_monitor.GATES, True
                )
                self.evidence["connectors"]["ntfy"]["prerequisites"][gate] = False
                row = self.evaluate()["connectors"][0]
                self.assertEqual(row["status"], "blocked")
                self.assertEqual(set(row["missing"]), {gate, "verification"})

    def test_verified_connector_requires_fresh_revision_bound_evidence(self):
        for update in (
            {"checked_at": NOW - 3601}, {"checked_at": NOW + 1},
            {"checked_at": True}, {"revision": "old"}, {"checked_at": None},
        ):
            with self.subTest(update=update):
                record = copy.deepcopy(self.evidence["connectors"]["ntfy"])
                self.evidence["connectors"]["ntfy"].update(update)
                row = self.evaluate()["connectors"][0]
                self.assertEqual(row["status"], "blocked")
                self.assertIn("verification", row["missing"])
                self.evidence["connectors"]["ntfy"] = record

    def test_check_missing_stale_future_malformed_and_outdated(self):
        cases = [
            (None, "missing"),
            ("invalid record", "invalid"),
            ({}, "invalid"),
            ({"checked_at": NOW - 3601}, "stale"),
            ({"checked_at": NOW + 1}, "invalid"),
            ({"checked_at": True}, "invalid"),
            ({"checked_at": float("nan")}, "invalid"),
            ({"revision": "old"}, "outdated"),
            ({"status": "pending"}, "pending"),
            ({"status": "failed"}, "failed"),
        ]
        original = self.evidence["checks"]["tests"]
        for update, expected in cases:
            with self.subTest(expected=expected, update=update):
                if update is None:
                    self.evidence["checks"].pop("tests", None)
                elif isinstance(update, dict) and update:
                    self.evidence["checks"]["tests"] = dict(original, **update)
                else:
                    self.evidence["checks"]["tests"] = update
                self.assertEqual(self.evaluate()["checks"][0]["status"], expected)

    def test_freshness_boundary_is_inclusive(self):
        for stamp, expected in ((NOW, True), (NOW - 3600, True),
                                (NOW - 3601, False), (NOW + 1, False)):
            with self.subTest(stamp=stamp):
                self.assertEqual(project_monitor.fresh(stamp, NOW, 3600), expected)

    def test_giant_epoch_and_max_age_fail_closed_without_overflow(self):
        self.assertFalse(project_monitor.fresh(HUGE_INT, NOW, 3600))
        self.evidence["checks"]["tests"]["checked_at"] = HUGE_INT
        self.assertEqual(self.evaluate()["checks"][0]["status"], "invalid")
        self.config["max_age_seconds"] = HUGE_INT
        with self.assertRaises(ValueError):
            self.evaluate()

    def test_json_size_limit_counts_utf8_bytes_not_characters(self):
        raw = '{"padding":"' + "\u00e9" * (512 * 1024) + '"}'
        self.assertLess(len(raw), 1024 * 1024)
        self.assertGreater(len(raw.encode("utf-8")), 1024 * 1024)
        path = self.root / "multibyte.json"
        path.write_text(raw, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "evidence too large"):
            project_monitor.read_json(path)

    def test_run_and_summary_reject_deeply_nested_and_oversized_json(self):
        config = self.write("config.json", self.config)
        evidence = self.write("evidence.json", self.evidence)
        for kind, raw in (("deeply nested", NESTED_JSON), ("oversized", OVERSIZED_JSON)):
            with self.subTest(kind=kind):
                for target in ("config", "evidence"):
                    with self.subTest(target=target):
                        config.write_text(json.dumps(self.config), encoding="utf-8")
                        evidence.write_text(json.dumps(self.evidence), encoding="utf-8")
                        (config if target == "config" else evidence).write_text(raw, encoding="utf-8")
                        with patch.object(project_monitor, "snapshot") as snapshot:
                            status = project_monitor.run(self.root, config, evidence, now=NOW)
                        snapshot.assert_not_called()
                        self.assertEqual(status["health"], "invalid")
                path = self.root / "status.json"
                path.write_text(raw, encoding="utf-8")
                text, attention = project_monitor.summary(path, now=NOW)
                self.assertTrue(attention)
                self.assertEqual(text, "Project: monitoring data missing, stale or invalid")

    def test_summary_handles_giant_timestamps_without_overflow(self):
        status = self.evaluate()
        for field in ("checked_at", "last_successful_check", "expires_at"):
            with self.subTest(field=field):
                text, attention = project_monitor.summary(
                    self.write("status.json", dict(status, **{field: HUGE_INT})), now=NOW
                )
                self.assertTrue(attention)
                self.assertNotIn("Project: healthy", text)

    def test_configuration_requires_both_notification_and_rave_connectors(self):
        for missing in ("ntfy", "rave"):
            with self.subTest(missing=missing):
                config = copy.deepcopy(self.config)
                del config["connectors"][missing]
                with self.assertRaises(ValueError):
                    project_monitor.evaluate(config, self.evidence, REVISION, self.docs, NOW)

    def test_expiry_is_earliest_passed_check_or_verified_connector_deadline(self):
        for source in ("tests", "lint", "ntfy"):
            with self.subTest(source=source):
                evidence = copy.deepcopy(self.evidence)
                record = (evidence["connectors"]["ntfy"] if source == "ntfy"
                          else evidence["checks"][source])
                record["checked_at"] = NOW - 3590
                result = project_monitor.evaluate(
                    self.config, evidence, REVISION, self.docs, NOW
                )
                self.assertEqual(result["expires_at"], NOW + 10)

    def test_summary_marks_expired_evidence_before_hourly_status_ages_out(self):
        self.evidence["checks"]["tests"]["checked_at"] = NOW - 3590
        status = self.evaluate()
        self.assertEqual(status["expires_at"], NOW + 10)
        status["health"] = "healthy"
        for connector in status["connectors"]:
            connector.update(status="verified", missing=[])
        path = self.write("status.json", status)
        for stamp in (NOW, NOW + 10):
            with self.subTest(now=stamp):
                text, attention = project_monitor.summary(path, now=stamp)
                self.assertFalse(attention)
                self.assertIn("Project: healthy", text)
        text, attention = project_monitor.summary(path, now=NOW + 11)
        self.assertTrue(attention)
        self.assertIn("Project: attention", text)
        self.assertIn("Evidence freshness: expired or invalid", text)

    def test_last_successful_check_retains_stale_and_outdated_passed_epochs(self):
        for age, revision, expected, label in (
            (90000, REVISION, "stale", " (stale)"),
            (60, "older-revision", "outdated", ""),
        ):
            with self.subTest(expected=expected):
                for record in self.evidence["checks"].values():
                    record.update(status="passed", checked_at=NOW - age, revision=revision)
                status = self.evaluate()
                self.assertEqual(status["last_successful_check"], NOW - age)
                self.assertEqual([row["status"] for row in status["checks"]], [expected] * 2)
                text, attention = project_monitor.summary(
                    self.write("status.json", status), now=NOW
                )
                self.assertTrue(attention)
                self.assertIn(
                    f"Last successful check (epoch): {NOW - age}{label}", text
                )

    def test_missing_or_changed_document_review_counts_drift(self):
        for reviews in ({}, {"README.md": "old"}):
            with self.subTest(reviews=reviews):
                self.evidence["docs"] = reviews
                result = self.evaluate()
                self.assertEqual(result["documentation_review_count"], 1)
                self.assertEqual(result["documentation_review_paths"], ["README.md"])
                self.assertIn("documentation: 1 file(s) require review", result["findings"])

    def test_obsolete_documentation_approvals_count_without_echoing_untrusted_paths(self):
        self.evidence["docs"].update({
            f"{PRIVATE}/deleted.md": "obsolete-hash",
            f"{PRIVATE}/another.md": "obsolete-hash",
        })
        result = self.evaluate()
        self.assertEqual(result["documentation_review_count"], 2)
        self.assertEqual(result["obsolete_documentation_approvals"], 2)
        self.assertEqual(result["documentation_review_paths"], [])
        self.assertNotIn(PRIVATE, json.dumps(result))
        text, attention = project_monitor.summary(self.write("status.json", result), now=NOW)
        self.assertTrue(attention)
        self.assertIn("Documentation review needs: 2", text)
        self.assertNotIn(PRIVATE, text)

    def test_evaluate_does_not_copy_arbitrary_evidence_or_paths(self):
        self.config["required_checks"] = ["private_check_name"]
        self.config["connectors"]["private_connector_name"] = {"implemented": False}
        self.evidence["checks"]["private_check_name"] = {
            "status": PRIVATE, "output": PRIVATE, "command": PRIVATE,
        }
        self.evidence["connectors"]["private_connector_name"] = {"notes": PRIVATE}
        self.evidence["docs"][PRIVATE] = PRIVATE
        encoded = json.dumps(self.evaluate())
        for value in (PRIVATE, "private_check_name", "private_connector_name"):
            self.assertNotIn(value, encoded)

    def test_run_valid_evidence_uses_snapshot(self):
        config = self.write("config.json", self.config)
        evidence = self.write("evidence.json", self.evidence)
        with patch.object(project_monitor, "snapshot", return_value=(REVISION, self.docs)) as snapshot:
            result = project_monitor.run(self.root, config, evidence, now=NOW)
        snapshot.assert_called_once_with(self.root)
        self.assertEqual(result, self.evaluate())

    def prepare_snapshot_repository(self):
        subprocess.run(["git", "init", "--quiet", str(self.root)],
                       check=True, capture_output=True)
        (self.root / ".gitignore").write_text("state/\nconfig/\n", encoding="utf-8")
        (self.root / "README.md").write_text("Reviewed documentation\n", encoding="utf-8")
        (self.root / "monitor.py").write_text("VALUE = 1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "."],
                       check=True, capture_output=True)
        revision, docs = project_monitor.snapshot(self.root)
        for record in self.evidence["checks"].values():
            record["revision"] = revision
        for record in self.evidence["connectors"].values():
            record["revision"] = revision
        self.evidence["docs"] = docs.copy()
        return revision, docs

    def test_new_nonignored_code_invalidates_successful_check_revision(self):
        before, docs = self.prepare_snapshot_repository()
        (self.root / "new_module.py").write_text("VALUE = 2\n", encoding="utf-8")
        after, current_docs = project_monitor.snapshot(self.root)
        self.assertNotEqual(before, after)
        self.assertEqual(current_docs, docs)
        result = project_monitor.evaluate(
            self.config, self.evidence, after, current_docs, NOW
        )
        self.assertEqual([row["status"] for row in result["checks"]], ["outdated"] * 2)
        self.assertEqual(result["documentation_review_count"], 0)

    def test_new_nonignored_document_requires_review_and_invalidates_revision(self):
        before, _ = self.prepare_snapshot_repository()
        (self.root / "NEW.md").write_text("New documentation\n", encoding="utf-8")
        after, docs = project_monitor.snapshot(self.root)
        self.assertNotEqual(before, after)
        result = project_monitor.evaluate(self.config, self.evidence, after, docs, NOW)
        self.assertEqual(result["documentation_review_count"], 1)
        self.assertEqual(result["documentation_review_paths"], ["NEW.md"])
        self.assertEqual([row["status"] for row in result["checks"]], ["outdated"] * 2)

    def test_tracked_working_tree_document_edit_invalidates_review(self):
        before, _ = self.prepare_snapshot_repository()
        (self.root / "README.md").write_text("Changed documentation\n", encoding="utf-8")
        after, docs = project_monitor.snapshot(self.root)
        self.assertNotEqual(before, after)
        result = project_monitor.evaluate(self.config, self.evidence, after, docs, NOW)
        self.assertEqual(result["documentation_review_paths"], ["README.md"])
        self.assertEqual(result["documentation_review_count"], 1)

    def test_ignored_runtime_state_and_configuration_do_not_change_snapshot(self):
        before = self.prepare_snapshot_repository()
        for name in ("state", "config"):
            directory = self.root / name
            directory.mkdir()
            (directory / "runtime.json").write_text('{"test": true}\n', encoding="utf-8")
            (directory / "runtime.md").write_text("Ignored runtime notes\n", encoding="utf-8")
        self.assertEqual(project_monitor.snapshot(self.root), before)

    def test_run_missing_or_malformed_files_fails_closed_without_details(self):
        config = self.write("config.json", self.config)
        evidence = self.root / "evidence.json"
        for contents in (None, PRIVATE, "[]", '{"checks": []}'):
            with self.subTest(contents=contents):
                if contents is not None:
                    evidence.write_text(contents, encoding="utf-8")
                with patch.object(project_monitor, "snapshot", return_value=(REVISION, self.docs)):
                    result = project_monitor.run(self.root, config, evidence, now=NOW)
                self.assertEqual(result["health"], "invalid")
                self.assertNotIn(PRIVATE, json.dumps(result))
                self.assertNotIn(str(self.root), json.dumps(result))

    def test_run_snapshot_failure_does_not_expose_exception(self):
        config = self.write("config.json", self.config)
        evidence = self.write("evidence.json", self.evidence)
        with patch.object(project_monitor, "snapshot", side_effect=subprocess.SubprocessError(PRIVATE)):
            result = project_monitor.run(self.root, config, evidence, now=NOW)
        self.assertEqual(result["health"], "invalid")
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_invalid_config_and_connector_records_fail_closed(self):
        config = self.write("config.json", self.config)
        for section, value in (
            ("checks", []), ("docs", []), ("connectors", []),
            ("connectors", {"rave": {"status": PRIVATE}}),
            ("connectors", {"rave": {"prerequisites": []}}),
        ):
            with self.subTest(section=section, value=value):
                evidence = copy.deepcopy(self.evidence)
                evidence[section] = value
                path = self.write("evidence.json", evidence)
                with patch.object(project_monitor, "snapshot", return_value=(REVISION, self.docs)):
                    self.assertEqual(
                        project_monitor.run(self.root, config, path, now=NOW)["health"], "invalid"
                    )
        self.config["required_checks"] = []
        config = self.write("config.json", self.config)
        with patch.object(project_monitor, "snapshot", return_value=(REVISION, self.docs)):
            result = project_monitor.run(
                self.root, config, self.write("evidence.json", self.evidence), now=NOW
            )
        self.assertEqual(result["health"], "invalid")

    def test_summary_reports_counts_and_rave_prerequisites(self):
        self.evidence["connectors"]["rave"]["prerequisites"]["approval"] = False
        text, attention = project_monitor.summary(
            self.write("status.json", self.evaluate()), now=NOW
        )
        self.assertTrue(attention)
        self.assertIn("Checks: 2/2 passed", text)
        self.assertIn(
            "Connector-2: blocked; prerequisites outstanding: interface, verification, approval",
            text,
        )
        self.assertIn(str(NOW - 60), text)

    def test_summary_never_uses_arbitrary_findings_or_record_content(self):
        status = self.evaluate()
        status["findings"] = [PRIVATE]
        status["documentation_review_paths"] = [PRIVATE]
        status["checks"][0].update({"check": PRIVATE, "output": PRIVATE})
        status["connectors"][0].update({"connector": PRIVATE, "notes": PRIVATE})
        status["connectors"][0]["missing"] = [PRIVATE, "approval"]
        text, attention = project_monitor.summary(self.write("status.json", status), now=NOW)
        self.assertTrue(attention)
        self.assertNotIn(PRIVATE, text)
        self.assertEqual(text, "Project: monitoring data missing, stale or invalid")

    def test_documentation_review_paths_are_json_only_not_summary_text(self):
        self.docs = {f"{PRIVATE}.md": "changed-hash"}
        status = self.evaluate()
        self.assertEqual(status["documentation_review_paths"], [f"{PRIVATE}.md"])
        text, attention = project_monitor.summary(self.write("status.json", status), now=NOW)
        self.assertTrue(attention)
        self.assertIn("Documentation review needs: 2", text)
        self.assertIn("Checks: 2/2 passed", text)
        self.assertNotIn(PRIVATE, text)

    def test_summary_requires_expiry_last_success_and_consistent_health(self):
        status = self.evaluate()
        status.update(health="healthy", expires_at=NOW + 60)
        for connector in status["connectors"]:
            connector.update(status="verified", missing=[])
        path = self.write("status.json", status)
        self.assertFalse(project_monitor.summary(path, now=NOW)[1])
        for update in (
            {"health": "attention"}, {"expires_at": None},
            {"expires_at": NOW - 1}, {"expires_at": NOW + 86401},
            {"last_successful_check": None}, {"last_successful_check": NOW + 1},
            {"documentation_review_count": 1},
        ):
            with self.subTest(update=update):
                path = self.write("status.json", dict(status, **update))
                self.assertTrue(project_monitor.summary(path, now=NOW)[1])

    def test_summary_missing_stale_future_and_malformed_never_green(self):
        path = self.root / "status.json"
        cases = [None, [], {}, {"schema": 1, "health": "healthy", "checked_at": NOW},
                 dict(self.evaluate(), schema=True),
                 dict(self.evaluate(), schema=1.0),
                 dict(self.evaluate(), checked_at=NOW - 7201),
                 dict(self.evaluate(), checked_at=NOW + 1),
                 dict(self.evaluate(), checks=[None]),
                 dict(self.evaluate(), connectors=[None])]
        for status in cases:
            with self.subTest(status=status):
                if status is not None:
                    path.write_text(json.dumps(status), encoding="utf-8")
                text, attention = project_monitor.summary(path, now=NOW)
                self.assertTrue(attention)
                self.assertNotIn("Project: healthy", text)
                self.assertEqual(text, "Project: monitoring data missing, stale or invalid")


if __name__ == "__main__":
    unittest.main()
