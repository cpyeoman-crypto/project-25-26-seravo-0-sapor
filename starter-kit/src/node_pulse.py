#!/usr/bin/env python3
"""Lightweight per-node pulse for every fleet client, current and future.

Collects local vitals (uptime, load, memory, disks, failed systemd units,
docker containers, mesh/overlay status, temperatures), writes a
machine-readable snapshot that any local tool or future LLM can consume, and
pushes updates through the kit's single ntfy delivery path — alerts fire only
on state transitions, plus one low-priority daily digest.

Standard library only, so a bare Python 3 (Linux or Windows) is the only
requirement. Every collector degrades gracefully: a probe that fails reports
null instead of aborting the pulse.

Safe by default: with no topic configured, or with NTFY_DRY_RUN=1, messages
are printed and nothing is sent. Configure NODE_NTFY_TOPIC (or reuse
NTFY_TOPIC) privately in config/fleet.env.

Snapshot: state/node/node_status.json          (schema fleet-kit.node_status/1)
History:  state/node/node_status_history.jsonl (capped)
"""
import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import ntfy_notify

SCHEMA = "fleet-kit.node_status/1"
HISTORY_MAX_LINES = 1000

HOME = Path.home()

# Default alert thresholds; override via env or config/fleet.env.
DISK_ALERT_PCT = 90
MEM_AVAILABLE_ALERT_PCT = 5
LOAD_PER_CPU_FACTOR = 2.0


def state_dir():
    return Path(ntfy_notify.setting("NODE_STATE_DIR", "state/node"))


def status_path():
    return state_dir() / "node_status.json"


def history_path():
    return state_dir() / "node_status_history.jsonl"


def pulse_state_path():
    return state_dir() / "node_pulse_state.json"


def setting(name, default=None):
    return ntfy_notify.setting(name, default)


def hostname():
    return socket.gethostname().split(".")[0].lower()


def node_topic():
    """This node's private topic; empty means dry-run printing only."""
    return setting("NODE_NTFY_TOPIC") or setting("NTFY_TOPIC") or ""


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(probe):
    try:
        return probe()
    except Exception:
        return None


def _run(command, timeout=15):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or str(result.returncode))
    return result.stdout


# --- collectors ----------------------------------------------------------------

def uptime_seconds():
    if sys.platform == "win32":
        import ctypes
        return int(ctypes.windll.kernel32.GetTickCount64() / 1000)
    return int(float(Path("/proc/uptime").read_text().split()[0]))


def load_average():
    load1, load5, load15 = os.getloadavg()
    return {"1m": round(load1, 2), "5m": round(load5, 2), "15m": round(load15, 2)}


def memory():
    if sys.platform == "win32":
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise RuntimeError("GlobalMemoryStatusEx failed")
        total, available = status.ullTotalPhys, status.ullAvailPhys
    else:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            values[key] = int(rest.split()[0]) * 1024
        total, available = values["MemTotal"], values["MemAvailable"]
    return {
        "total_bytes": total,
        "available_bytes": available,
        "available_pct": round(available / total * 100, 1),
    }


def disks():
    if sys.platform == "win32":
        paths = {os.environ.get("SystemDrive", "C:") + "\\"}
    else:
        paths = {"/", str(HOME)}
    seen, out = set(), []
    for path in sorted(paths):
        usage = _safe(lambda p=path: shutil.disk_usage(p))
        if not usage or usage.total in seen:
            continue
        seen.add(usage.total)
        out.append({
            "path": path,
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "used_pct": round(usage.used / usage.total * 100, 1),
        })
    return out


def failed_units():
    if sys.platform == "win32":
        return None
    output = _run(["systemctl", "--failed", "--plain", "--no-legend", "--full"])
    units = [line.split()[0] for line in output.splitlines() if line.strip()]
    return [unit.lstrip("●* ") for unit in units]


def docker_containers():
    output = _run(["docker", "ps", "-a", "--format", "{{json .}}"], timeout=20)
    containers = []
    for line in output.splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        containers.append({
            "name": raw.get("Names"),
            "image": raw.get("Image"),
            "state": raw.get("State"),
            "status": raw.get("Status"),
        })
    return containers


