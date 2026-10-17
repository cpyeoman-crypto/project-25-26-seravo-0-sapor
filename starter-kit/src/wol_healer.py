#!/usr/bin/env python3
"""Wake nodes that are down and marked `wake_required` in the manifest.

Dry-run unless --apply is given. Only nodes with wake_required=true and a MAC
address are ever woken. Mobile or travelling nodes must never be marked
wake_required unless a person asked for it.

  python3 src/wol_healer.py --manifest config/fleet_manifest.json            # dry-run
  python3 src/wol_healer.py --manifest config/fleet_manifest.json --apply
"""
import argparse
import json
import socket
from pathlib import Path

import ntfy_notify as ntfy
import resolver

STATE_FILE = Path(__file__).resolve().parent.parent / "state" / "fleet_status.json"


def magic_packet(mac):
    compact = resolver.normalize_mac(mac)
    if not compact:
        raise ValueError(f"invalid MAC address: {mac!r}")
    raw = bytes.fromhex(compact.replace(":", ""))
    return b"\xff" * 6 + raw * 16


def send_magic(mac, broadcast, port=9):
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))


def candidates(manifest, state):
    for node in manifest["nodes"]:
        if node.get("wake_required") and node.get("macs") and state.get(node["name"], {}).get("up") is False:
            yield node


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--state", default=str(STATE_FILE))
    parser.add_argument("--broadcast", default=None, help="LAN broadcast address, e.g. from your own address plan")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    manifest = resolver.load_manifest(args.manifest)
    try:
        state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    broadcast = args.broadcast or manifest.get("wol_broadcast")
    events = []
    for node in candidates(manifest, state):
        if args.apply:
            if not broadcast:
                raise SystemExit("--broadcast (or manifest wol_broadcast) is required with --apply")
            send_magic(node["macs"][0], broadcast)
            events.append(f"Wake-on-LAN sent to {node['name']}")
        else:
            events.append(f"[dry-run] would wake {node['name']}")
    for event in events:
        print(event)
    if events and args.apply:
        ntfy.send("healer", ntfy.bullets(events), headline=f"FLEET HEALING · {len(events)} wake packet(s)")


if __name__ == "__main__":
    main()
