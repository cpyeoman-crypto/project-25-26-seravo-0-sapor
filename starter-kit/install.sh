#!/usr/bin/env bash
# Installs the kit for the current user. Read it first. Nothing runs as root.
# Usage:
#   ./install.sh            copy files and install timers for a HUB (poll + daily; heal stays dry-run)
#   ./install.sh client     install the heartbeat timer only, for an edge client
set -euo pipefail

ROLE="${1:-hub}"
DEST="$HOME/fleet-kit"
SRC="$(cd "$(dirname "$0")" && pwd)"

mkdir -p "$DEST"
if [ "$SRC" != "$DEST" ]; then
  cp -r "$SRC"/src "$SRC"/config "$SRC"/systemd "$DEST"/
  cp "$SRC/SCRIPT_GUIDE.txt" "$DEST/"
fi
mkdir -p "$DEST/state/heartbeats"

if [ ! -f "$DEST/config/fleet.env" ]; then
  cp "$DEST/config/fleet.env.example" "$DEST/config/fleet.env"
  chmod 600 "$DEST/config/fleet.env"
  echo "Created $DEST/config/fleet.env. Fill in NTFY_TOPIC before enabling timers."
fi
if [ "$ROLE" = "hub" ] && [ ! -f "$DEST/config/fleet_manifest.json" ]; then
  cp "$DEST/config/fleet_manifest.example.json" "$DEST/config/fleet_manifest.json"
  echo "Created $DEST/config/fleet_manifest.json from the example. Edit it before enabling timers."
fi

UNITS="$HOME/.config/systemd/user"
mkdir -p "$UNITS"
if [ "$ROLE" = "client" ]; then
  names=(fleet-heartbeat)
else
  names=(fleet-poll fleet-daily fleet-heal fleet-project)
fi
for n in "${names[@]}"; do
  cp "$DEST/systemd/$n.service" "$DEST/systemd/$n.timer" "$UNITS/"
done
systemctl --user daemon-reload
echo "Units installed but NOT enabled. After editing config, enable with:"
for n in "${names[@]}"; do echo "  systemctl --user enable --now $n.timer"; done
echo "To keep user timers running without a login session: loginctl enable-linger \$USER"