def mesh_status():
    """Encrypted-overlay membership, when the local mesh CLI is present."""
    status = json.loads(_run(["tailscale", "status", "--json"], timeout=20))
    self_node = status.get("Self") or {}
    peers = [p for p in (status.get("Peer") or {}).values() if isinstance(p, dict)]
    return {
        "self_online": bool(self_node.get("Online")),
        "peers_online": sum(1 for p in peers if p.get("Online")),
        "peers_total": len(peers),
    }


def temperatures():
    if sys.platform == "win32":
        return None
    readings = {}
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        kind = _safe(lambda z=zone: (z / "type").read_text().strip())
        millis = _safe(lambda z=zone: int((z / "temp").read_text().strip()))
        if kind and millis is not None:
            readings[kind] = round(millis / 1000, 1)
    return readings or None


def collect():
    uname = platform.uname()
    return {
        "schema": SCHEMA,
        "host": hostname(),
        "timestamp": now_utc(),
        "platform": {"system": uname.system, "release": uname.release, "machine": uname.machine},
        "uptime_seconds": _safe(uptime_seconds),
        "load": _safe(load_average),
        "cpu_count": os.cpu_count(),
        "memory": _safe(memory),
        "disks": _safe(disks) or [],
        "failed_units": _safe(failed_units),
        "docker": _safe(docker_containers),
        "mesh": _safe(mesh_status),
        "temperatures_c": _safe(temperatures),
    }


# --- issue evaluation ----------------------------------------------------------

def evaluate_issues(snapshot):
    """Return {stable_key: human message} for everything currently wrong."""
    issues = {}
    disk_pct = float(setting("NODE_DISK_ALERT_PCT", DISK_ALERT_PCT))
    for disk in snapshot["disks"]:
        if disk["used_pct"] >= disk_pct:
            issues[f"disk:{disk['path']}"] = f"disk {disk['path']} at {disk['used_pct']}% used"
    mem = snapshot.get("memory")
    mem_pct = float(setting("NODE_MEM_AVAILABLE_ALERT_PCT", MEM_AVAILABLE_ALERT_PCT))
    if mem and mem["available_pct"] <= mem_pct:
        issues["memory"] = f"only {mem['available_pct']}% memory available"
    load, cpus = snapshot.get("load"), snapshot.get("cpu_count")
    factor = float(setting("NODE_LOAD_PER_CPU_FACTOR", LOAD_PER_CPU_FACTOR))
    if load and cpus and load["5m"] > factor * cpus:
        issues["load"] = f"5m load {load['5m']} above {factor}x{cpus} CPUs"
    for unit in snapshot.get("failed_units") or []:
        issues[f"unit:{unit}"] = f"systemd unit {unit} failed"
    for container in snapshot.get("docker") or []:
        state = (container.get("state") or "").lower()
        status = (container.get("status") or "").lower()
        if state in ("restarting", "dead") or "unhealthy" in status:
            issues[f"docker:{container['name']}"] = (
                f"container {container['name']} {container.get('status') or state}"
            )
    mesh = snapshot.get("mesh")
    if mesh and not mesh["self_online"]:
        issues["mesh"] = "the overlay reports this node offline"
    return issues


# --- state, snapshot, and history files ----------------------------------------

def _write_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load_pulse_state():
    try:
        state = json.loads(pulse_state_path().read_text(encoding="utf-8"))
        if isinstance(state, dict):
            return {"issues": state.get("issues") or {}, "digest_date": state.get("digest_date")}
    except (OSError, ValueError):
        pass
    return {"issues": {}, "digest_date": None}


def _resolved_issue_message(key, value):
    """Read current/legacy pulse state into a useful recovery message."""
    if isinstance(value, dict) and isinstance(value.get("message"), str):
        return value["message"]
    if isinstance(value, str) and not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        return value
    if key.startswith("unit:"):
        return f"systemd unit {key[len('unit:'):]} failed"
    if key.startswith("disk:"):
        return f"disk {key[len('disk:'):]} crossed its usage threshold"
    if key.startswith("docker:"):
        return f"container {key[len('docker:'):]} was unhealthy"
    return {
        "memory": "available memory fell below its threshold",
        "load": "5-minute system load exceeded its threshold",
        "mesh": "the overlay reported this node offline",
    }.get(key, f"{key} issue cleared")


