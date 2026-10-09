#!/bin/bash
# Bring the app up to date: back up the database, fetch the new version, update the packages and the
# database, and restart the background app if it is running.
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -x .venv/bin/python ] || { echo "Run ./deploy/macos/install.sh first."; exit 1; }
if [ -f data/cutting_patterns.db ]; then .venv/bin/python -m app backup --keep 0; fi
git pull --ff-only
.venv/bin/python -m pip install --quiet -r requirements.txt
.venv/bin/python -m app migrate
if launchctl print "gui/$(id -u)/local.sawing-patterns" >/dev/null 2>&1; then
  launchctl kickstart -k "gui/$(id -u)/local.sawing-patterns"
  echo "Updated and restarted."
else
  echo "Updated. Start it with .venv/bin/python -m app"
fi
