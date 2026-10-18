#!/usr/bin/env python3
"""Unprivileged, opt-in fleet kit installation and SSH deployment."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import subprocess
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
SAFE_PATH = re.compile(r"^[A-Za-z0-9_./~-]+$")
HOST = re.compile(r"^[a-z_][a-z0-9_-]*@[A-Za-z0-9][A-Za-z0-9.-]*$")
PRIVATE = ("fleet.env", "fleet_manifest.json", "maintenance.json")
SCRIPTS = ("daily_status.py", "docs_publish.py", "fleet_poll.py", "heartbeat.py", "ntfy_notify.py",
           "project_monitor.py", "resolver.py", "wol_healer.py")
EXAMPLES = ("fleet.env.example", "fleet_manifest.example.json", "maintenance.example.json")
PUBLIC = ("fleetctl.py", "install.sh", "requirements.txt") + tuple(
    "src/" + name for name in SCRIPTS
) + tuple("config/" + name for name in EXAMPLES)
DEFAULTS = {
    "kit_name": "fleet", "unit_prefix": "fleet", "install_dir": "~/fleet-kit",
    "role": "hub", "hub_label": "hub", "client_label": "client",
    "node_name": None, "repo": None, "host": None, "send": False, "enable": False,
    "include_config": [],
}
MANIFEST = ".fleetctl-installed.json"


class Refusal(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)


def name(value, label):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise Refusal(label + " must match ^[a-z][a-z0-9-]{0,31}$")
    return value


def path_text(value):
    if not isinstance(value, str) or not SAFE_PATH.fullmatch(value):
        raise Refusal("Unsafe directory: use a plain absolute or ~/ path without spaces")
    if ".." in value.split("/") or "//" in value or value.endswith("/"):
        raise Refusal("Unsafe directory components")
    if not value.startswith(("/", "~/")):
        raise Refusal("Directory must be absolute or start with ~/")
    return value


def settings(raw):
    if not isinstance(raw, dict) or set(raw) - set(DEFAULTS):
        raise Refusal("Unknown userconfig settings")
    result = dict(DEFAULTS, **raw)
    for key in ("kit_name", "unit_prefix", "hub_label", "client_label"):
        name(result[key], key)
    if result["node_name"] is not None:
        name(result["node_name"], "node_name")
    if result["role"] not in ("hub", "client"):
        raise Refusal("Role must be hub or client")
    path_text(result["install_dir"])
    if result["repo"] is not None:
        path_text(result["repo"])
    if result["host"] is not None:
        if not isinstance(result["host"], str) or not HOST.fullmatch(result["host"]):
            raise Refusal("SSH target must be user@host (no options or passwords)")
        if result["host"].split("@")[0] == "root":
            raise Refusal("Root SSH targets are forbidden")
    for flag in ("send", "enable"):
        if not isinstance(result[flag], bool):
            raise Refusal(flag + " must be boolean")
    includes = result["include_config"]
    if not isinstance(includes, list) or any(item not in PRIVATE for item in includes):
        raise Refusal("--include-config allows only exact fleet.env, fleet_manifest.json, maintenance.json")
    result["include_config"] = sorted(set(includes))
    return result


def inspect(path, directory=False, private=False, secure=True):
    """Check all existing ancestors without resolving symlinks."""
    path = Path(path).absolute()
    for parent in reversed((path,) + tuple(path.parents)):
        if not parent.exists() and not parent.is_symlink():
            continue
        st = parent.lstat()
        if stat.S_ISLNK(st.st_mode):
            raise Refusal("Symlink path refused: " + str(parent))
        if parent == path:
            if st.st_uid != os.getuid():
                raise Refusal("Path is not owned by current user: " + str(path))
            expected = stat.S_ISDIR if directory else stat.S_ISREG
            if not expected(st.st_mode):
                raise Refusal("Unexpected file type: " + str(path))
            if private and st.st_mode & 0o077:
                raise Refusal("Private path permissions must exclude group/other: " + str(path))
            if directory and secure and st.st_mode & 0o022:
                raise Refusal("Writable directory refused: " + str(path))
        elif not stat.S_ISDIR(st.st_mode):
            raise Refusal("Non-directory ancestor: " + str(parent))
        elif secure and st.st_mode & 0o022 and not (
            parent == Path("/tmp") and st.st_mode & stat.S_ISVTX
        ):
            raise Refusal("Writable ancestor refused: " + str(parent))
    return path


def home_path(value):
    path_text(value)
    home = Path.home().absolute()
    path = Path(value.replace("~/", str(home) + "/", 1)).absolute()
    path_text(str(path))
    if path == home or home not in path.parents:
        raise Refusal("Install directory must be strictly inside the current user's home")
    inspect(path, directory=True)
    return path


def mkdir(path):
    inspect(path, directory=True)
    missing = []
    current = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    for item in reversed(missing):
        item.mkdir(mode=0o700)


def read_private(path):
    inspect(path, private=True)
    if not path.is_file():
        raise Refusal("Missing private configuration: " + str(path))
    if path.stat().st_size > 1024 * 1024:
        raise Refusal("Configuration is too large")
    return path.read_bytes()


def load_json(data):
    try:
        return json.loads(data)
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise Refusal("Invalid JSON configuration") from exc


def placeholder(value):
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            pending.extend(v for k, v in current.items() if not k.startswith("_"))
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, str) and (
            re.search(r"change[-_]me|placeholder|[<>]", current, re.I)
            or current.lower().startswith(("x-", "xx:", "x.x.", "xxxx"))
        ):
            return True
    return False


def address(value):
    if (not isinstance(value, str) or not value or len(value) > 253
            or not re.fullmatch(r"[A-Za-z0-9_.:-]+", value)
            or re.search(r"(?:^|[.:-])x+(?:$|[.:-])", value, re.I)
            or placeholder(value)):
        raise Refusal("Invalid or placeholder runtime address")


def environment(data):
    result = {}
    for line in data.decode().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise Refusal("Invalid fleet.env assignment (never executed)")
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise Refusal("Invalid fleet.env key")
        if key in result:
            raise Refusal("Duplicate fleet.env assignment")
        value = value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        if any(c in value for c in ("$", "`", "\x00")):
            raise Refusal("Shell expressions are not configuration")
        result[key] = value
    if placeholder(result):
        raise Refusal("Replace runtime configuration placeholders")
    return result


def validate_runtime(config, opts, required=False, supplied=None):
    supplied = supplied or {}
    if opts["role"] == "client" and not opts["node_name"]:
        raise Refusal("Client operations require --node-name")
    for filename in PRIVATE:
        path = config / filename
        if filename not in supplied and not path.exists() and not path.is_symlink():
            if required and filename == "fleet_manifest.json" and opts["role"] == "hub":
                raise Refusal("Hub requires a private fleet_manifest.json")
            if (required or opts["send"]) and filename == "fleet.env" and opts["send"]:
                raise Refusal("--send requires private fleet.env")
            continue
        data = supplied[filename] if filename in supplied else read_private(path)
        if filename == "fleet.env":
            env = environment(data)
            if any(re.search(r"(?:^|[-_.:/])x+(?:$|[-_.:/])", env.get(key, ""), re.I)
                   for key in ("NTFY_TOPIC", "NTFY_TOKEN")):
                raise Refusal("Replace notification placeholders")
            if env.get("NTFY_SERVER"):
                try:
                    server = urlsplit(env["NTFY_SERVER"])
                    port = server.port
                except ValueError as exc:
                    raise Refusal("Invalid NTFY_SERVER") from exc
                if (server.scheme not in ("http", "https") or not server.hostname
                        or server.username or server.password or server.query or server.fragment
                        or (port is not None and not 1 <= port <= 65535)):
                    raise Refusal("Invalid NTFY_SERVER")
                address(server.hostname)
            if opts["send"]:
                topic = env.get("NTFY_TOPIC", "")
                if (not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", topic)
                        or re.search(r"(?:^|[-_])x+(?:$|[-_])", topic, re.I)):
                    raise Refusal("--send requires a nonempty valid NTFY_TOPIC")
        else:
            value = load_json(data)
            if not isinstance(value, dict) or placeholder(value):
                raise Refusal("Replace runtime JSON placeholders")
            if filename == "fleet_manifest.json":
                nodes = value.get("nodes")
                if not isinstance(nodes, list) or not nodes:
                    raise Refusal("Manifest requires nodes")
                seen = set()
                for node in nodes:
                    if not isinstance(node, dict):
                        raise Refusal("Invalid manifest node")
                    name(node.get("name"), "manifest node")
                    if node["name"] in seen:
                        raise Refusal("Duplicate manifest node")
                    seen.add(node["name"])
                    macs = node.get("macs", [])
                    if not isinstance(macs, list):
                        raise Refusal("Invalid manifest MAC list")
                    for mac in macs:
                        if not isinstance(mac, str) or not re.fullmatch(
                            r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", mac
                        ):
                            raise Refusal("Invalid manifest MAC")
                    for key in ("mesh_name", "last_known_address"):
                        if key in node:
                            address(node[key])
                    port = node.get("probe_port", 22)
                    if type(port) is not int or not 1 <= port <= 65535:
                        raise Refusal("Invalid manifest probe port")
                if "wol_broadcast" in value:
                    address(value["wol_broadcast"])


def bundle(source, opts):
    result = {}
    for relative in PUBLIC:
        path = source / relative
        inspect(path, secure=False)
        if not path.is_file():
            raise Refusal("Missing allowed source: " + relative)
        result[relative] = path.read_bytes()
    for filename in opts["include_config"]:
        result["config/" + filename] = read_private(source / "config" / filename)
    return result


def unit_names(opts):
    return ("heartbeat",) if opts["role"] == "client" else ("poll", "daily", "heal", "project")


def units(opts, dest):
    prefix = opts["unit_prefix"]
    label = opts[opts["role"] + "_label"]
    env = "Environment=FLEET_ENV=" + str(dest / "config/fleet.env") + "\n"
    commands = {
        "poll": "src/fleet_poll.py --manifest config/fleet_manifest.json",
        "daily": "src/daily_status.py",
        "heal": "src/wol_healer.py --manifest config/fleet_manifest.json",
        "project": "src/project_monitor.py --repo " + (
            str(Path(opts["repo"]).expanduser()) if opts["repo"] else str(dest / "unconfigured-repo")
        ),
        "heartbeat": "src/heartbeat.py --name " + (opts["node_name"] or "unconfigured")
        + " --out " + str(dest / "state/heartbeats" / ((opts["node_name"] or "unconfigured") + ".json")),
    }
    calendars = {"poll": "*:0/2", "daily": "*-*-* 07:10:00", "heal": "*:0/5",
                 "project": "hourly", "heartbeat": "*:0/5"}
    result = {}
    for item in unit_names(opts):
        command = commands[item] + (" --send" if opts["send"] and item in ("poll", "daily") else "")
        stem = prefix + "-" + item
        result[stem + ".service"] = (
            "[Unit]\nDescription=" + opts["kit_name"] + " " + label + " " + item
            + "\n\n[Service]\nType=oneshot\nWorkingDirectory=" + str(dest) + "\n"
            + (env if item in ("poll", "daily", "heal") else "")
            + "ExecStart=/usr/bin/python3 " + command + "\n"
        ).encode()
        result[stem + ".timer"] = (
            "[Unit]\nDescription=" + opts["kit_name"] + " " + item + " timer\n\n"
            "[Timer]\nOnBootSec=1min\nOnCalendar=" + calendars[item]
            + "\nPersistent=true\n\n[Install]\nWantedBy=timers.target\n"
        ).encode()
    return result


def targets(opts):
    dest = home_path(opts["install_dir"])
    unitdir = Path.home() / ".config/systemd/user"
    inspect(unitdir, directory=True)
    return dest, unitdir


def allowed_records(opts, dest):
    return set("kit/" + p for p in PUBLIC) | set(
        "kit/config/" + p for p in PRIVATE
    ) | set(prefix + p for prefix in ("unit/", "kit/systemd/") for p in units(opts, dest))


def record_path(key, dest, unitdir):
    base, relative = key.split("/", 1)
    return (dest if base == "kit" else unitdir) / relative


def installed(opts, dest):
    path = dest / MANIFEST
    if not path.exists() and not path.is_symlink():
        return {}
    data = load_json(read_private(path))
    if not isinstance(data, dict) or data.get("settings") != recorded_settings(opts):
        raise Refusal("Installed manifest belongs to different settings; use original userconfig")
    records = data.get("files")
    if not isinstance(records, dict) or not set(records) <= allowed_records(opts, dest):
        raise Refusal("Unsafe installed-files manifest")
    if any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
           for v in records.values()):
        raise Refusal("Invalid installed hash")
    return records


def recorded_settings(opts):
    return dict(opts, host=None, enable=False, send=False, include_config=[])


def atomic(path, data, replace=False):
    temp = path.parent / (".fleetctl-write-" + secrets.token_hex(12))
    try:
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temp, path)
        else:
            os.link(temp, path, follow_symlinks=False)
            temp.unlink()
    finally:
        if temp.exists():
            temp.unlink()


def install(opts, payload, legacy=False):
    if os.getuid() == 0:
        raise Refusal("Never install or manage services as root")
    dest, unitdir = targets(opts)
    previous = installed(opts, dest)
    had_manifest = (dest / MANIFEST).exists()
    for filename in PRIVATE:
        path = dest / "config" / filename
        if path.exists() or path.is_symlink():
            read_private(path)
    writes = {"kit/" + key: value for key, value in payload.items()}
    for key, value in units(opts, dest).items():
        writes["unit/" + key] = value
        writes["kit/systemd/" + key] = value
    # Runtime examples are inert and always disabled. They are not activation-ready config.
    if not opts["enable"]:
        for filename, example in (("fleet.env", "fleet.env.example"),
                                  ("fleet_manifest.json", "fleet_manifest.example.json")):
            if filename == "fleet_manifest.json" and opts["role"] != "hub":
                continue
            key = "kit/config/" + filename
            path = dest / "config" / filename
            if key not in writes and not path.exists() and not path.is_symlink():
                writes[key] = payload["config/" + example]
    if not set(writes) <= allowed_records(opts, dest):
        raise Refusal("Unknown install entry")
    # Complete no-overwrite preflight before creating any installation files.
    for key, data in writes.items():
        path = record_path(key, dest, unitdir)
        inspect(path)
        if path.exists():
            current = digest(path.read_bytes())
            if previous.get(key) != current or current != digest(data):
                raise Refusal("Refusing to overwrite unowned or changed file: " + str(path))
    for key in previous:
        inspect(record_path(key, dest, unitdir))
    if opts["enable"]:
        validate_runtime(dest / "config", opts, required=True, supplied={
            p: payload["config/" + p] for p in PRIVATE if "config/" + p in payload
        })
        if opts["repo"]:
            repo = Path(opts["repo"]).expanduser()
            inspect(repo, directory=True)
            if not repo.is_dir() or not (repo / ".git").exists():
                raise Refusal("--repo must be an existing reviewed Git checkout")
    # Preflight every managed directory, including empty runtime directories.
    directories = {dest, unitdir, dest / "state", dest / "state/heartbeats"}
    directories.update(record_path(key, dest, unitdir).parent for key in writes)
    for directory in directories:
        inspect(directory, directory=True, private=(directory == dest or dest in directory.parents))
    mkdir(dest)
    mkdir(unitdir)
    mkdir(dest / "state/heartbeats")
    records = dict(previous)
    created = {}
    try:
        for key, data in writes.items():
            path = record_path(key, dest, unitdir)
            mkdir(path.parent)
            if not path.exists():
                atomic(path, data)
                created[path] = digest(data)
                if key in ("kit/fleetctl.py", "kit/install.sh"):
                    path.chmod(0o700)
            records[key] = digest(data)
        atomic(dest / MANIFEST, encoded({"settings": recorded_settings(opts), "files": records}),
               replace=had_manifest)
    except OSError as exc:
        for path, expected in reversed(list(created.items())):
            try:
                inspect(path)
                if digest(path.read_bytes()) == expected:
                    path.unlink()
            except (OSError, Refusal):
                pass
        raise Refusal("Installation write failed; new unchanged files rolled back; "
                      "inspect for modified partial files before retry: " + str(exc)) from exc
    run(["systemctl", "--user", "daemon-reload"])
    if opts["enable"]:
        for item in unit_names(opts):
            if item in ("heal", "project") and (item == "heal" or not opts["repo"]):
                continue
            run(["systemctl", "--user", "enable", "--now", opts["unit_prefix"] + "-" + item + ".timer"])
    print("Installed " + opts["kit_name"] + " at " + str(dest) + (
        "; selected timers explicitly enabled" if opts["enable"] else "; units NOT enabled"
    ))
    if legacy:
        print("Edit private config before enabling timers. Heal remains dry-run; project requires --repo.")


def local_status(opts, uninstall=False, apply=False):
    if os.getuid() == 0:
        raise Refusal("Never manage installations as root")
    dest, unitdir = targets(opts)
    records = installed(opts, dest)
    retained = {}
    for key, expected in records.items():
        path = record_path(key, dest, unitdir)
        try:
            inspect(path)
            state = "missing" if not path.exists() else (
                "unchanged" if digest(path.read_bytes()) == expected else "modified"
            )
        except Refusal:
            state = "unsafe"
        print(key + ": " + state)
        if uninstall and apply and state == "unchanged":
            if key.startswith("unit/") and key.endswith(".timer"):
                run(["systemctl", "--user", "disable", "--now", path.name])
            path.unlink()
        elif state != "missing":
            retained[key] = expected
    if uninstall and apply and records:
        if retained:
            atomic(dest / MANIFEST, encoded({"settings": recorded_settings(opts), "files": retained}),
                   replace=True)
        else:
            (dest / MANIFEST).unlink()
        run(["systemctl", "--user", "daemon-reload"])
    if not records:
        print("No tracked installation")
    if uninstall and not apply:
        print("Dry-run only; --apply removes only recorded unchanged files")


def ssh_options(opts, trust=None):
    result = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
              "-o", "ForwardAgent=no", "-o", "PasswordAuthentication=no",
              "-o", "KbdInteractiveAuthentication=no", "-o", "ConnectTimeout=10"]
    if trust:
        result += ["-o", "UserKnownHostsFile=" + str(trust), "-o", "GlobalKnownHostsFile=/dev/null"]
    return result


def trusted(opts, args):
    if not opts["host"]:
        raise Refusal("--host user@host is required")
    if not args.trust_host_key:
        if args.expected_fingerprint:
            raise Refusal("--expected-fingerprint also requires --trust-host-key")
        return None
    fingerprint = args.expected_fingerprint
    if not fingerprint or not re.fullmatch(r"SHA256:[A-Za-z0-9+/]{43}", fingerprint):
        raise Refusal("Trust requires an independently verified SHA256 fingerprint")
    host = opts["host"].split("@")[1]
    try:
        scan = run(["ssh-keyscan", "-T", "5", host], capture_output=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Refusal("Host key acquisition failed; verify identity out-of-band") from exc
    matches = []
    for line in scan.splitlines():
        if line.startswith(b"#") or not line.strip():
            continue
        fields = line.split()
        if len(fields) != 3 or fields[0].decode() != host:
            continue
        try:
            key = base64.b64decode(fields[2], validate=True)
        except ValueError:
            continue
        calculated = "SHA256:" + base64.b64encode(hashlib.sha256(key).digest()).decode().rstrip("=")
        if calculated == fingerprint:
            matches.append(line + b"\n")
    if not matches:
        raise Refusal("Host fingerprint mismatch; verify identity out-of-band")
    directory = Path.home() / ".local/state/fleetctl"
    mkdir(directory)
    inspect(directory, directory=True, private=True)
    path = directory / ("known-hosts-" + secrets.token_hex(12))
    atomic(path, b"".join(matches))
    # OpenSSH independently parses and fingerprints the selected key.
    try:
        checked = run(["ssh-keygen", "-lf", str(path), "-E", "sha256"], capture_output=True)
        if fingerprint not in checked.stdout.decode().split():
            raise Refusal("OpenSSH fingerprint mismatch")
    except (OSError, subprocess.CalledProcessError, Refusal, UnicodeError):
        path.unlink()
        raise
    return path


def remote(opts, trust, argv, **kwargs):
    return run(["ssh"] + ssh_options(opts, trust) + [opts["host"], shlex.join(argv)], **kwargs)


# Only fixed code is sent for the initial check; settings travel as JSON data.
PREFLIGHT = """import json,os,pathlib
if os.getuid()==0: raise SystemExit('Remote root refused')
print(json.dumps({'home':str(pathlib.Path.home()),'uid':os.getuid()}))
"""
STAGE = """import os,pathlib,secrets,stat
if os.getuid()==0: raise SystemExit('Remote root refused')
p=pathlib.Path.home()
for ancestor in (p,)+tuple(p.parents):
 if ancestor.is_symlink(): raise SystemExit('Unsafe home symlink')
 if ancestor.stat().st_mode&0o022: raise SystemExit('Unsafe home permissions')
