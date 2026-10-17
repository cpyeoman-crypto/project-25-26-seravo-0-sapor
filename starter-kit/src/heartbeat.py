#!/usr/bin/env python3
"""Write this client's heartbeat as JSON, for the hub to collect.

Run from a timer on each client (every 5 minutes). The hub reads the file with
rsync, scp or a shared folder. The file holds health numbers only: no
credentials, no addresses.

  python3 src/heartbeat.py --name edge-scout-1 --out /tmp/edge-scout-1.json
"""
import argparse
import json
import os
import shutil
import time
from pathlib import Path


def collect(name):
    load = os.getloadavg()
    total, used, free = shutil.disk_usage("/")
    meminfo = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            meminfo[key] = int(rest.split()[0])
    except (OSError, ValueError, IndexError):
        pass
    mem_pct = None
    if meminfo.get("MemTotal"):
        mem_pct = round(100 * (1 - meminfo.get("MemAvailable", 0) / meminfo["MemTotal"]), 1)
    return {
        "name": name,
        "epoch": time.time(),
        "load1": round(load[0], 2),
        "cores": os.cpu_count(),
        "mem_pct": mem_pct,
        "disk_pct": round(100 * used / total, 1),
        "disk_free_gb": round(free / 1e9, 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="the node's name in the manifest")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(collect(args.name)), encoding="utf-8")
    tmp.replace(out)


if __name__ == "__main__":
    main()
