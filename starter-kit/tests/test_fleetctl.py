import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


KIT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fleetctl", KIT / "fleetctl.py")
fleetctl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fleetctl)

STUB = """#!{python}
import json,os,pathlib,shlex,shutil,subprocess,sys
kind=pathlib.Path(sys.argv[0]).name
args=sys.argv[1:]
with open(os.environ['TEST_LOG'],'a') as f: f.write(json.dumps([kind]+args)+'\\n')
if kind=='systemctl': raise SystemExit(0)
if kind=='ssh':
 if os.environ.get('TEST_KNOWN')!='1': raise SystemExit(255)
 i=0
 while args[i]=='-o': i+=2
 command=shlex.split(args[i+1])
 if os.environ.get('TEST_REMOTE_ROOT')=='1' and command[:2]==['python3','-c']:
  command[2]='import os;os.getuid=lambda:0\\n'+command[2]
 env=dict(os.environ,HOME=os.environ['TEST_REMOTE_HOME'])
 raise SystemExit(subprocess.run(command,env=env).returncode)
if kind=='scp':
 source,destination=args[-2:]
 path=destination.split(':',1)[1]
 shutil.copyfile(source,path)
 if os.environ.get('TEST_TAMPER')=='1' and path.endswith('src__heartbeat.py'):
  pathlib.Path(path).write_text('tampered')
 raise SystemExit(0)
if kind=='ssh-keyscan':
 print(args[-1]+' ssh-ed25519 '+os.environ['TEST_HOST_KEY'])
 raise SystemExit(0)
if kind=='ssh-keygen':
 print('256 '+os.environ['TEST_FINGERPRINT']+' test (ED25519)')
 raise SystemExit(0)
"""


