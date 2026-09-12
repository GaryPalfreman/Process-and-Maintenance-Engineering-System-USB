#!/bin/bash
set -e
APP="$HOME/Applications/PMES-USB"
PY="$APP/.venv/bin/python"
if [ ! -x "$PY" ]; then
  osascript -e 'display alert "Engineering System not installed" message "Run install_local.py once on this Mac before using this launcher."'
  exit 1
fi
cd "$APP"
exec "$PY" launch_local.py
