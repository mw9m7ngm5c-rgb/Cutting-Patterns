#!/bin/bash
# Stop the background app and the daily backup, and stop them starting at login. Data is kept.
set -uo pipefail
AGENTS="$HOME/Library/LaunchAgents"
for label in local.sawing-patterns local.sawing-patterns.backup; do
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null
  rm -f "$AGENTS/$label.plist"
done
echo "Stopped. Start it again with ./deploy/macos/start-at-login.sh"
