#!/usr/bin/env bash
# Builds fleet-kit.zip from this folder (no state, no real config).
set -euo pipefail
cd "$(dirname "$0")"
python3 - <<'PY'
from pathlib import Path
import zipfile
import fleetctl

files = fleetctl.PUBLIC + (
    "README.md", "PROMPT_GUIDE.md", "INFORMATION_CHECKLIST.md", "SCRIPT_GUIDE.txt",
    "tests/test_kit.py", "tests/test_daily_status.py", "tests/test_project_monitor.py",
    "tests/test_runtime_validation.py", "tests/test_fleetctl.py",
) + tuple(
    "systemd/fleet-" + name + "." + ext
    for name in ("poll", "daily", "heal", "project", "heartbeat")
    for ext in ("service", "timer")
)
for filename in files:
    fleetctl.inspect(Path(filename), secure=False)
output = Path("fleet-kit.zip")
if output.is_symlink():
    raise SystemExit("Refusing symlink package output")
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for filename in files:
        archive.write(filename)
PY
echo "Built $(pwd)/fleet-kit.zip"
