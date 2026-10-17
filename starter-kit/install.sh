#!/usr/bin/env bash
# Installs the kit for the current user. Read it first. Nothing runs as root.
# Usage:
#   ./install.sh            copy files and install timers for a HUB (poll + daily; heal stays dry-run)
#   ./install.sh client     install the heartbeat timer only, for an edge client
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
ROLE="${1:-hub}"
if [ "$#" -gt 0 ]; then shift; fi
exec python3 "$SRC/fleetctl.py" _install --role "$ROLE" --send "$@"