class FleetctlTests(unittest.TestCase):
    def setUp(self):
        # Keep test artifacts inside the checkout, never a global temporary path.
        self.tmp = tempfile.TemporaryDirectory(prefix=".fleetctl-test-", dir=KIT.parent)
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / "home"
        self.remote_home = self.base / "remote"
        self.bin = self.base / "bin"
        for directory in (self.home, self.remote_home, self.bin):
            directory.mkdir(mode=0o700)
        self.log = self.base / "commands.jsonl"
        for command in ("ssh", "scp", "systemctl", "ssh-keyscan", "ssh-keygen"):
            path = self.bin / command
            path.write_text(STUB.format(python=sys.executable))
            path.chmod(0o700)
        self.env = {
            "HOME": str(self.home),
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "TEST_REMOTE_HOME": str(self.remote_home),
            "TEST_LOG": str(self.log),
            "TEST_KNOWN": "1",
        }
        self.patch = patch.dict(os.environ, self.env)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fleetctl.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def commands(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def config(self, filename, value, source=None, mode=0o600):
        path = (source or self.home / "kit") / "config" / filename
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(value if isinstance(value, str) else json.dumps(value))
        path.chmod(mode)
        return path

    def source(self):
        path = self.home / "source"
        for relative in fleetctl.PUBLIC:
            destination = path / relative
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(KIT / relative, destination)
        return path

    def install(self, **overrides):
        opts = fleetctl.settings(dict(overrides))
        with contextlib.redirect_stdout(io.StringIO()):
            fleetctl.install(opts, fleetctl.bundle(KIT, opts))
        return opts, self.home / "fleet-kit"

    def test_init_private_no_install_no_overwrite_and_json_flags(self):
        path = self.home / "settings.json"
        code, _, error = self.cli("init", "--output", str(path), "--kit-name", "orchard",
                                  "--unit-prefix", "orchard", "--role", "client", "--node-name", "edge-one")
        self.assertEqual(code, 0, error)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(json.loads(path.read_bytes())["kit_name"], "orchard")
        self.assertFalse((self.home / "fleet-kit").exists())
        self.assertEqual(self.commands(), [])
        self.assertEqual(self.cli("init", "--output", str(path))[0], 1)
        path.write_text('{"kit_name": "bad;touch"}')
        self.assertEqual(self.cli("--userconfig", str(path), "status")[0], 1)

    def test_names_paths_and_host_injection_fail_before_commands(self):
        for flag in ("--kit-name", "--unit-prefix", "--hub-label", "--client-label", "--node-name"):
            for value in ("a;id", "a\nExecStart=id", "-a", "UPPER", "a" * 33, "x%h"):
                with self.subTest(flag=flag, value=value):
                    self.assertEqual(self.cli("deploy", flag + "=" + value)[0], 1)
        for value in ("/", "~/../escape", "~/kit%h", "~/kit;id", "~/has space", "~/a//b"):
            self.assertEqual(self.cli("deploy", "--install-dir", value)[0], 1)
        for value in ("root@localhost", "user@host;id", "-oProxyCommand=id", "user:pass@host"):
            self.assertEqual(self.cli("deploy", "--host=" + value)[0], 1)
        self.assertEqual(self.commands(), [])

    def test_dryrun_exact_manifest_excludes_private_state_and_no_network(self):
        source = self.source()
        self.config("fleet.env", "NTFY_TOPIC=private-topic\n", source)
        (source / "state").mkdir()
        (source / "state/private.json").write_text("private")
        (source / "hub.env").write_text("private")
        code, output, error = self.cli("deploy", "--source", str(source), "--host", "user@host")
        self.assertEqual(code, 0, error)
        plan, _ = json.JSONDecoder().raw_decode(output)
        self.assertEqual(set(plan["source_manifest"]), set(fleetctl.PUBLIC))
        for key, sha in plan["source_manifest"].items():
            self.assertEqual(sha, hashlib.sha256((source / key).read_bytes()).hexdigest())
        self.assertNotIn("private-topic", output)
        self.assertEqual(self.commands(), [])

    def test_public_examples_allowed_runtime_placeholders_refused(self):
        source = self.source()
        self.assertEqual(self.cli("deploy", "--source", str(source))[0], 0)
        self.config("fleet_manifest.json", {"nodes": [{"name": "edge", "macs": ["xx:xx:xx:xx:xx:xx"]}]}, source)
        for command in ("deploy", "check", "connect"):
            self.assertEqual(self.cli(command, "--source", str(source), "--host", "user@host")[0], 1)
        self.assertEqual(self.commands(), [])

    def test_private_permissions_symlinks_and_no_shell_data(self):
        source = self.source()
        config = self.config("fleet.env", "NTFY_TOPIC=topic\n", source, 0o644)
        self.assertEqual(self.cli("deploy", "--source", str(source), "--include-config", "fleet.env")[0], 1)
        config.chmod(0o600)
        config.write_text("NTFY_TOPIC=$(touch marker)\n")
        self.assertEqual(self.cli("deploy", "--source", str(source))[0], 1)
        config.unlink()
        config.symlink_to(KIT / "config/fleet.env.example")
        self.assertEqual(self.cli("deploy", "--source", str(source))[0], 1)
        self.assertEqual(self.cli("deploy", "--include-config", "../hub.env")[0], 1)
        self.assertEqual(self.commands(), [])

    def test_notification_placeholders_duplicate_keys_and_bad_addresses_refused(self):
        source = self.source()
        for content in (
            "NTFY_TOPIC=first\nNTFY_TOPIC=second\n",
            "NTFY_TOPIC=topic\nNTFY_SERVER=https://x-mesh-host\n",
            "NTFY_TOPIC=topic-x\n",
            "NTFY_TOPIC=topic\nNTFY_SERVER=https://[broken\n",
            "NTFY_TOPIC=topic\nNTFY_SERVER=https://ntfy.sh:bad\n",
        ):
            self.config("fleet.env", content, source)
            self.assertEqual(self.cli("deploy", "--send", "--source", str(source))[0], 1)
        (source / "config/fleet.env").unlink()
        for address in ("server-x", "CHANGE_ME", "host;id", "<hostname>"):
            self.config("fleet_manifest.json", {"nodes": [{"name": "edge", "mesh_name": address}]}, source)
            self.assertEqual(self.cli("connect", "--host", "user@host", "--source", str(source))[0], 1)
        self.assertEqual(self.commands(), [])

    def test_apply_ssh_scp_real_receiver_units_permissions_and_idempotence(self):
        (self.remote_home / ".local").mkdir(mode=0o755)
        args = ("deploy", "--apply", "--host", "user@host", "--kit-name", "orchard",
                "--unit-prefix", "orchard", "--role", "client", "--node-name", "edge-one",
                "--install-dir", "~/orchard-kit", "--client-label", "scout")
        code, _, error = self.cli(*args)
        self.assertEqual(code, 0, error)
        dest = self.remote_home / "orchard-kit"
        units = self.remote_home / ".config/systemd/user"
        service = (units / "orchard-heartbeat.service").read_text()
        self.assertIn("--name edge-one", service)
        self.assertIn("orchard scout heartbeat", service)
        self.assertIn(str(dest), service)
        self.assertFalse((units / "fleet-heartbeat.service").exists())
        self.assertEqual((dest / "systemd/orchard-heartbeat.service").read_text(), service)
        self.assertFalse((dest / "systemd/fleet-heartbeat.service").exists())
        self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((dest / "config/fleet.env").stat().st_mode), 0o600)
        self.assertTrue((dest / fleetctl.MANIFEST).exists())
        self.assertEqual(stat.S_IMODE((dest / "install.sh").stat().st_mode), 0o700)
        commands = self.commands()
        self.assertTrue(any(cmd[0] == "scp" for cmd in commands))
        for cmd in commands:
            if cmd[0] in ("ssh", "scp"):
                for option in ("BatchMode=yes", "StrictHostKeyChecking=yes", "ForwardAgent=no"):
                    self.assertIn(option, cmd)
        self.assertFalse(any("enable" in cmd for cmd in commands))
        self.assertEqual(self.cli(*args)[0], 0)
        self.assertEqual(list((self.remote_home / ".local/state/fleetctl/staging").iterdir()), [])

    def test_remote_status_uninstall_uses_trusted_controller_even_after_removal(self):
        args = ("--host", "user@host")
        self.assertEqual(self.cli("deploy", "--apply", *args)[0], 0)
        dest = self.remote_home / "fleet-kit"
        (dest / "fleetctl.py").write_text("raise SystemExit('untrusted installed controller')")
        source = self.source()
        self.config("fleet_manifest.json", {"nodes": [{"name": "edge", "mesh_name": "x-mesh-host"}]}, source)
        self.assertEqual(self.cli("status", "--source", str(source), *args)[0], 0)
        self.assertEqual(self.cli("uninstall", "--apply", *args)[0], 0)
        self.assertTrue((dest / "fleetctl.py").exists())
        self.assertFalse((dest / "src/heartbeat.py").exists())
        self.assertEqual(self.cli("status", *args)[0], 0)
        self.assertEqual(self.cli("uninstall", "--apply", *args)[0], 0)

    def test_remote_root_refused_before_scp(self):
        os.environ["TEST_REMOTE_ROOT"] = "1"
        self.assertEqual(self.cli("deploy", "--apply", "--host", "user@host")[0], 1)
        self.assertFalse(any(cmd[0] == "scp" for cmd in self.commands()))
        self.assertFalse((self.remote_home / "fleet-kit").exists())

    def test_unknown_host_fails_without_transfer_or_trust_mutation(self):
        os.environ["TEST_KNOWN"] = "0"
        code, _, error = self.cli("deploy", "--apply", "--host", "user@host")
        self.assertEqual(code, 1)
        self.assertIn("out-of-band", error)
        self.assertEqual([cmd[0] for cmd in self.commands()], ["ssh"])
        self.assertFalse((self.remote_home / "fleet-kit").exists())
        self.assertFalse((self.home / ".ssh/known_hosts").exists())

    def test_explicit_host_trust_compares_fingerprint_and_is_isolated(self):
        import base64
        key = b"test-public-host-key"
        fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(key).digest()).decode().rstrip("=")
        os.environ["TEST_HOST_KEY"] = base64.b64encode(key).decode()
        os.environ["TEST_FINGERPRINT"] = fingerprint
        args = ("connect", "--host", "user@host", "--trust-host-key")
        self.assertEqual(self.cli(*args, "--expected-fingerprint", "SHA256:" + "A" * 43)[0], 1)
        self.assertFalse(any(cmd[0] == "ssh" for cmd in self.commands()))
        self.assertEqual(self.cli(*args, "--expected-fingerprint", fingerprint)[0], 0)
        ssh = [cmd for cmd in self.commands() if cmd[0] == "ssh"][0]
        self.assertTrue(any(arg.startswith("UserKnownHostsFile=") for arg in ssh))
        self.assertNotIn("accept-new", " ".join(ssh))
        self.assertEqual(list((self.home / ".local/state/fleetctl").iterdir()), [])

    def test_checksum_tamper_before_any_installation(self):
        os.environ["TEST_TAMPER"] = "1"
        self.assertEqual(self.cli("deploy", "--apply", "--host", "user@host")[0], 1)
        self.assertFalse((self.remote_home / "fleet-kit").exists())
        self.assertFalse(any(cmd[0] == "systemctl" for cmd in self.commands()))

    def test_nooverwrite_preflight_leaves_no_partial_installation(self):
        target = self.home / ".config/systemd/user/fleet-poll.service"
        target.parent.mkdir(parents=True)
        target.write_text("unowned")
        opts = fleetctl.settings({})
        with self.assertRaises(fleetctl.Refusal):
            fleetctl.install(opts, fleetctl.bundle(KIT, opts))
        self.assertEqual(target.read_text(), "unowned")
        self.assertFalse((self.home / "fleet-kit").exists())
        self.assertEqual(self.commands(), [])

    def test_unowned_identical_files_and_insecure_existing_runtime_config_refused(self):
        dest = self.home / "fleet-kit"
        dest.mkdir(mode=0o700)
        target = dest / "requirements.txt"
        target.write_bytes((KIT / "requirements.txt").read_bytes())
        opts = fleetctl.settings({})
        with self.assertRaisesRegex(fleetctl.Refusal, "unowned"):
            fleetctl.install(opts, fleetctl.bundle(KIT, opts))
        target.unlink()
        path = self.config("fleet.env", "NTFY_TOPIC=sensitive\n", source=dest, mode=0o644)
        with self.assertRaisesRegex(fleetctl.Refusal, "permissions"):
            fleetctl.install(opts, fleetctl.bundle(KIT, opts))
        path.unlink()
        path.symlink_to(KIT / "config/fleet.env.example")
        with self.assertRaisesRegex(fleetctl.Refusal, "Symlink"):
            fleetctl.install(opts, fleetctl.bundle(KIT, opts))
        self.assertEqual(self.commands(), [])

    def test_local_units_default_no_send_and_legacy_defaults(self):
        opts, dest = self.install()
        unitdir = self.home / ".config/systemd/user"
        self.assertNotIn("--send", (unitdir / "fleet-poll.service").read_text())
        self.assertNotIn("--apply", (unitdir / "fleet-heal.service").read_text())
        self.assertEqual(set(fleetctl.unit_names(opts)), {"poll", "daily", "heal", "project"})
        self.assertEqual(self.cli("_install", "--install-dir", "~/other-kit", "--unit-prefix", "other",
                                  "--send")[0], 0)
        self.assertIn("--send", (unitdir / "other-daily.service").read_text())
        self.assertTrue((dest / "state/heartbeats").is_dir())

    def test_send_and_activation_require_real_config_never_enable_heal(self):
        source = self.source()
        args = ("deploy", "--source", str(source), "--role", "client", "--node-name", "edge",
                "--enable", "--send", "--apply", "--host", "user@host")
        self.assertEqual(self.cli(*args)[0], 1)
        self.assertEqual(self.commands(), [])
        self.config("fleet.env", "NTFY_TOPIC=valid-topic\n", source)
        self.assertEqual(self.cli(*args, "--include-config", "fleet.env")[0], 0)
        enabled = [cmd for cmd in self.commands() if "enable" in cmd]
        self.assertEqual(enabled, [["systemctl", "--user", "enable", "--now", "fleet-heartbeat.timer"]])

    def test_hub_custom_units_enable_only_poll_daily_without_repo(self):
        source = self.source()
        self.config("fleet_manifest.json", {"nodes": [{"name": "edge", "macs": ["02:00:00:00:00:01"]}]}, source)
        args = ("deploy", "--source", str(source), "--host", "user@host", "--apply",
                "--enable", "--unit-prefix", "garden", "--kit-name", "garden",
                "--hub-label", "orchestrator", "--include-config", "fleet_manifest.json")
        self.assertEqual(self.cli(*args)[0], 0)
        enabled = [cmd[-1] for cmd in self.commands() if "enable" in cmd]
        self.assertEqual(enabled, ["garden-poll.timer", "garden-daily.timer"])
        units = self.remote_home / ".config/systemd/user"
        for item in ("poll", "daily", "heal", "project"):
            text = (units / ("garden-" + item + ".service")).read_text()
            self.assertIn("garden orchestrator " + item, text)
            self.assertNotIn("--send", text)
            self.assertNotIn("--apply", text)
        self.assertEqual(self.cli("status", "--host", "user@host", "--unit-prefix", "garden",
                                  "--kit-name", "garden", "--hub-label", "orchestrator")[0], 0)

    def test_repo_activation_requires_existing_checkout(self):
        opts = fleetctl.settings({"repo": str(self.home / "missing"), "enable": True})
        payload = fleetctl.bundle(KIT, opts)
        payload["config/fleet_manifest.json"] = json.dumps(
            {"nodes": [{"name": "edge", "macs": ["02:00:00:00:00:01"]}]}
        ).encode()
        with self.assertRaisesRegex(fleetctl.Refusal, "checkout"):
            fleetctl.install(opts, payload)
        self.assertFalse((self.home / "fleet-kit").exists())
        repo = self.home / "repo"
        repo.mkdir(mode=0o700)
        (repo / ".git").mkdir()
        opts["repo"] = str(repo)
        with contextlib.redirect_stdout(io.StringIO()):
            fleetctl.install(opts, payload)
        enabled = [cmd[-1] for cmd in self.commands() if "enable" in cmd]
        self.assertEqual(enabled, ["fleet-poll.timer", "fleet-daily.timer", "fleet-project.timer"])

    def test_receiver_rejects_unknown_entries_and_hash_mismatches_before_install(self):
        opts = fleetctl.settings({})
        payload = fleetctl.bundle(KIT, opts)
        for variant in ("extra", "unknown-key", "mismatch", "symlink"):
            stage = self.home / variant
            stage.mkdir(mode=0o700)
            hashes = {key: fleetctl.digest(value) for key, value in payload.items()}
            for key, value in payload.items():
                path = stage / key.replace("/", "__")
                path.write_bytes(value)
                path.chmod(0o600)
            if variant == "extra":
                (stage / "unexpected").write_text("unknown")
            elif variant == "unknown-key":
                hashes["../escape"] = fleetctl.digest(b"unknown")
            elif variant == "mismatch":
                (stage / "src__heartbeat.py").write_text("tampered")
            else:
                (stage / "src__heartbeat.py").unlink()
                (stage / "src__heartbeat.py").symlink_to(KIT / "src/heartbeat.py")
            request = fleetctl.encoded({"settings": opts, "files": hashes})
            (stage / "request.json").write_bytes(request)
            (stage / "request.json").chmod(0o600)
            with self.subTest(variant=variant), self.assertRaises(fleetctl.Refusal):
                fleetctl.receive(stage, fleetctl.digest(request))
            self.assertFalse((self.home / "fleet-kit").exists())
        self.assertEqual(self.commands(), [])

    def test_check_hub_requires_manifest_client_requires_node(self):
        source = self.source()
        self.assertEqual(self.cli("check", "--source", str(source))[0], 1)
        self.assertEqual(self.cli("check", "--source", str(source), "--role", "client")[0], 1)
        self.config("fleet_manifest.json", {"nodes": [{"name": "edge", "macs": ["02:00:00:00:00:01"]}]}, source)
        self.assertEqual(self.cli("check", "--source", str(source))[0], 0)

    def test_status_and_uninstall_preserve_modified_config_runtime_and_symlink_target(self):
        opts, dest = self.install()
        secret = dest / "config/fleet.env"
        secret.write_text("NTFY_TOPIC=never-print-this\n")
        state = dest / "state/heartbeats/edge.json"
        state.write_text("runtime")
        target = self.home / "outside"
        target.write_text("outside")
        script = dest / "src/heartbeat.py"
        script.unlink()
        script.symlink_to(target)
        code, output, error = self.cli("status")
        self.assertEqual(code, 0, error)
        self.assertIn("kit/config/fleet.env: modified", output)
        self.assertNotIn("never-print", output)
        self.assertEqual(self.cli("uninstall")[0], 0)
        self.assertTrue((dest / "fleetctl.py").exists())
        self.assertEqual(self.cli("uninstall", "--apply")[0], 0)
        self.assertEqual(target.read_text(), "outside")
        self.assertTrue(script.is_symlink())
        self.assertEqual(secret.read_text(), "NTFY_TOPIC=never-print-this\n")
        self.assertEqual(state.read_text(), "runtime")
        self.assertFalse((dest / "fleetctl.py").exists())
        manifest = json.loads((dest / fleetctl.MANIFEST).read_text())
        self.assertEqual(set(manifest["files"]), {"kit/config/fleet.env", "kit/src/heartbeat.py"})

    def test_forged_uninstall_paths_fail_closed(self):
        opts, dest = self.install()
        outside = self.home / "valuable"
        outside.write_text("keep")
        manifest_path = dest / fleetctl.MANIFEST
        original = json.loads(manifest_path.read_text())
        for key in ("kit/../../valuable", "unit/../../valuable", "kit/.git/config",
                    "other/valuable", "/home/valuable"):
            manifest = dict(original, files={key: hashlib.sha256(b"keep").hexdigest()})
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(self.cli("uninstall", "--apply")[0], 1)
            self.assertEqual(outside.read_text(), "keep")

    def test_root_and_symlink_install_refused(self):
        opts = fleetctl.settings({})
        with patch.object(fleetctl.os, "getuid", return_value=0):
            with self.assertRaises(fleetctl.Refusal):
                fleetctl.install(opts, fleetctl.bundle(KIT, opts))
        (self.home / "fleet-kit").symlink_to(self.remote_home, target_is_directory=True)
        with self.assertRaises(fleetctl.Refusal):
            fleetctl.install(opts, fleetctl.bundle(KIT, opts))
        self.assertEqual(self.commands(), [])

    def test_failed_write_is_visible_and_not_successfully_recorded(self):
        opts = fleetctl.settings({})
        original = fleetctl.atomic

        def fail(path, data, replace=False):
            if path.name == "fleet.env.example":
                raise OSError("simulated full disk")
            return original(path, data, replace)

        with patch.object(fleetctl, "atomic", side_effect=fail):
            with self.assertRaisesRegex(fleetctl.Refusal, "partial files"):
                fleetctl.install(opts, fleetctl.bundle(KIT, opts))
        self.assertFalse((self.home / "fleet-kit" / fleetctl.MANIFEST).exists())
        self.assertEqual(list((self.home / "fleet-kit").glob("*.py")), [])
        self.assertFalse(any(cmd[0] == "systemctl" for cmd in self.commands()))


if __name__ == "__main__":
    unittest.main()
