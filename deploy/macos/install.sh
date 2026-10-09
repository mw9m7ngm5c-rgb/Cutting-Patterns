#!/bin/bash
# Install the sawing-pattern app on this Mac: a private Python environment, the packages it needs,
# and an empty database. Safe to run again; it only brings things up to date.
#
#   ./deploy/macos/install.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
APP_DIR="$(pwd)"

# The Python that comes with macOS (3.9) is too old. Use 3.11 or newer from python.org or Homebrew.
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.11 or newer is needed. Install it from https://www.python.org/downloads/macos/"
  echo "(or with Homebrew: brew install python@3.12), then run this script again."
  exit 1
fi
echo "Using $PYTHON ($("$PYTHON" --version))"

[ -d .venv ] || "$PYTHON" -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip setuptools wheel
.venv/bin/python -m pip install --quiet -r requirements.txt
.venv/bin/python -m app migrate

echo
echo "Installed in $APP_DIR"
echo "Try it:                       .venv/bin/python -m app"
echo "Run it for the whole office:  ./deploy/macos/start-at-login.sh --shared"
