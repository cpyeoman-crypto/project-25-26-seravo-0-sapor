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
import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAC_PATTERN = re.compile(r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}")


def validate_address(value):
    """Reject non-operational public placeholders before DNS or network access."""
    if (not isinstance(value, str) or not value or len(value) > 253
            or re.search(r"[<>/\s@]", value)
            or re.search(r"(?:^|[.:\-])x+(?:$|[.:\-])", value, re.I)
            or value == "CHANGE-ME"
            or not re.fullmatch(r"[a-zA-Z0-9_.:\-]+", value)):
        raise ValueError("invalid or placeholder address; configure a private runtime value")
    return value


@dataclass(frozen=True)
class Resolution:
    address: str
    channel: str  # "lan" | "mesh" | "last-known"


def normalize_mac(value):
    """Return a normalized six-octet MAC, or None for invalid/xx placeholders."""
    if not value:
        return None
    if not re.fullmatch(r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2})", str(value)):
        return None
    compact = re.sub(r"[:-]", "", str(value))
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
    if result.returncode:
        raise RuntimeError("LAN neighbor discovery failed")
    return parse_neighbor_table(result.stdout)


def read_mesh_peers(runner=subprocess.run):
    """Read `tailscale status --json`; {} if not installed, error if collection fails.

    Replace this function if you use a different mesh overlay.
    """
    if not shutil.which("tailscale"):
        return {}
    try:
        result = runner(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=15, check=True)
        data = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise RuntimeError("Mesh discovery failed") from exc
    peers = {}
    for peer in list(data.get("Peer", {}).values()):
        addresses = peer.get("TailscaleIPs") or []
        if peer.get("Online") and addresses:
            peers[str(peer.get("HostName", "")).lower()] = addresses[0]
    return peers


def load_manifest(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be an object")
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError("manifest needs a 'nodes' list")
    age = data.get("heartbeat_max_age_min", 15)
    if type(age) not in (int, float) or not math.isfinite(age) or age <= 0:
        raise ValueError("invalid heartbeat age limit")
    seen = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise ValueError("manifest nodes must be objects")
        name = node.get("name")
        if not isinstance(name, str) or not name or name in seen or Path(name).name != name or name in (".", ".."):
            raise ValueError("manifest node names must be safe and unique")
        seen.add(name)
        if not isinstance(node.get("macs", []), list) or any(normalize_mac(mac) is None for mac in node.get("macs", [])):
            raise ValueError("manifest MAC is invalid or a non-operational placeholder")
        for key in ("mesh_name", "last_known_address"):
            if node.get(key):
                validate_address(node[key])
        if type(node.get("probe_port", 22)) is not int or not 1 <= node.get("probe_port", 22) <= 65535:
            raise ValueError("invalid probe port")
    if data.get("wol_broadcast"):
        validate_address(data["wol_broadcast"])
    return data


def resolve(node, neighbors, mesh_peers, probe):
    """Return a Resolution that answers `probe(address)`, or None.

    `probe` is a callable taking an address and returning True when reachable.
    """
    for mac in filter(None, (normalize_mac(m) for m in node.get("macs", []))):
        for address in neighbors.get(mac, []):
            validate_address(address)
            if probe(address):
                return Resolution(address, "lan")
    mesh_name = str(node.get("mesh_name", "")).lower()
    if mesh_name and mesh_name in mesh_peers:
        address = validate_address(mesh_peers[mesh_name])
        if probe(address):
            return Resolution(address, "mesh")
    last_known = node.get("last_known_address")
    if last_known and probe(validate_address(last_known)):
        return Resolution(last_known, "last-known")
    return None
