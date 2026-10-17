#!/usr/bin/env python3
"""Find a client by hardware identity first, addresses last.

Order of trust:
  1. LAN neighbour table (live evidence tying a MAC address to an IP address).
  2. Mesh overlay peer list (live, matched on the node's mesh name).
  3. Last known address from the manifest (stale, lowest trust, flagged as such).

A node that cannot be resolved is reported as unresolved. Callers must not send
work to it.
"""
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAC_PATTERN = re.compile(r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}")


@dataclass(frozen=True)
class Resolution:
    address: str
    channel: str  # "lan" | "mesh" | "last-known"


def normalize_mac(value):
    """Return aa:bb:cc:dd:ee:ff or None."""
    if not value:
        return None
    compact = re.sub(r"[^0-9a-fA-F]", "", str(value))
    if len(compact) != 12:
        return None
    return ":".join(compact[i:i + 2] for i in range(0, 12, 2)).lower()


def parse_neighbor_table(output):
    """Parse `ip neigh show` output into {mac: [ip, ...]}, ignoring failed entries."""
    table = {}
    for line in output.splitlines():
        if "FAILED" in line or "INCOMPLETE" in line:
            continue
        match = MAC_PATTERN.search(line)
        fields = line.split()
        if not match or not fields:
            continue
        mac = normalize_mac(match.group(0))
        if mac:
            table.setdefault(mac, []).append(fields[0])
    return table


def read_neighbors(runner=subprocess.run):
    if not shutil.which("ip"):
        return {}
    result = runner(["ip", "neigh", "show"], capture_output=True, text=True, timeout=10, check=False)
    return parse_neighbor_table(result.stdout)


def read_mesh_peers(runner=subprocess.run):
    """Return {mesh_name: address} from `tailscale status --json`; {} when unavailable.

    Replace this function if you use a different mesh overlay.
    """
    if not shutil.which("tailscale"):
        return {}
    try:
        result = runner(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=15, check=True)
        data = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {}
    peers = {}
    for peer in list(data.get("Peer", {}).values()):
        addresses = peer.get("TailscaleIPs") or []
        if peer.get("Online") and addresses:
            peers[str(peer.get("HostName", "")).lower()] = addresses[0]
    return peers


def load_manifest(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("manifest needs a 'nodes' list")
    seen = set()
    for node in nodes:
        name = node.get("name")
        if not name or name in seen:
            raise ValueError(f"manifest node names must be present and unique: {name!r}")
        seen.add(name)
    return data


def resolve(node, neighbors, mesh_peers, probe):
    """Return a Resolution that answers `probe(address)`, or None.

    `probe` is a callable taking an address and returning True when reachable.
    """
    for mac in filter(None, (normalize_mac(m) for m in node.get("macs", []))):
        for address in neighbors.get(mac, []):
            if probe(address):
                return Resolution(address, "lan")
    mesh_name = str(node.get("mesh_name", "")).lower()
    if mesh_name and mesh_name in mesh_peers and probe(mesh_peers[mesh_name]):
        return Resolution(mesh_peers[mesh_name], "mesh")
    last_known = node.get("last_known_address")
    if last_known and probe(last_known):
        return Resolution(last_known, "last-known")
    return None
