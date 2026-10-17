#!/usr/bin/env bash
# Builds fleet-kit.zip from this folder (no state, no real config).
set -euo pipefail
cd "$(dirname "$0")"
rm -f fleet-kit.zip
zip -r fleet-kit.zip README.md PROMPT_GUIDE.md INFORMATION_CHECKLIST.md requirements.txt install.sh \
  src config/*.example* systemd tests -x '*/__pycache__/*' '*.pyc'
echo "Built $(pwd)/fleet-kit.zip"
