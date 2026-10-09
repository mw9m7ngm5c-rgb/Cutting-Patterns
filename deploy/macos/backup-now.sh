#!/bin/bash
# Back up the database now (safe while the app is running). Copies go to backups/.
set -euo pipefail
cd "$(dirname "$0")/../.."
.venv/bin/python -m app backup --keep "${1:-30}"
