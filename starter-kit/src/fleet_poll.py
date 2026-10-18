#!/usr/bin/env python3
"""Poll every node in the manifest and push an alert only when its state changes.

Run from a timer (every 2 to 5 minutes). Writes state/fleet_status.json, which
the daily report and any dashboard can read.

  python3 src/fleet_poll.py --manifest config/fleet_manifest.json            # dry-run
  python3 src/fleet_poll.py --manifest config/fleet_manifest.json --send     # push alerts

Heartbeat files (see heartbeat.py) are optional. If a node is reachable but its
heartbeat is older than `heartbeat_max_age_min`, a separate "online but not
reporting" alert fires, again on change only.
"""
import argparse
import json
import socket
import sys
import time
from pathlib import Path

import ntfy_notify as ntfy
import project_monitor
import resolver

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "fleet_status.json"
REMIND_AFTER_SECONDS = 24 * 3600


def tcp_probe(address, port, timeout=2.0):
    resolver.validate_address(address)
    try:
        with socket.create_connection((address, port), timeout=timeout):
            return True
    except OSError:
        return False


def load_state(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def heartbeat_age_minutes(heartbeat_dir, name, now):
    if not heartbeat_dir:
        return None
    path = Path(heartbeat_dir) / f"{name}.json"
    try:
        stamp = project_monitor.read_json(path).get("epoch")
    except (OSError, ValueError, TypeError, AttributeError, RecursionError):
        return None
    return (now - stamp) / 60.0 if project_monitor.fresh(stamp, now, float("inf")) else None


def poll_once(manifest, previous, neighbors, mesh_peers, probe_port, now):
    """Return (new_state, alerts). Pure function apart from the injected probes."""
    state, alerts = {}, []
    max_age = manifest.get("heartbeat_max_age_min", 15)
    hb_dir = manifest.get("heartbeat_dir")
    for node in manifest["nodes"]:
        name = node["name"]
        port = node.get("probe_port", 22)
        before = previous.get(name, {})
        found = resolver.resolve(node, neighbors, mesh_peers, lambda addr, p=port: probe_port(addr, p))
        up = found is not None
        entry = {
            "role": node.get("role", ""),
            "up": up,
            "channel": found.channel if found else None,
            "since": before.get("since", now) if before.get("up") == up else now,
            "notified": before.get("notified", now),
            "stale": False,
            "checked_at": now,
        }
        if up and before.get("up") is False:
            alerts.append(("node_up", name, node, f"{node.get('role', 'node')} is reachable again over **{found.channel}**."))
            entry["notified"] = now
        elif not up and before.get("up") is not False:
            if before:  # first run only seeds state
                alerts.append(("node_down", name, node, f"{node.get('role', 'node')} did not answer on LAN, mesh or last-known address."))
                entry["notified"] = now
        elif not up and now - before.get("notified", 0) >= REMIND_AFTER_SECONDS:
            hours = (now - entry["since"]) / 3600
            alerts.append(("node_down", name, node, f"Still down after {hours:.0f} h."))
            entry["notified"] = now
        age = heartbeat_age_minutes(hb_dir, name, now) if up else None
        if up and hb_dir and (age is None or age > max_age):
            entry["stale"] = True
            if not before.get("stale"):
                alerts.append(("stale", name, node, "Reachable, but heartbeat missing, invalid or stale."))
        state[name] = entry
    return state, alerts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--state", default=str(STATE_FILE))
    parser.add_argument("--send", action="store_true", help="push alerts (default: print only)")
    args = parser.parse_args(argv)

    manifest = resolver.load_manifest(args.manifest)
    previous = load_state(args.state)
    now = time.time()
    state, alerts = poll_once(
        manifest, previous, resolver.read_neighbors(), resolver.read_mesh_peers(), tcp_probe, now
    )
    delivery_failed = False
    for kind, name, node, text in alerts:
        details = [("Node", name), ("Role", node.get("role")), ("Wake required", node.get("wake_required", False))]
        if args.send:
            if not ntfy.send(kind, text, headline=f"{ntfy.STYLES[kind].label} · {name}", details=details):
                delivery_failed = True
        else:
            print(f"[dry-run alert] {kind}: {name}: {text}")
    save_state(args.state, state)
    up = sum(1 for entry in state.values() if entry["up"])
    print(f"[+] polled {len(state)} nodes, {up} up, {len(alerts)} state change(s)")
    return 1 if delivery_failed else 0


if __name__ == "__main__":
    sys.exit(main())