if p.stat().st_uid!=os.getuid(): raise SystemExit('Unsafe home ownership')
for part in ('.local','state','fleetctl','staging'):
 p=p/part
 if p.is_symlink(): raise SystemExit('Unsafe staging symlink')
 if not p.exists(): p.mkdir(mode=0o700)
 s=p.stat()
 mask=0o077 if part in ('fleetctl','staging') else 0o022
 if s.st_uid!=os.getuid() or s.st_mode&mask: raise SystemExit('Unsafe staging permissions')
p=p/secrets.token_hex(16);p.mkdir(mode=0o700);print(p)
"""
BOOTSTRAP = """import hashlib,os,pathlib,runpy,sys
if os.getuid()==0: raise SystemExit('Remote root refused')
p=pathlib.Path(sys.argv[1])
if p.is_symlink() or p.stat().st_uid!=os.getuid() or p.stat().st_mode&0o077: raise SystemExit('Unsafe stage')
f=p/'fleetctl.py'
if f.is_symlink() or not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=sys.argv[2]: raise SystemExit('Controller checksum mismatch')
sys.argv=[str(f),'_receive',str(p),sys.argv[3]]
runpy.run_path(str(f),run_name='__main__')
"""
SEAL = """import os,pathlib,sys
if os.getuid()==0: raise SystemExit('Remote root refused')
p=pathlib.Path(sys.argv[1])
if p.is_symlink() or p.stat().st_uid!=os.getuid() or p.stat().st_mode&0o077: raise SystemExit('Unsafe stage')
for f in p.iterdir():
 if f.is_symlink() or not f.is_file() or f.stat().st_uid!=os.getuid(): raise SystemExit('Unsafe staging entry')
 f.chmod(0o600)
