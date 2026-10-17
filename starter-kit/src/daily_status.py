#!/usr/bin/env python3
"""Compose and push the once-a-day status report from local metrics and fleet state.

  python3 src/daily_status.py            # prints the report (dry-run)
  python3 src/daily_status.py --send     # pushes it through ntfy
"""
import argparse
import os
import platform
import shutil
import time
from pathlib import Path

import ntfy_notify as ntfy
import project_monitor
import resolver

STATE_FILE = Path(__file__).resolve().parent.parent / "state" / "fleet_status.json"
PROJECT_FILE = STATE_FILE.with_name("project_status.json")
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


def build_report(metrics, state, project=None, fleet_issue=None, now=None):
    now = time.time() if now is None else now
    warnings = []
    if fleet_issue:
        warnings.append(fleet_issue)
    if not state:
        warnings.append("Fleet monitoring evidence missing")
    elif any(not project_monitor.fresh(entry.get("checked_at"), now, 600) for entry in state.values()):
        warnings.append("Fleet monitoring evidence stale or invalid")
    if project is None:
        project = ("Project: monitoring evidence missing", True)
    if project[1]:
        warnings.append("Project maintenance needs attention")
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
    sections = [verdict, "### Project maintenance\n" + project[0],
                "### 🖥️ Hub\n" + ntfy.bullets(host_lines)]
    if state:
        rows = [f"{'🟢' if e.get('up') else '🔴'} **{name}** · {e.get('role', '')} · {e.get('channel') or 'unreachable'}"
                for name, e in sorted(state.items())]
        sections.append(f"### 🛰️ Fleet · {len(state) - len(down)}/{len(state)} reachable\n" + ntfy.bullets(rows))
    headline = "DAILY STATUS · " + ("ALL GREEN" if not warnings else "ATTENTION")
    return headline, "\n\n".join(sections), bool(warnings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default=str(STATE_FILE))
    parser.add_argument("--manifest", default=str(STATE_FILE.parent.parent / "config/fleet_manifest.json"))
    parser.add_argument("--project-state", default=str(PROJECT_FILE))
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()
    fleet_issue = None
    try:
        state = project_monitor.read_json(args.state)
        if not isinstance(state, dict) or any(
                not isinstance(entry, dict) or type(entry.get("up")) is not bool
                or type(entry.get("stale")) is not bool for entry in state.values()):
            raise ValueError("invalid fleet state")
        manifest = resolver.load_manifest(args.manifest)
        if set(state) != {node["name"] for node in manifest["nodes"]}:
            fleet_issue = "Fleet evidence does not cover configured nodes"
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        state = {}
        fleet_issue = "Fleet state or manifest missing or invalid"
    headline, body, attention = build_report(
        host_metrics(), state, project_monitor.summary(args.project_state), fleet_issue)
    if args.send:
        delivered = ntfy.send("daily", body, headline=headline, priority="high" if attention else "default")
        if not delivered:
            return 1
    else:
        print(ntfy.compose("daily", headline, body))
    return 1 if attention else 0


if __name__ == "__main__":
    raise SystemExit(main())
