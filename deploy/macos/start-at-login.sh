#!/bin/bash
# Run the app in the background whenever this Mac user is logged in, restart it if it stops, and
# back up the database every evening. Run again to change the options; ./deploy/macos/stop.sh undoes it.
#
#   ./deploy/macos/start-at-login.sh             only this Mac can open it (http://127.0.0.1:8000)
#   ./deploy/macos/start-at-login.sh --shared    other computers on the office network can open it too
#   options: --port 8000   --backup-time 19:00   --keep 30
set -euo pipefail
cd "$(dirname "$0")/../.."
APP_DIR="$(pwd)"
HOST="127.0.0.1"; PORT="8000"; BACKUP_TIME="19:00"; KEEP="30"
while [ $# -gt 0 ]; do
  case "$1" in
    --shared) HOST="0.0.0.0" ;;
    --port) PORT="$2"; shift ;;
    --backup-time) BACKUP_TIME="$2"; shift ;;
    --keep) KEEP="$2"; shift ;;
    *) echo "Unknown option $1"; exit 1 ;;
  esac
  shift
done
[ -x .venv/bin/python ] || { echo "Run ./deploy/macos/install.sh first."; exit 1; }
BACKUP_HOUR="${BACKUP_TIME%%:*}"; BACKUP_MINUTE="${BACKUP_TIME##*:}"

AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/SawingPatterns"
APP_LABEL="local.sawing-patterns"
BACKUP_LABEL="local.sawing-patterns.backup"
mkdir -p "$AGENTS" "$LOGS"
xml() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
PY="$(xml "$APP_DIR/.venv/bin/python")"
DIR="$(xml "$APP_DIR")"

cat > "$AGENTS/$APP_LABEL.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$APP_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string><string>-m</string><string>app</string>
    <string>--host</string><string>$HOST</string>
    <string>--port</string><string>$PORT</string>
    <string>--no-browser</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>$(xml "$LOGS/app.log")</string>
  <key>StandardErrorPath</key><string>$(xml "$LOGS/app.log")</string>
</dict>
</plist>
PLIST

cat > "$AGENTS/$BACKUP_LABEL.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$BACKUP_LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string><string>-m</string><string>app</string>
    <string>backup</string><string>--keep</string><string>$KEEP</string>
  </array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$((10#$BACKUP_HOUR))</integer><key>Minute</key><integer>$((10#$BACKUP_MINUTE))</integer></dict>
  <key>StandardOutPath</key><string>$(xml "$LOGS/backup.log")</string>
  <key>StandardErrorPath</key><string>$(xml "$LOGS/backup.log")</string>
</dict>
</plist>
PLIST

DOMAIN="gui/$(id -u)"
for label in "$APP_LABEL" "$BACKUP_LABEL"; do
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$AGENTS/$label.plist"
done

echo "The app now runs in the background and starts whenever you log in."
echo "  On this Mac:   http://127.0.0.1:$PORT"
if [ "$HOST" = "0.0.0.0" ]; then
  IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "<this Mac's address>")"
  echo "  In the office: http://$IP:$PORT"
  echo "  If macOS asks whether Python may accept incoming connections, click Allow."
fi
echo "  Backups:       every day at $BACKUP_TIME into $APP_DIR/backups (newest $KEEP kept)"
echo "  Log:           $LOGS/app.log"