"""
ACTION = """import hashlib,os,sys
if os.getuid()==0: raise SystemExit('Remote root refused')
code=sys.stdin.buffer.read()
if hashlib.sha256(code).hexdigest()!=sys.argv[1]: raise SystemExit('Controller checksum mismatch')
sys.argv=['fleetctl.py']+sys.argv[2:]
exec(compile(code,'fleetctl.py','exec'),{'__name__':'__main__','__file__':'fleetctl.py'})
"""


def connection(opts, trust):
    try:
        reply = remote(opts, trust, ["python3", "-c", PREFLIGHT], capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise Refusal("SSH verification failed. Verify the host identity out-of-band and provision trusted keys; no trust changes made.") from exc
    data = load_json(reply.stdout)
    if not isinstance(data, dict) or data.get("uid") == 0:
        raise Refusal("Remote root refused")
    path_text(data.get("home"))
    return data


def deploy(opts, args, source):
    validate_runtime(source / "config", opts, required=opts["enable"])
    payload = bundle(source, opts)
    hashes = {key: digest(data) for key, data in payload.items()}
    print(json.dumps({"source_manifest": hashes}, sort_keys=True, indent=2))
    if not args.apply:
        print("Dry-run only; no network, files, or services changed")
        return
    trust = trusted(opts, args)
    stage = None
    try:
        info = connection(opts, trust)
        stage = remote(opts, trust, ["python3", "-c", STAGE], capture_output=True).stdout.decode().strip()
        path_text(stage)
        stagepath = Path(stage)
        if stagepath.parent != Path(info["home"]) / ".local/state/fleetctl/staging" or not re.fullmatch(
            r"[0-9a-f]{32}", stagepath.name
        ):
            raise Refusal("Unsafe remote staging response")
        request = encoded({"settings": opts, "files": hashes})
        # No local archive or scratch copy: scp exact source files only.
        for key in payload:
            destination = stage + "/" + key.replace("/", "__")
            run(["scp"] + ssh_options(opts, trust) + [
                str(source / key), opts["host"] + ":" + destination
            ])
        remote(opts, trust, ["python3", "-c",
                            "import os,pathlib,sys;p=pathlib.Path(sys.argv[1]);"
                            "f=os.open(p/'request.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);"
                            "os.write(f,sys.stdin.buffer.read());os.close(f)", stage],
               input=request, capture_output=True)
        remote(opts, trust, ["python3", "-c", SEAL, stage], capture_output=True)
        remote(opts, trust, ["python3", "-c", BOOTSTRAP, stage,
                            hashes["fleetctl.py"], digest(request)])
    finally:
        if trust:
            trust.unlink()
        # Verified receiver removes its own staging files. Failures leave a private
        # stage for inspection rather than executing recursive cleanup remotely.


def receive(stage, expected):
    if os.getuid() == 0:
        raise Refusal("Remote root refused")
    inspect(stage, directory=True, private=True)
    request = read_private(stage / "request.json")
    if digest(request) != expected:
        raise Refusal("Request checksum mismatch")
    data = load_json(request)
    if not isinstance(data, dict) or set(data) != {"settings", "files"}:
        raise Refusal("Invalid staging request")
    opts = settings(data["settings"])
    hashes = data["files"]
    allow = set(PUBLIC) | {"config/" + p for p in opts["include_config"]}
    if not isinstance(hashes, dict) or set(hashes) != allow:
        raise Refusal("Unknown or missing bundle entries")
    expected_names = {key.replace("/", "__") for key in hashes} | {"request.json"}
    if {p.name for p in stage.iterdir()} != expected_names:
        raise Refusal("Unknown staging entries")
    payload = {}
    for key, expected_hash in hashes.items():
        path = stage / key.replace("/", "__")
        inspect(path)
        if path.stat().st_mode & 0o022:
            raise Refusal("Writable staging file")
        content = path.read_bytes()
        if digest(content) != expected_hash:
            raise Refusal("Bundle checksum mismatch: " + key)
        payload[key] = content
    # Validate transferred runtime data without executing any bundle code.
    validate_runtime(stage / "absent-config", opts, required=False, supplied={
        filename: payload["config/" + filename] for filename in opts["include_config"]
    })
    install(opts, payload)
    for path in stage.iterdir():
        path.unlink()
    stage.rmdir()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--userconfig")
    subs = result.add_subparsers(dest="command", required=True)
    docs = subs.add_parser("docs", help="local-only documentation export and knowledge index")
    docs.add_argument("arguments", nargs=argparse.REMAINDER)
    for command in ("init", "check", "connect", "deploy", "status", "uninstall", "_install"):
        sub = subs.add_parser(command)
        sub.add_argument("--userconfig", default=argparse.SUPPRESS)
        for key in ("kit_name", "unit_prefix", "install_dir", "role", "hub_label",
                    "client_label", "node_name", "repo", "host"):
            sub.add_argument("--" + key.replace("_", "-"), default=argparse.SUPPRESS)
        for flag in ("send", "enable"):
            sub.add_argument("--" + flag, action="store_true", default=argparse.SUPPRESS)
        sub.add_argument("--include-config", action="append", default=argparse.SUPPRESS)
        sub.add_argument("--apply", action="store_true")
        sub.add_argument("--source", default=str(ROOT))
        sub.add_argument("--trust-host-key", action="store_true")
        sub.add_argument("--expected-fingerprint")
        if command == "init":
            sub.add_argument("--output", default="fleetctl.json")
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv and argv[0] == "docs":
            sys.path.insert(0, str(ROOT / "src"))
            import docs_publish
            return docs_publish.main(argv[1:])
        if argv and argv[0] == "_receive":
            if len(argv) != 3:
                raise Refusal("Invalid receiver arguments")
            receive(Path(argv[1]), argv[2])
            return 0
        args = parser().parse_args(argv)
        raw = {}
        if args.userconfig:
            raw = load_json(read_private(Path(args.userconfig)))
        if not isinstance(raw, dict):
            raise Refusal("Userconfig must be a JSON object")
        raw.update({key: value for key, value in vars(args).items() if key in DEFAULTS})
        opts = settings(raw)
        source = Path(args.source).absolute()
        if args.command == "init":
            output = Path(args.output).absolute()
            inspect(output)
            atomic(output, encoded(opts))
            print("Created private userconfig; no installation or services changed")
        elif args.command == "check":
            validate_runtime(source / "config", opts, required=True)
            print("Configuration valid; no network or services changed")
        elif args.command == "deploy":
            deploy(opts, args, source)
        elif args.command == "_install":
            # Legacy local wrapper: install inert examples, never enable.
            if opts["enable"]:
                raise Refusal("Use deploy --apply --enable for explicit activation")
            install(opts, bundle(source, opts), legacy=True)
        elif args.command in ("status", "uninstall") and not opts["host"]:
            local_status(opts, uninstall=args.command == "uninstall", apply=args.apply)
        else:
            if args.command == "connect":
                validate_runtime(source / "config", opts)
            trust = trusted(opts, args)
            try:
                info = connection(opts, trust)
                if args.command == "connect":
                    print("Verified unprivileged SSH connection")
                else:
                    # Use this trusted controller, never execute a possibly modified
                    # installed script. Status still works after partial uninstall.
                    code = Path(__file__).read_bytes()
                    argv_remote = ["python3", "-c", ACTION, digest(code), args.command]
                    argv_remote += ["--" + key.replace("_", "-") + "=" + str(value)
                                    for key, value in opts.items()
                                    if isinstance(value, str)]
                    for key in ("send", "enable"):
                        if opts[key]:
                            argv_remote.append("--" + key)
                    for item in opts["include_config"]:
                        argv_remote += ["--include-config", item]
                    if args.apply:
                        argv_remote.append("--apply")
                    # Do not recursively SSH from the remote status command.
                    argv_remote = [a for a in argv_remote if not a.startswith("--host=")]
                    remote(opts, trust, argv_remote, input=code)
            finally:
                if trust:
                    trust.unlink()
        return 0
    except (Refusal, OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        print("fleetctl: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
