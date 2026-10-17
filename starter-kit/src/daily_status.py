#!/usr/bin/env python3
"""Compose and push the once-a-day status report from local metrics and fleet state.

  python3 src/daily_status.py            # prints the report (dry-run)
  python3 src/daily_status.py --send     # pushes it through ntfy
"""
import argparse
import json
import os
import platform
import shutil
from pathlib import Path

import ntfy_notify as ntfy

STATE_FILE = Path(__file__).resolve().parent.parent / "state" / "fleet_status.json"
DISK_WARN_PCT = 90


def host_metrics():
    total, used, free = shutil.disk_usage("/")
    load = os.getloadavg()
    mem_pct = None
    try:
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            info[key] = int(rest.split()[0])
        mem_pct = 100 * (1 - info["MemAvailable"] / info["MemTotal"])
    except (OSError, ValueError, KeyError, IndexError):
        pass
    return {
        "kernel": platform.release(),
        "load": load,
        "cores": os.cpu_count() or 1,
        "mem_pct": mem_pct,
        "disk_pct": 100 * used / total,
        "disk_free_gb": free / 1e9,
    }


def build_report(metrics, state):
    warnings = []
    if metrics["disk_pct"] >= DISK_WARN_PCT:
        warnings.append(f"💽 Disk is {metrics['disk_pct']:.0f}% full")
    down = sorted(name for name, entry in state.items() if not entry.get("up"))
    stale = sorted(name for name, entry in state.items() if entry.get("stale"))
    if down:
        warnings.append("🔴 Down: " + ", ".join(down))
    if stale:
        warnings.append("🔭 Not reporting: " + ", ".join(stale))
    verdict = (
        "✅ **All nodes green**" if not warnings
        else f"⚠️ **{len(warnings)} item(s) need attention**\n\n" + ntfy.bullets(warnings)
    )
    host_lines = [
        f"Kernel `{metrics['kernel']}`",
        f"Load `{metrics['load'][0]:.2f} {metrics['load'][1]:.2f} {metrics['load'][2]:.2f}` on {metrics['cores']} cores",
        f"Disk / {ntfy.bar(metrics['disk_pct'])} **{metrics['disk_pct']:.0f}%** · {metrics['disk_free_gb']:.0f} GB free",
    ]
    if metrics["mem_pct"] is not None:
        host_lines.insert(2, f"Memory {ntfy.bar(metrics['mem_pct'])} **{metrics['mem_pct']:.0f}%**")
    sections = [verdict, "### 🖥️ Hub\n" + ntfy.bullets(host_lines)]
    if state:
        rows = [f"{'🟢' if e.get('up') else '🔴'} **{name}** · {e.get('role', '')} · {e.get('channel') or 'unreachable'}"
                for name, e in sorted(state.items())]
        sections.append(f"### 🛰️ Fleet · {len(state) - len(down)}/{len(state)} reachable\n" + ntfy.bullets(rows))
    headline = "DAILY STATUS · " + ("ALL GREEN" if not warnings else "ATTENTION")
    return headline, "\n\n".join(sections), bool(warnings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default=str(STATE_FILE))
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    try:
        state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    headline, body, attention = build_report(host_metrics(), state)
    if args.send:
        ntfy.send("daily", body, headline=headline, priority="high" if attention else "default")
    else:
        print(ntfy.compose("daily", headline, body))


if __name__ == "__main__":
    main()