def _next_issue_state(issues, previous, now):
    next_state = {}
    for key, message in issues.items():
        old = previous.get(key)
        since = old.get("since") if isinstance(old, dict) else old
        if not isinstance(since, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T", since):
            since = now
        next_state[key] = {"message": message, "since": since}
    return next_state


def save_snapshot(snapshot, issues):
    snapshot = dict(snapshot, issues=[
        {"key": key, "message": message} for key, message in sorted(issues.items())
    ], ok=not issues)
    _write_atomic(status_path(), json.dumps(snapshot, indent=2) + "\n")
    try:
        lines = history_path().read_text(encoding="utf-8").splitlines() if history_path().exists() else []
    except OSError:
        lines = []
    lines.append(json.dumps(snapshot, separators=(",", ":")))
    _write_atomic(history_path(), "\n".join(lines[-HISTORY_MAX_LINES:]) + "\n")
    return snapshot


# --- reporting -----------------------------------------------------------------

def digest_body(snapshot, issues):
    lines = []
    if snapshot.get("uptime_seconds"):
        lines.append(f"- **Uptime** `{snapshot['uptime_seconds'] // 86400}d "
                     f"{snapshot['uptime_seconds'] % 86400 // 3600}h`")
    if snapshot.get("load"):
        lines.append(f"- **Load** `{snapshot['load']['1m']} / {snapshot['load']['5m']} "
                     f"/ {snapshot['load']['15m']}` ({snapshot.get('cpu_count')} CPUs)")
    if snapshot.get("memory"):
        lines.append(f"- **Memory free** `{snapshot['memory']['available_pct']}%`")
    for disk in snapshot["disks"]:
        lines.append(f"- **Disk {disk['path']}** `{disk['used_pct']}% used`")
    docker = snapshot.get("docker")
    if docker is not None:
        running = sum(1 for c in docker if (c.get("state") or "").lower() == "running")
        lines.append(f"- **Docker** `{running}/{len(docker)} running`")
    mesh = snapshot.get("mesh")
    if mesh:
        lines.append(f"- **Overlay** `{'online' if mesh['self_online'] else 'OFFLINE'}, "
                     f"{mesh['peers_online']}/{mesh['peers_total']} peers`")
    state_line = "all clear" if not issues else f"{len(issues)} open issue(s)"
    return f"{state_line}\n\n" + "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-notify", action="store_true",
                        help="collect and write the snapshot without any ntfy push")
    parser.add_argument("--print", dest="print_snapshot", action="store_true",
                        help="dump the snapshot JSON to stdout")
    args = parser.parse_args(argv)

    snapshot = collect()
    issues = evaluate_issues(snapshot)
    state = load_pulse_state()
    snapshot = save_snapshot(snapshot, issues)
    if args.print_snapshot:
        print(json.dumps(snapshot, indent=2))

    delivered = True
    if not args.no_notify:
        topic = node_topic()
        new = {k: v for k, v in issues.items() if k not in state["issues"]}
        resolved = {k: v for k, v in state["issues"].items() if k not in issues}
        if new:
            delivered &= ntfy_notify.send(
                "pulse_alert", "\n".join(f"- {message}" for message in new.values()),
                headline=f"NODE ALERT · {hostname()}", topic_name=topic)
        if resolved:
            delivered &= ntfy_notify.send(
                "pulse_recovered",
                "\n".join(f"- resolved: {_resolved_issue_message(key, value)}"
                          for key, value in resolved.items()),
                headline=f"NODE RECOVERED · {hostname()}", topic_name=topic)
        today = now_utc()[:10]
        if setting("NODE_PULSE_DIGEST", "1") != "0" and state["digest_date"] != today:
            ntfy_notify.send(
                "pulse_digest", digest_body(snapshot, issues),
                headline=f"NODE PULSE · {hostname()}", topic_name=topic)
            state["digest_date"] = today  # spooled messages still deliver later

    state["issues"] = _next_issue_state(issues, state["issues"], now_utc())
    _write_atomic(pulse_state_path(), json.dumps(state, indent=2) + "\n")
    print(f"[+] Node pulse complete: {len(issues)} issue(s); snapshot at {status_path()}")
    return 0 if delivered else 1


if __name__ == "__main__":
    raise SystemExit(main())
